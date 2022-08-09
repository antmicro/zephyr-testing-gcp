#!/usr/bin/env python3

import filecmp
import git
import glob
import hashlib
import jinja2
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import time
import urllib.request
import yaml
import zipfile
from argparse import Namespace
from dts2repl import dts2repl
from joblib import Parallel, delayed, parallel_backend

from colorama import init
init()

from colorama import Fore, Back, Style

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

dashboard_url = 'https://zephyr-dashboard.renode.io'

def get_board_path(board):
    return str(board.dir).replace(os.getcwd()+'/','').replace(zephyr_path+'/','')

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

dts_flash_template = templateEnv.get_template('templates/flash_override.dts')
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

def run_in_renode(renode_platform, zephyr_platform, sample_name, uart_name, auto=False, script=None, remote_board=None):
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

    skip_sim = True
    if remote_board is not None:
        files = ('resc', 'repl', 'config', 'robot')
        files = filter(lambda f: f in remote_board['files'], files)

        if download_remote_artifacts(zephyr_platform, sample_name, files, suffix='.remote'):
            for remote_file in glob.glob(f'artifacts/{remote_board["board_name"]}-{remote_board["sample_name"]}/*.remote'):
                local_file = os.path.splitext(remote_file)[0]
                if not bool(filecmp.cmp(local_file, remote_file)):
                    skip_sim = False
                    print(f"Found difference in {bold(local_file)} contents!")
                    break
        else:
            skip_sim = False
    else:
        skip_sim = False

    # remove remote artifacts
    if remote_board is not None:
        for remote_file in glob.glob(f'artifacts/{remote_board["board_name"]}-{remote_board["sample_name"]}/*.remote'):
            os.remove(remote_file)

    if skip_sim:
        # download all artifacts without a suffix this time
        try:
            files = remote_board['files'][:]
            for f in ('elf', 'dts'):
                if f in remote_board['files']:
                    files.remove(f)
            download_remote_artifacts(zephyr_platform, sample_name, files)
            print(f'Skipping Renode simulation for platform {bold(zephyr_platform)}!')
            return remote_board['status'] == 'PASSED'
        except urllib.error.HTTPError:
            pass

    print(f'Run this interactively using: {bold("renode " + resc_filename)}')
    try:
        process = subprocess.Popen(f"./renode_portable/renode-test --kill-stale-renode-instances artifacts/{zephyr_platform}-{sample_name}/{zephyr_platform}-{sample_name}.robot".split(), start_new_session=True)
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

def download_remote_artifacts(zephyr_platform, sample_name, artifacts, suffix=""):
    print(f"Downloading artifacts {bold(zephyr_platform)}, sample: {bold(sample_name)}, files: ", end="")
    artifacts = list(artifacts)
    files = map(lambda x: artifacts_dict[x], artifacts)
    files = map(lambda x: x.format(board_name=zephyr_platform, sample_name=sample_name), files)
    files = map(lambda x: '/'.join(x.split('/')[1:]), files)
    downloads = []
    ret = True

    for remote_file, ftype in zip(files, artifacts):
        file_path = artifacts_dict[ftype].format(board_name=zephyr_platform, sample_name=sample_name) + suffix
        data = get_remote_file(f"{dashboard_url}/{remote_file}", decode=False)

        # if file wasn't found - break the loop
        if data is None:
            downloads.append(f'{bold(red(ftype))} not found')
            ret = False
            break

        with open(os.path.join(file_path), "wb") as f:
            downloads.append(f'{bold(green(ftype))} found')
            f.write(data)

    print(f'{", ".join(downloads)}.')
    return ret

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

def get_board_yaml_path(board_name, board_path):
    board_yaml = f'{zephyr_path}/{board_path}/{board_name}.yaml'

    # this hack is needed for pinetime_devkit0
    if not os.path.exists(board_yaml):
        board_yaml = f'{zephyr_path}/{board_path}/{board_name.replace("_", "-")}.yaml'

    return board_yaml

def run_renode_simulation(board_name, sample_name, sample_path, flat_boards, remote_board=None):
    result = {
        'board_name': board_name,
        'board_path': get_board_path(flat_boards[board_name]),
        'sample_name': sample_name,
        'status': 'NOT BUILT',
        'uart_name': '',
    }
    elf_filename = artifacts_dict['elf'].format(**result)
    dts_filename = artifacts_dict['dts'].format(**result)
    repl_filename = artifacts_dict['repl'].format(**result)
    save_filename = artifacts_dict['save'].format(**result)
    zephyr_log_filename = artifacts_dict['zephyr-log'].format(**result)
    board_yaml = get_board_yaml_path(board_name, result['board_path'])

    # this hack is needed for pinetime_devkit0
    if not os.path.exists(board_yaml):
        board_yaml = f'{zephyr_path}/{result["board_path"]}/{result["board_name"].replace("_", "-")}.yaml'

    if os.path.exists(elf_filename):
        result['status'] = 'BUILT'

    renode_platform = None
    extra_cmd = None
    uart = None

    if board_name in flat_boards:
        cpu, uart = try_match_board(flat_boards[board_name])
    else:
        print(f"Platform {bold(board_name)} not found anywhere. Typo?")
        return result

    result['arch'] = flat_boards[board_name].arch
    result['board_full_name'] = get_full_name(board_yaml)

    dts_path = f'{zephyr_path}/{result["board_path"]}/{result["board_name"]}.dts'
    result['cpu'] = get_cpu_name(result['arch'], dts_path)
    cpu_dep_chain = dts2repl.get_cpu_dep_chain(result['arch'], dts_path, zephyr_path, [])

    if uart is None:
        print("No uart. Cannot run test.")
    else:
        result['uart_name'] = uart

    if uart is not None and result['status'] != 'NOT BUILT':
        passed = False
        skip = False

        print(f"Autogenerating repl for {bold(board_name)} using device tree.")
        fake_args = Namespace(filename=dts_filename, overlays=",".join(cpu_dep_chain + [board_name]))
        repl = dts2repl.generate(fake_args)
        with open(repl_filename, 'w') as repl_file:
            repl_file.write(repl)

        if "cortex-m" in repl:
            extra_cmd = 'cpu0 VectorTableOffset `sysbus GetSymbolAddress "_vector_table"`'
        elif "RiscV" in repl:
            extra_cmd = f'cpu0 EnableProfiler true $ORIGIN/{board_name}-{sample_name}-profile true'

        passed = run_in_renode(repl_filename, board_name, sample_name, uart, True, extra_cmd, remote_board)
        result['repl_type'] = 'AUTO'
        result['repl_name'] = f'{board_name}-{sample_name}.repl'
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

def get_boards():
    # the Zephyr utility has its own argument parsing, so avoid args clash
    sys.argv = [sys.argv[0]]
    sys.path.append(f'{zephyr_path}/scripts')
    from list_boards import find_arch2boards
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument("--arch-root", dest='arch_roots', default=[],
                        type=Path, action='append',
                        help='''add an architecture root (ZEPHYR_BASE is
                        always present), may be given more than once''')
    parser.add_argument("--board-root", dest='board_roots', default=[],
                        type=Path, action='append',
                        help='''add a board root (ZEPHYR_BASE is always
                        present), may be given more than once''')
    return find_arch2boards(parser.parse_args())

def get_full_name(yaml_filename):
    if os.path.exists(yaml_filename):
        with open(yaml_filename) as f:
            board_data = yaml.load(f, Loader=yaml.FullLoader)
    
        full_board_name = board_data['name']
        if len(full_board_name) > 50:
            full_board_name = re.sub(r'\(.*\)', '', full_board_name)
    else:
        full_board_name = ''

    return full_board_name

def get_toolchain(yaml_filename):
    if os.path.exists(yaml_filename):
        with open(yaml_filename) as f:
            board_data = yaml.load(f, Loader=yaml.FullLoader)
            toolchains = board_data['toolchain']

        # try using the default zephyr toolchain
        if 'zephyr' in toolchains:
            toolchain = 'zephyr'
        else:
            toolchain = toolchains[0]
    else:
        print(f'Could not open YAML file {yaml_filename}! Defaulting to Zephyr toolchain...')
        toolchain = 'zephyr'

    return toolchain

def flatten(zephyr_boards):
    flat_boards = {}
    for arch in zephyr_boards:
        for board in zephyr_boards[arch]:
            flat_boards[board.name] = board
    return flat_boards

def try_match_board(board):
    sample_name, _ = get_sample_name_path()
    board_path = get_board_path(board)
    dts_filename = artifacts_dict['dts'].format(board_name=board.name, sample_name=sample_name)
    cpu_dep_chain = dts2repl.get_cpu_dep_chain(board.arch, dts_filename, zephyr_path, [])
    uart = dts2repl.get_uart(dts_filename)
    return None, uart

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
    if sample_name is None:
        # CI_NODE_INDEX starts with 1; default to the first entry
        idx = int(os.getenv('CI_NODE_INDEX', 1)) - 1
    else:
        # find first entry that matches the sample name
        idx = list(map(lambda x: x[0], samples)).index(sample_name)

    return samples[idx]

def get_remote_json(sample_name):
    url = f'{dashboard_url}/results-{sample_name}_all.json'

    return json.loads(get_remote_file(url))

def get_remote_version(name):
    return get_remote_file(f'{dashboard_url}/{name}.version').strip()

def get_remote_file(url, decode=True):
    content = None

    try:
        with urllib.request.urlopen(url) as u:
            content = u.read()
            content = content.decode() if decode else content
    except urllib.error.HTTPError:
        pass

    return content

def loop_wrapper(b, i, total_boards, dashboard_json, sample_name, sample_path, stage='build'):
    board_name = b if isinstance(b, str) else b.name
    if total_boards > 1:
        print(f">> [{i} / {total_boards}] -- {board_name} {stage} --")
    remote_board = filter(lambda x: x['board_name'] == board_name, dashboard_json)
    remote_board = next(remote_board, None)
    out = None

    artifacts_path = f'artifacts/{board_name}-{sample_name}'
    if not os.path.exists(artifacts_path):
        os.mkdir(artifacts_path)

    out = run_renode_simulation(board_name, sample_name, sample_path, flat_boards, remote_board)
    if total_boards > 1:
        print(f"<< [{i} / {total_boards}] -- {board_name} {stage} --")
    return out

def get_renode_version():
    renode_ver = subprocess.run('renode -v', capture_output=True, shell=True).stdout.decode()
    if renode_ver == "":
        return None

    renode_commit, renode_date = renode_ver.split()[-1][1:-1].split('-')
    renode_date = renode_date[:8]
    renode_ver = '.'.join(renode_ver.split()[-2].split('.')[:-1])

    return renode_commit, f'renode-{renode_ver}+{renode_date}@git{renode_commit}'

if __name__ == '__main__':
    # Determine if we want to run build/sim routines for all boards or only for
    # a subset of them. If any cmdline arguments are provided - treat them as
    # board names.
    selected_platforms = "all"
    if len(sys.argv) > 1:
        selected_platforms = sys.argv[1:]
        print(f'Running dashboard generation for the selected boards: {bold(", ".join(selected_platforms))}.') 
    else:
        print(f'Running dashboard generation for {bold("all boards")}.')

    # Get and write Renode version; save commit hash for later usage
    with open('artifacts/renode.version', 'w') as f:
        renode_ver = get_renode_version()
        if renode_ver is None:
           print('error: renode not found')
           sys.exit(1)

        renode_commit = renode_ver[0]
        f.write(renode_ver[1])

    # Get and write Zephyr version; save commit hash for later usage
    with open('artifacts/zephyr.version', 'w') as f:
        try:
            zephyr_repo = git.Repo(zephyr_path)
            zephyr_commit = zephyr_repo.git.rev_parse('HEAD', short=True)
            f.write(zephyr_commit)
        except git.exc.NoSuchPathError:
            print("error: zephyr not found")
            sys.exit(1)

    # Skipping simulation is possible if:
    # - local and remote Renode version are the same
    # - FORCE_SIM env variable has *not* been set
    _, renode_commit_remote = get_remote_version('renode').split('git')
    print(f'Comparing remote Renode commit {bold(renode_commit_remote)} with local {bold(renode_commit)}.')
    possible_sim_skip = renode_commit_remote == renode_commit
    possible_sim_skip = possible_sim_skip and not os.getenv('FORCE_SIM', False)

    sample_name, sample_path = get_sample_name_path()
    zephyr_boards = get_boards()
    flat_boards = flatten(zephyr_boards)
    flat_boards = dict(filter(lambda b: "qemu" not in b[0] and "native" not in b[0], flat_boards.items()))
    flat_boards = dict(filter(lambda b: not b[0].startswith("fvp_"), flat_boards.items()))
    dashboard_json = get_remote_json(sample_name) if possible_sim_skip else []
    if selected_platforms == "all":
        boards_to_run = flat_boards.values()
        omit_arch = ('arc', 'posix')
        boards_to_run = filter(lambda x: all(map(lambda y: y != x.arch, omit_arch)), boards_to_run)
        omit_board = ('acrn', 'qemu', 'native', 'nsim', 'xenvm', 'xt-sim')
        boards_to_run = list(filter(lambda x: all(map(lambda y: y not in x.name, omit_board)), boards_to_run))
    else:
        boards_to_run = selected_platforms

    boards_to_run = ['96b_aerocore2'] # Test

    total_boards = len(boards_to_run)
    sim_jobs = int(os.getenv('SIM_JOBS', 1))

    results = [loop_wrapper(b, i, total_boards, dashboard_json, sample_name, sample_path, stage='sim') for i, b in enumerate(boards_to_run, start=1)]

    # if boards are selected manually from the cmdline, append their names to
    # the final json file
    if isinstance(selected_platforms, list):
        selected_platforms = '_'.join(selected_platforms)

    with open(f"artifacts/results/results-{sample_name}_{selected_platforms}.json", "w") as f:
        json.dump(results, f)
