#!/usr/bin/env python
import itertools

WORKFLOW_FILE = 'workflow.yaml'
WORKFLOW_NAME = 'workflow'
SAMPLES = ['hello_world', 'shell_module', 'philosophers', 'micropython', 'tensorflow_lite_micro']
NUMBER_OF_THREADS = 2
MAX_NUMBER_OF_COMMITS = 2
UBUNTU_VERSION = 'jammy'
ZEPHYR_SDK_VERSION = '0.14.2'
RENODE_VERSION = '1.13.1+20220731git8eca7310'

def generate():
    commit_sample_product = list(itertools.product(range(MAX_NUMBER_OF_COMMITS), SAMPLES))
    tasks = []
    newline = '\n          '
    for zephyr_commit in range(MAX_NUMBER_OF_COMMITS):
        tasks.append(f'''
  prepare-zephyr-{zephyr_commit}:
    container: ubuntu:{UBUNTU_VERSION}
    runs-on: [self-hosted, Linux, X64]
    env:
      ZEPHYR_COMMIT: {zephyr_commit}
      ZEPHYR_SDK_VERSION: {ZEPHYR_SDK_VERSION}
    steps:
    - uses: actions/checkout@v2
    - name: Prepare environment
      run: ./scripts/prepare_environment.sh
    - name: Download Zephyr
      run: ./scripts/download_zephyr.sh
    - name: Pass Zephyr as artifact
      uses: actions/upload-artifact@v2
      with:
        name: zephyr-{zephyr_commit}
        path: zephyr.tar.gz''')
    for zephyr_commit, sample in commit_sample_product:
        tasks.append(f'''
  build-{zephyr_commit}-{sample}:
    container: ubuntu:{UBUNTU_VERSION}
    runs-on: [self-hosted, Linux, X64]
    needs: [prepare-zephyr-{zephyr_commit}]
    env:
      SAMPLE_NAME: {sample}
      MICROPYTHON_VERSION: 97a7cc243b
      NUMBER_OF_THREADS: {NUMBER_OF_THREADS}
    steps:
    - uses: actions/checkout@v2
    - name: Prepare environment
      run: ./scripts/prepare_environment.sh
    - name: Get Zephyr
      uses: actions/download-artifact@v2
      with:
        name: zephyr-{zephyr_commit}
        path: zephyr-artifact
    - name: Prepare Zephyr
      run: ./scripts/prepare_zephyr.sh
    - name: Prepare Micropython
      run: ./scripts/prepare_micropython.sh
    - name: Build boards
      run: ./scripts/build.py
    - name: Upload artifacts
      uses: actions/upload-artifact@v2
      with:
        name: build-{zephyr_commit}
        path: artifacts/''')
        tasks.append(f'''
  simulate-{zephyr_commit}-{sample}:
    container: ubuntu:{UBUNTU_VERSION}
    runs-on: [self-hosted, Linux, X64]
    needs: [build-{zephyr_commit}-{sample}]
    env:
       SAMPLE_NAME: {sample}
       RENODE_VERSION: {RENODE_VERSION}
    steps:
    - uses: actions/checkout@v2
    - name: Get artifacts
      uses: actions/download-artifact@v2
      with:
        name: build-{zephyr_commit}
        path: artifacts/
    - name: Prepare environment
      run: ./scripts/prepare_environment.sh
    - name: Prepare Renode
      run: ./scripts/download_renode.sh
    - name: Simulate
      run: ./scripts/simulate.py
    - name: Get Zephyr commit
      id: get-zephyr-commit
      run: |
        zephyr_commit=$(cat artifacts/zephyr.version)
        echo '::set-output name=ZEPHYR_COMMIT::$zephyr_commit'
    - name: Upload artifacts
      uses: actions/upload-artifact@v2
      with:
        name: ${"{{ steps.get-zephyr-commit.outputs.ZEPHYR_COMMIT }}"}
        path: artifacts/''')
    tasks.append(f'''
  results:
    container: ubuntu:{UBUNTU_VERSION}
    runs-on: [self-hosted, Linux, X64]
    needs: [{", ".join([f'simulate-{zephyr_commit}-{sample}' for zephyr_commit, sample in commit_sample_product])}]
    if: always()
    steps:
    - name: Delete unnecessary artifacts
      uses: geekyeggo/delete-artifact@v1
      with:
        name: |
          {newline.join([f"zephyr-{i}" for i in range(MAX_NUMBER_OF_COMMITS)])}
          {newline.join([f"build-{i}" for i in range(MAX_NUMBER_OF_COMMITS)])}
    - name: Download binaries
      uses: actions/download-artifact@v2
      with:
        path: results/
    - name: Install dependencies
      run: |
        apt update -qq
        apt install -y curl gnupg
    - name: Upload artifacts
      uses: actions/upload-artifact@v2
      with:
        name: result
        path: results''')
    with open(WORKFLOW_FILE, 'w') as file:
        file.write(f'''name: {WORKFLOW_NAME}
on:
  push:
    paths-ignore:
      - 'last_zephyr_commit'
  schedule:
    - cron: '0 3 * * *'
  workflow_dispatch:
jobs:''')
        file.write("".join(tasks))

if __name__ == '__main__':
    generate()

