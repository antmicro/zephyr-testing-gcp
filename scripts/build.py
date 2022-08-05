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


def build_sample(zephyr_platform, sample_name, sample_path, sample_args, toolchain, download_artifacts, skip_not_built):
    if download_artifacts:
        try:
            # all artifacts were succesfully downloaded, can return from this function
            artifacts = ['elf', 'dts', 'config', 'zephyr-log', 'sbom-app', 'sbom-build', 'sbom-zephyr']
            download_remote_artifacts(zephyr_platform, sample_name, artifacts)
            return
        except urllib.error.HTTPError:
            print("Artifact not found! ", end="")
            if skip_not_built:
                print("Skipping build locally due to matching CI hash.")
                return
            else:
                print("Trying to build it locally.")
    env = os.environ.copy()
    if toolchain == "zephyr":
        pass
    elif toolchain == "espressif":
        env["ZEPHYR_TOOLCHAIN_VARIANT"] = "espressif"
        env["ESPRESSIF_TOOLCHAIN_PATH"] = os.path.join(
            os.path.expanduser("~"), ".espressif", "tools", "zephyr"
        )
    else:
        print(f"Toolchain {bold(toolchain)} not found!")
        return
    print(f"Building for {bold(zephyr_platform)}, sample: {bold(sample_name)} with args: {bold(sample_args)} using {bold(toolchain)} toolchain.")
    args = f'-- {sample_args}' if sample_args != '' else ''
    process = subprocess.run(["./build_and_copy_bin.sh", zephyr_platform, sample_path, args, sample_name], stdout=subprocess.PIPE, env=env)

    # try increasing flash size if the sample doesn't fit in it 
    dts_filename = artifacts_dict['dts'].format(board_name=zephyr_platform, sample_name=sample_name)
    if process.returncode:
        m = re.search(r"region `FLASH' overflowed by (\d+) bytes", process.stdout.decode())
        if m is not None and os.path.exists(dts_filename):
            shutil.copy2(dts_filename, dts_filename + '.orig')
            flash_increase = math.ceil(int(m.group(1)) / 1024) * 1024
            flash_name, flash_size = find_flash_size(dts_filename)
            if len(flash_size) >= 2:
                flash_base, flash_size = flash_size[-2:]
                flash_size = int(flash_size, 16)
                flash_size += flash_increase

                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8') as f:
                    f.write(dts_flash_template.render(
                        flash_name=flash_name,
                        reg_base=flash_base,
                        reg_size=flash_size
                    ))
                    f.flush()
                    overlay_path = f.name

                    # build again, this time with bigger flash size
                    overlay_args = f'-DDTC_OVERLAY_FILE={overlay_path}'
                    args = f'-- {sample_args} {overlay_args}'
                    process = subprocess.run(["./build_and_copy_bin.sh", zephyr_platform, sample_path, args, sample_name], stdout=subprocess.PIPE, env=env)


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

def try_build(board_name, board_path, sample_name, sample_path, download_artifacts=False, skip_not_built=False):
    board_yaml = get_board_yaml_path(board_name, board_path)
    if os.getenv('CI', False):
        # check if additional custom config is available
        config_path = f'configs/{sample_name}.conf'
        if os.path.exists(config_path):
            sample_args = f'-DCONF_FILE={os.path.realpath(config_path)}'
        else:
            sample_args = ''

        # build the sample
        build_sample(board_name, sample_name, f'samples/{sample_path}', sample_args, get_toolchain(board_yaml), download_artifacts, skip_not_built)

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

def loop_wrapper(b, i, total_boards, dashboard_json, sample_name, sample_path, download_artifacts, skip_not_built):
    board_name = b if isinstance(b, str) else b.name
    if total_boards > 1:
        print(f">> [{i} / {total_boards}] -- {board_name} --")
    remote_board = filter(lambda x: x['board_name'] == board_name, dashboard_json)
    remote_board = next(remote_board, None)
    out = None

    artifacts_path = f'artifacts/{board_name}-{sample_name}'
    if not os.path.exists(artifacts_path):
        os.mkdir(artifacts_path)

    try_build(board_name, get_board_path(flat_boards[board_name]), sample_name, sample_path, download_artifacts, skip_not_built)
    if total_boards > 1:
        print(f"<< [{i} / {total_boards}] -- {board_name} --")
    return out


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

    # Get and write Zephyr version; save commit hash for later usage
    with open('artifacts/zephyr.version', 'w') as f:
        try:
            zephyr_repo = git.Repo(zephyr_path)
            zephyr_commit = zephyr_repo.git.rev_parse('HEAD', short=True)
            f.write(zephyr_commit)
        except git.exc.NoSuchPathError:
            print("error: zephyr not found")
            sys.exit(1)

    # Create a 'version' of CI script to determine later if we want to rebuild
    # boards with 'NOT BUILT' status. If nothing in the CI had changed,
    # presumably trying to rebuild them doesn't make sense and is a waste of
    # time.
    with open('.github/workflows/test.yml') as f:
        ci_contents = f.read().encode()
    with open('artifacts/ci.version', 'w') as f:
        build_version = hashlib.sha256(ci_contents).hexdigest()
        f.write(build_version)

    # Skipping simulation is possible if:
    # - local and remote Renode version are the same
    # - FORCE_SIM env variable has *not* been set
    _, renode_commit_remote = get_remote_version('renode').split('git')
    # print(f'Comparing remote Renode commit {bold(renode_commit_remote)} with local {bold(renode_commit)}.')
    possible_sim_skip = False
    possible_sim_skip = possible_sim_skip and not os.getenv('FORCE_SIM', False)

    # Skipping sample building is possible if:
    # - local and remote Zephyr version are the same
    # - FORCE_BUILD env variable has *not* been set
    zephyr_commit_remote = get_remote_version('zephyr')
    print(f'Comparing remote Zephyr commit {bold(zephyr_commit_remote)} with local {bold(zephyr_commit)}.')
    download_artifacts = zephyr_commit_remote == zephyr_commit
    download_artifacts = download_artifacts and not os.getenv('FORCE_BUILD', False)

    # We want to try to rebuild samples with 'NOT BUILT' status if:
    # - local and remote CI version are *not* the same
    # - FORCE_SKIP_NOT_BUILT has *not* been set
    # where CI version is a sha256 calculated from the CI script
    build_remote_version = get_remote_version('ci')
    skip_not_built = build_remote_version == build_version
    skip_not_built = skip_not_built or os.getenv('FORCE_SKIP_NOT_BUILT', False)

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
    build_jobs = int(os.getenv('BUILD_JOBS', 1))

    [loop_wrapper(b, i, total_boards, dashboard_json, sample_name, sample_path, download_artifacts, skip_not_built) for i, b in enumerate(boards_to_run, start=1)]

    # if boards are selected manually from the cmdline, append their names to
    # the final json file
    if isinstance(selected_platforms, list):
        selected_platforms = '_'.join(selected_platforms)
