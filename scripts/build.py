#!/usr/bin/env python3

import git
import jinja2
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import yaml
from joblib import Parallel, delayed, parallel_backend

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


def get_board_path(board):
    return str(board.dir).replace(os.getcwd()+'/','').replace(zephyr_path+'/','')


templateLoader = jinja2.FileSystemLoader(searchpath="./")
templateEnv = jinja2.Environment(loader=templateLoader)

dts_flash_template = templateEnv.get_template('templates/flash_override.dts')

def find_flash_size(dts_filename):
    with open(dts_filename) as f:
        dts = f.read()

    flash_name = re.search(r"zephyr,flash = &(\w+);", dts).group(1)
    flash_size = re.search(r"{}:(.*\n)*?.*reg = <(.*)>;".format(flash_name), dts).group(2)
    flash_size = flash_size.split()

    return flash_name, flash_size

def build_and_copy_bin(zephyr_platform, sample_path, args, sample_name, env):
    zephyr_sample_name = f"{zephyr_platform}-{sample_name}"
    return_code = 1
    os.makedirs(f"artifacts/{zephyr_sample_name}", exist_ok=True)
    previous_dir = os.getcwd()
    os.chdir(zephyr_path)
    build_path = f"build.{zephyr_platform}.{sample_name}"
    if os.path.isdir(build_path):
        shutil.rmtree(build_path)
    log_path = f"../../artifacts/{zephyr_sample_name}/{zephyr_sample_name}-zephyr.log"

    run_west_cmd(f"west spdx --init -d {build_path}", env, log_path)
    west_output = run_west_cmd(f"west build --pristine -b {zephyr_platform} -d {build_path} {sample_path} {args}".strip(), env, log_path)
    run_west_cmd(f"west spdx -d {build_path}", env, log_path)

    os.chdir(previous_dir)
    file_list=["zephyr/zephyr.elf", "zephyr/zephyr.dts", "zephyr/.config", "spdx/app.spdx", "spdx/build.spdx", "spdx/zephyr.spdx"]

    for file_name in file_list:
        file_path = f"{zephyr_path}/{build_path}/{file_name}"
        base_name = os.path.basename(file_path)
        if os.path.exists(file_path):
            if re.search("spdx/.+", file_name):
                shutil.copyfile(file_path, f"artifacts/{zephyr_sample_name}/{zephyr_sample_name}-{base_name}")
            if file_name == file_list[0]:
                shutil.copyfile(file_path, f"artifacts/{zephyr_sample_name}/{zephyr_platform}-zephyr-{sample_name}.elf")
                return_code = 0
            if file_name == file_list[1]:
                shutil.copyfile(file_path, f"artifacts/{zephyr_sample_name}/{zephyr_sample_name}.dts")
            if file_name == file_list[2]:
                shutil.copyfile(file_path, f"artifacts/{zephyr_sample_name}/{zephyr_sample_name}-config")
    if os.path.isdir(f"{zephyr_path}/{build_path}"):
        shutil.rmtree(f"{zephyr_path}/{build_path}")
    return return_code, west_output

def run_west_cmd(cmd, env, log_file):
    try:
        output = subprocess.check_output((cmd.split(" ")), env=env, stderr=subprocess.STDOUT).decode()
    except subprocess.CalledProcessError as error:
        output = error.output.decode()
    with open(log_file, 'a') as file:
        file.write(output)
    return output

def build_sample(zephyr_platform, sample_name, sample_path, sample_args, toolchain):
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
    print(f"Building for {bold(zephyr_platform)}, sample: {bold(sample_name)} with args: {bold(sample_args)} using {bold(toolchain)} toolchain.")
    args = f'-- {sample_args}' if sample_args != '' else ''
    return_code, west_output = build_and_copy_bin(zephyr_platform, sample_path, args, sample_name, env)
    # try increasing flash size if the sample doesn't fit in it
    dts_filename = 'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}.dts'.format(board_name=zephyr_platform, sample_name=sample_name)
    m = re.search(r"region `FLASH' overflowed by (\d+) bytes", west_output)
    if return_code:
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
                    build_and_copy_bin(zephyr_platform, sample_path, args, sample_name, env)

def get_board_yaml_path(board_name, board_path):
    board_yaml = f'{zephyr_path}/{board_path}/{board_name}.yaml'

    # this hack is needed for pinetime_devkit0
    if not os.path.exists(board_yaml):
        board_yaml = f'{zephyr_path}/{board_path}/{board_name.replace("_", "-")}.yaml'

    return board_yaml

def try_build(board_name, board_path, sample_name, sample_path):
    board_yaml = get_board_yaml_path(board_name, board_path)
    config_path = f'configs/{sample_name}.conf'
    if os.path.exists(config_path):
        sample_args = f'-DCONF_FILE={os.path.realpath(config_path)}'
    else:
        sample_args = ''

    # build the sample
    build_sample(board_name, sample_name, f'samples/{sample_path}', sample_args, get_toolchain(board_yaml))

def get_boards():
    # the Zephyr utility has its own argument parsing, so avoid args clash
    sys.argv = [sys.argv[0]]
    sys.path.append(f'{zephyr_path}/scripts')
    from list_boards import find_arch2boards
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument("--arch-root", dest='arch_roots', default=[Path(zephyr_path)],
                        type=Path, action='append',
                        help='''add an architecture root (ZEPHYR_BASE is
                        always present), may be given more than once''')
    parser.add_argument("--board-root", dest='board_roots', default=[Path(zephyr_path)],
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

samples = (
    # sample name and path of the samples that we support
    ("hello_world", "hello_world"),
    ("shell_module", "subsys/shell/shell_module"),
    ("philosophers", "philosophers"),
    ("micropython", "../../../micropython/ports/zephyr"),
    ("tensorflow_lite_micro", "modules/tflite-micro/hello_world"),
)

def get_sample_name_path():
    sample_name = os.getenv('SAMPLE_NAME')
    idx = list(map(lambda x: x[0], samples)).index(sample_name) if sample_name is not None else 0
    return samples[idx]

def loop_wrapper(b, i, total_boards, sample_name, sample_path):
    board_name = b if isinstance(b, str) else b.name
    if total_boards > 1:
        print(f">> [{i} / {total_boards}] -- {board_name} --")
    remote_board = filter(lambda x: x['board_name'] == board_name, [])
    remote_board = next(remote_board, None)
    out = None

    try_build(board_name, get_board_path(flat_boards[board_name]), sample_name, sample_path)
    if total_boards > 1:
        print(f"<< [{i} / {total_boards}] -- {board_name} --")
    return out


if __name__ == '__main__':
    # Get and write Zephyr version; save commit hash for later usage
    with open('artifacts/zephyr.version', 'w') as f:
        try:
            zephyr_repo = git.Repo(zephyr_path)
            zephyr_commit = zephyr_repo.git.rev_parse('HEAD', short=True)
            f.write(zephyr_commit)
        except git.exc.NoSuchPathError:
            print("error: zephyr not found")
            sys.exit(1)

    sample_name, sample_path = get_sample_name_path()
    zephyr_boards = get_boards()
    flat_boards = flatten(zephyr_boards)
    flat_boards = dict(filter(lambda b: "qemu" not in b[0] and "native" not in b[0], flat_boards.items()))
    flat_boards = dict(filter(lambda b: not b[0].startswith("fvp_"), flat_boards.items()))
    boards_to_run = flat_boards.values()
    omit_arch = ('arc', 'posix')
    boards_to_run = filter(lambda x: all(map(lambda y: y != x.arch, omit_arch)), boards_to_run)
    omit_board = ('acrn', 'qemu', 'native', 'nsim', 'xenvm', 'xt-sim')
    boards_to_run = list(filter(lambda x: all(map(lambda y: y not in x.name, omit_board)), boards_to_run))
    total_boards = len(boards_to_run)
    thread_number = int(os.getenv("NUMBER_OF_THREADS", 1))

    with parallel_backend('multiprocessing', n_jobs=thread_number):
        Parallel()(delayed(loop_wrapper)(board, i, total_boards, sample_name, sample_path) for i, board in enumerate(boards_to_run, start=1))

    boards_to_serialize = []
    for board in boards_to_run:
        boards_to_serialize.append({
            "name": board.name,
            "full_name": get_full_name(get_board_yaml_path(board.name, get_board_path(board))),
            "arch": board.arch,
            "path": get_board_path(board)
            })
    with open("artifacts/built_boards.json", "w") as file:
        json.dump(boards_to_serialize, file)

