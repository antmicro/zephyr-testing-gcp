#!/usr/bin/env python3

import jinja2
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
import time
from argparse import Namespace
from dts2repl import dts2repl
import xml.etree.ElementTree as ET

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
robots_yaml = 'artifacts/robots.yaml'
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

def prepare_robot_file(renode_platform, zephyr_platform, sample_name, uart_name, script=None):
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

def run_renode_simulation(boards, sample_name, thread_number):
    robots = []
    result = []
    for board in boards:
        result.append({
            'board_name': board['name'],
            'board_path': board['path'],
            'sample_name': sample_name,
            'status': 'NOT BUILT',
            'uart_name': '',
        })
        elf_filename = artifacts_dict['elf'].format(**result[-1])
        dts_filename = artifacts_dict['dts'].format(**result[-1])
        repl_filename = artifacts_dict['repl'].format(**result[-1])

        if os.path.exists(elf_filename):
            result[-1]['status'] = 'BUILT'

        uart = try_match_board(board)

        result[-1]['arch'] = board['arch']
        result[-1]['board_full_name'] = board['full_name']

        dts_path = f'{zephyr_path}/{result[-1]["board_path"]}/{result[-1]["board_name"]}.dts'
        result[-1]['cpu'] = get_cpu_name(result[-1]['arch'], dts_path)
        cpu_dep_chain = dts2repl.get_cpu_dep_chain(result[-1]['arch'], dts_path, zephyr_path, [])

        extra_cmd = None

        if uart is None:
            print(f"{board['name']}-{sample_name}: No uart. Cannot run test.")
        else:
            result[-1]['uart_name'] = uart

        if uart is not None and result[-1]['status'] != 'NOT BUILT':
            print(f"Autogenerating repl for {bold(board['name'])} using device tree.")
            fake_args = Namespace(filename=dts_filename, overlays=",".join(cpu_dep_chain + [board['name']]))
            repl = dts2repl.generate(fake_args)
            with open(repl_filename, 'w') as repl_file:
                repl_file.write(repl)

            if "cortex-m" in repl:
                extra_cmd = 'cpu0 VectorTableOffset `sysbus GetSymbolAddress "_vector_table"`'
            elif "RiscV" in repl:
                extra_cmd = f"cpu0 EnableProfiler true $ORIGIN/{board['name']}-{sample_name}-profile true"
            prepare_robot_file(repl_filename, board['name'], sample_name, uart, extra_cmd)
            robots.append(artifacts_dict['robot'].format(board_name=board['name'], sample_name=sample_name))
            result[-1]['repl_type'] = 'AUTO'
            result[-1]['repl_name'] = f"{board['name']}-{sample_name}.repl"
    with open(robots_yaml, 'w') as file:
        for robot in robots:
            file.write(f"- {robot}\n")
    subprocess.run(f"./renode_portable/renode-test -t {robots_yaml} -j {thread_number}".split())
    robot_output = ET.parse("robot_output.xml").getroot()
    stats = robot_output.findall(".//statistics/suite/stat")[1:]
    stats = {stat.attrib['name']: int(stat.attrib['pass']) for stat in stats}

    for res in result:
        test_name = f"{res['board_name']}-{res['sample_name']}"
        if test_name in stats and stats[test_name] > 0:
            res['status'] = 'PASSED'

        # create zip archive with all artifacts
        res['files'] = get_artifacts_list(res)
        create_zip_archive(res)

        # create zip archive with sboms
        sbom_zip_name = artifacts_dict['zip-sbom'].format(**res)
        create_zip_archive(res, zip_name=sbom_zip_name, files=['sbom-app', 'sbom-zephyr', 'sbom-build'])

        # get memory usage
        memory = {}
        if res['status'] != 'NOT BUILT':
            with open(artifacts_dict['zephyr-log'].format(**res)) as f:
                match = re.findall(r"(?P<region>\w+){1}:\s*(?P<used>\d+\s+\w{1,2})\s*(?P<size>\d+\s+\w{1,2})\s*(?P<percentage>\d+.\d+%)", f.read())
            for m in match:
                region, used, size, _ = m
                memory[region] = {
                    'used': conv_zephyr_mem_usage(used),
                    'size': conv_zephyr_mem_usage(size),
                }

            # check if flash size was increased
            if os.path.exists(artifacts_dict['dts'].format(**res) + '.orig') and 'FLASH' in memory:
                _, flash_size = find_flash_size(artifacts_dict['dts'].format(**res) + '.orig')
                flash_size = int(flash_size[-1], 16)
                memory['FLASH'].update({
                    'size': flash_size,
                })

        res['memory'] = memory
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
    thread_number = int(os.getenv("NUMBER_OF_THREADS", 1))

    results = run_renode_simulation(boards_to_run, sample_name, thread_number)

    with open(f"artifacts/results/results-{sample_name}_all.json", "w") as f:
        json.dump(results, f)
