#!/usr/bin/env python3

import jinja2
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import zipfile
from argparse import Namespace
from dts2repl import dts2repl

from colorama import init
init()

from colorama import Fore, Style

def bold(text):
    return Style.BRIGHT + (text or '') + Style.RESET_ALL

def red(text):
    return Fore.RED + (text or '') + Style.RESET_ALL

def green(text):
    return Fore.GREEN + (text or '') + Style.RESET_ALL

zephyr_path = 'zephyrproject/zephyr'
artifacts_dict = {
    'asciinema':    'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}-asciinema',
    'config':       'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}-config',
    'dts':          'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}.dts',
    'elf':          'artifacts/{board_name}-{sample_name}/{board_name}-zephyr-{sample_name}.elf',
    'log':          'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}.html',
    'monitor':      'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}_monitor.txt',
    'profiling':    'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}-profile',
    'repl':         'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}.repl',
    'resc':         'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}.resc',
    'robot':        'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}.robot',
    'save':         'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}.{sample_name}_on_{board_name}.fail.save',
    'sbom-app':     'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}-app.spdx',
    'sbom-build':   'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}-build.spdx',
    'sbom-zephyr':  'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}-zephyr.spdx',
    'zip':          'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}.zip',
    'zip-sbom':     'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}-sbom.zip',
    'zephyr-log':   'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}-zephyr.log',
}

def get_cpu_name(arch, dts_filename, verbose=False):
    cpu_dep_chain = dts2repl.get_cpu_dep_chain(arch, dts_filename, zephyr_path, [])
    verbose = os.getenv("VERBOSE", False) or verbose
    cpu_dep_chain_string = ''
    if not verbose:
        if len(cpu_dep_chain) > 0:
            for cpu in cpu_dep_chain:
                if cpu[0] != '!':
                    cpu_dep_chain_string = cpu
                    break
    else:
        cpu_dep_chain_string = " -> ".join(cpu_dep_chain)

    return cpu_dep_chain_string


templateLoader = jinja2.FileSystemLoader(searchpath="./")
templateEnv = jinja2.Environment(loader=templateLoader)

resc_template = templateEnv.get_template('templates/common.resc')
robot_template_hello_world = templateEnv.get_template('templates/hello_world.robot')
robot_template_shell_module = templateEnv.get_template('templates/shell_module.robot')
robot_template_philosophers = templateEnv.get_template('templates/philosophers.robot')
robot_template_micropython = templateEnv.get_template('templates/micropython.robot')
robot_template_tflm = templateEnv.get_template('templates/tensorflow_lite_micro.robot')

robot_templates = {
    'hello_world':           robot_template_hello_world,
    'shell_module':          robot_template_shell_module,
    'philosophers':          robot_template_philosophers,
    'micropython':           robot_template_micropython,
    'tensorflow_lite_micro': robot_template_tflm,
}

def run_in_renode(renode_platform, zephyr_platform, sample_name, uart_name, script=None):
    rm_files = ('log.html', 'logs', 'monitor.txt')
    format_args = {
        'board_name': zephyr_platform,
        'sample_name': sample_name,
    }
    resc_filename = artifacts_dict['resc'].format(**format_args)
    repl_filename = artifacts_dict['repl'].format(**format_args)
    robot_filename = artifacts_dict['robot'].format(**format_args)
    monitor_filename = artifacts_dict['monitor'].format(**format_args)
    log_filename = artifacts_dict['log'].format(**format_args)
    config_filename = artifacts_dict['config'].format(**format_args)
    save_filename = artifacts_dict['save'].format(**format_args)

    if os.path.exists(f"renode_portable/platforms/{renode_platform}"):
        shutil.copy2(f"renode_portable/platforms/{renode_platform}", repl_filename)

    # it's a repl, not a resc, generate relevant resc file
    renode_platform = renode_platform[:-5]
    with open(resc_filename, "w") as resc_file:
        resc_file.write(resc_template.render(
            renode_platform=renode_platform,
            zephyr_platform=zephyr_platform,
            path_to_artifacts="artifacts",
            sample_name=sample_name,
            uart_name=uart_name,
            script=script
        ))

    # get CONFIG_BOARD as defined in the config file
    with open(config_filename) as f:
        m = re.search(r'CONFIG_BOARD="(.*)"', f.read())
        config_board_name = m.group(1)

    with open(robot_filename, "w") as robot_file:
        robot_file.write(robot_templates[sample_name].render(
            board_name=zephyr_platform,
            config_board_name=config_board_name,
            uart_name=uart_name,
            sample_name=sample_name
        ))

    try:
        process = subprocess.Popen(f"./renode_portable/renode-test --kill-stale-renode-instances {artifacts_dict['robot'].format(board_name=zephyr_platform, sample_name=sample_name)}".split(), start_new_session=True)
        pgid = os.getpgid(process.pid)
        _, __ = process.communicate(timeout=30)
        ret = process.returncode
    except subprocess.TimeoutExpired:
        # We send two interrupt signals to shut down Robot
        print(f"Timeout running tests for {zephyr_platform}-{sample_name}")
        os.killpg(pgid, signal.SIGINT)
        os.killpg(pgid, signal.SIGINT)
        process.terminate()
        ret = 1

    snapshot_path = os.path.join("snapshots", os.path.basename(save_filename))
    if os.path.exists(snapshot_path):
        shutil.copy2(snapshot_path, save_filename)

    if os.path.exists("monitor.txt"):
        with open("monitor.txt") as f:
            monitor = f.read().split('\n')

        # save only the first 100 lines of logs
        monitor = '\n'.join(monitor[:100])
        with open(monitor_filename, "w") as f:
            f.write(monitor)

    # give Renode 1s of time if Robot logs were not yet generated
    if not os.path.exists("log.html"):
        time.sleep(1)
    if os.path.exists("log.html"):
        shutil.copy2("log.html", log_filename);

    # clean unneeded artifacts
    for f in rm_files:
        if os.path.exists(f):
            if os.path.isdir(f):
                shutil.rmtree(f)
            else:
                os.remove(f)

    if ret:
        print(red("Test failed."))
        return False
    else:
        print(green("Test passed."))
        return True

def conv_zephyr_mem_usage(val):
    if val.endswith(' B'):
        val = int(val[:-2])
    elif val.endswith(' KB'):
        val = int(val[:-2]) * 1024
    elif val.endswith(' MB'):
        val = int(val[:-2]) * 1024 * 1024
    elif val.endswith(' GB'):
        val = int(val[:-2]) * 1024 * 1024 * 1024

    return val


def find_flash_size(dts_filename):
    with open(dts_filename) as f:
        dts = f.read()
    flash_name = re.search(r"zephyr,flash = &(\w+);", dts).group(1)
    flash_size = re.search(r"{}:(.*\n)*?.*reg = <(.*)>;".format(flash_name), dts).group(2)
    flash_size = flash_size.split()

    return flash_name, flash_size

def create_zip_archive(platform, zip_name=None, files=[]):
    if zip_name is None:
        zip_filename = artifacts_dict['zip'].format(**platform)
    else:
        zip_filename = zip_name

    with zipfile.ZipFile(zip_filename, 'w') as f:
        for ftype in platform['files'] if files == [] else files:
            fname = artifacts_dict[ftype].format(**platform)
            if os.path.exists(fname):
                f.write(fname)

def get_artifacts_list(platform):
    ret = []
    for ftype, path in artifacts_dict.items():
        file_path = path.format(**platform)
        if os.path.exists(file_path) and os.stat(file_path).st_size > 0 and not ftype.startswith('zip'):
            ret.append(ftype)

    return ret

def run_renode_simulation(board, sample_name):
    result = {
        'board_name': board['name'],
        'board_path': board['path'],
        'sample_name': sample_name,
        'status': 'NOT BUILT',
        'uart_name': '',
    }
    elf_filename = artifacts_dict['elf'].format(**result)
    dts_filename = artifacts_dict['dts'].format(**result)
    repl_filename = artifacts_dict['repl'].format(**result)
    save_filename = artifacts_dict['save'].format(**result)
    zephyr_log_filename = artifacts_dict['zephyr-log'].format(**result)

    if os.path.exists(elf_filename):
        result['status'] = 'BUILT'

    uart = try_match_board(board)

    result['arch'] = board['arch']
    result['board_full_name'] = board['full_name']

    dts_path = artifacts_dict['dts'].format(board_name=board['name'], sample_name=sample_name)
    result['cpu'] = get_cpu_name(result['arch'], dts_path)
    cpu_dep_chain = dts2repl.get_cpu_dep_chain(result['arch'], dts_path, zephyr_path, [])

    extra_cmd = None

    if uart is None:
        print("No uart. Cannot run test.")
    else:
        result['uart_name'] = uart

    if uart is not None and result['status'] != 'NOT BUILT':
        passed = False

        print(f"Autogenerating repl for {bold(board['name'])} using device tree.")
        fake_args = Namespace(filename=dts_filename, overlays=",".join(cpu_dep_chain + [board['name']]))
        repl = dts2repl.generate(fake_args)
        with open(repl_filename, 'w') as repl_file:
            repl_file.write(repl)

        if "cortex-m" in repl:
            extra_cmd = 'cpu0 VectorTableOffset `sysbus GetSymbolAddress "_vector_table"`'
        elif "RiscV" in repl:
            extra_cmd = f"cpu0 EnableProfiler true $ORIGIN/{board['name']}-{sample_name}-profile true"

        passed = run_in_renode(repl_filename, board['name'], sample_name, uart, extra_cmd)
        result['repl_type'] = 'AUTO'
        result['repl_name'] = f"{board['name']}-{sample_name}.repl"
        if passed:
            # state snapshot was created by the previously failed run (dict-matched)
            if os.path.exists(save_filename):
                os.remove(save_filename)
            result['status'] = 'PASSED'

    # create zip archive with all artifacts
    result['files'] = get_artifacts_list(result)
    create_zip_archive(result)

    # create zip archive with sboms
    sbom_zip_name = artifacts_dict['zip-sbom'].format(**result)
    create_zip_archive(result, zip_name=sbom_zip_name, files=['sbom-app', 'sbom-zephyr', 'sbom-build'])

    # get memory usage
    memory = {}
    if result['status'] != 'NOT BUILT':
        with open(zephyr_log_filename) as f:
            match = re.findall(r"(?P<region>\w+){1}:\s*(?P<used>\d+\s+\w{1,2})\s*(?P<size>\d+\s+\w{1,2})\s*(?P<percentage>\d+.\d+%)", f.read())
        for m in match:
            region, used, size, _ = m
            memory[region] = {
                'used': conv_zephyr_mem_usage(used),
                'size': conv_zephyr_mem_usage(size),
            }

        # check if flash size was increased
        if os.path.exists(dts_filename + '.orig') and 'FLASH' in memory:
            _, flash_size = find_flash_size(dts_filename + '.orig')
            flash_size = int(flash_size[-1], 16)
            memory['FLASH'].update({
                'size': flash_size,
            })

    result['memory'] = memory

    return result

def try_match_board(board):
    sample_name, _ = get_sample_name_path()
    dts_filename = artifacts_dict['dts'].format(board_name=board['name'], sample_name=sample_name)
    uart = dts2repl.get_uart(dts_filename)
    return uart

samples = (
    # sample name and path of the samples that we support
    ("hello_world", "hello_world"),
    ("shell_module", "subsys/shell/shell_module"),
    ("philosophers", "philosophers"),
    ("micropython", "../../../micropython/ports/zephyr"),
    ("tensorflow_lite_micro", "modules/tflite-micro/hello_world"),
)

def get_sample_name_path():
    # make it possible for the user to choose which sample to build
    sample_name = os.getenv('SAMPLE_NAME')
    idx = list(map(lambda x: x[0], samples)).index(sample_name) if sample_name is not None else 0
    return samples[idx]

def loop_wrapper(b, i, total_boards, sample_name):
    board_name = b if isinstance(b, str) else b["name"]
    if total_boards > 1:
        print(f">> [{i} / {total_boards}] -- {board_name} --")
    out = None

    out = run_renode_simulation(b, sample_name)
    if total_boards > 1:
        print(f"<< [{i} / {total_boards}] -- {board_name} --")
    return out

def get_renode_version():
    renode_ver = subprocess.run(f'./renode_portable/renode -v', capture_output=True, shell=True).stdout.decode()
    if renode_ver == "":
        return None

    renode_commit, renode_date = renode_ver.split()[-1][1:-1].split('-')
    renode_date = renode_date[:8]
    renode_ver = '.'.join(renode_ver.split()[-2].split('.')[:-1])

    return renode_commit, f'renode-{renode_ver}+{renode_date}@git{renode_commit}'

if __name__ == '__main__':
    # Get and write Renode version; save commit hash for later usage
    with open('artifacts/renode.version', 'w') as f:
        renode_ver = get_renode_version()
        if renode_ver is None:
           print('error: renode not found')
           sys.exit(1)

        renode_commit = renode_ver[0]
        f.write(renode_ver[1])


    sample_name, _ = get_sample_name_path()
    with open("artifacts/built_boards.json") as file:
        boards_to_run = json.loads(file.read())

    total_boards = len(boards_to_run)
    sim_jobs = int(os.getenv('SIM_JOBS', 1))

    results = [loop_wrapper(b, i, total_boards, sample_name) for i, b in enumerate(boards_to_run, start=1)]

    with open(f"artifacts/results/results-{sample_name}_all.json", "w") as f:
        json.dump(results, f)
