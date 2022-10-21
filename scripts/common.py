#!/usr/bin/env python3

import re
import os
from colorama import init, Fore, Style

samples = {
    "hello_world": "hello_world",
    "shell_module": "subsys/shell/shell_module",
    "philosophers": "philosophers",
    "micropython": "../../../micropython/ports/zephyr",
    "tensorflow_lite_micro": "modules/tflite-micro/hello_world",
}

artifacts_dict = {
    'asciinema':    'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}-asciinema',
    'config':       'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}-config',
    'dts':          'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}.dts',
    'elf':          'artifacts/{board_name}-{sample_name}/{board_name}-zephyr-{sample_name}.elf',
    'log':          'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}.html',
    'monitor':      'artifacts/{board_name}-{sample_name}/{board_name}-{sample_name}_renode.log',
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

def bold(text):
    return Style.BRIGHT + (text or '') + Style.RESET_ALL

def red(text):
    return Fore.RED + (text or '') + Style.RESET_ALL

def green(text):
    return Fore.GREEN + (text or '') + Style.RESET_ALL

def get_sample_name_path():
    sample_name = os.getenv('SAMPLE_NAME', default="hello_world")
    return sample_name, samples[sample_name]

def find_flash_size(dts_filename):
    with open(dts_filename) as f:
        dts = f.read()
    try:
        flash_name = re.search(r"zephyr,flash = &(\w+);", dts).group(1)
        flash_size = re.search(r"{}:(.*\n)*?.*reg = <(.*)>;".format(flash_name), dts).group(2)
        flash_size = flash_size.split()
    except AttributeError:
        return None
    return flash_name, flash_size

init()
