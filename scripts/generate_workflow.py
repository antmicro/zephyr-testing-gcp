#!/usr/bin/env python
import itertools

WORKFLOW_FILE = 'workflow.yaml'
WORKFLOW_NAME = 'workflow'
SAMPLES = ['hello_world', 'shell_module', 'philosophers', 'micropython', 'tensorflow_lite_micro']
NUMBER_OF_THREADS_BUILD = 32
NUMBER_OF_THREADS_SIMULATE = 2
MAX_NUMBER_OF_COMMITS = 2
UBUNTU_VERSION = 'jammy'
ZEPHYR_SDK_VERSION = '0.14.2'
RENODE_VERSION = '1.13.1+20220731git8eca7310'
LAST_ZEPHYR_COMMIT_FILE = 'last_zephyr_commit'

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
      NUMBER_OF_THREADS: {NUMBER_OF_THREADS_BUILD}
      GHA_MACHINE_TYPE: "n2-standard-32"
    steps:
    - uses: actions/checkout@v2
    - name: Get sargraph
      uses: actions/checkout@v2
      with:
        repository: antmicro/sargraph
        path: sargraph
        fetch-depth: 0
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
    - name: Start sargraph
      run: ./sargraph/sargraph.py build start
    - name: Build boards
      run: ./scripts/build.py
    - name: Stop sargraph
      run: |
        ./sargraph/sargraph.py build stop
        mv plot.png artifacts/build_{sample}_plot.png
    - name: Upload artifacts
      uses: actions/upload-artifact@v2
      with:
        name: build-{zephyr_commit}-{sample}
        path: artifacts/''')
        tasks.append(f'''
  simulate-{zephyr_commit}-{sample}:
    container: ubuntu:{UBUNTU_VERSION}
    runs-on: [self-hosted, Linux, X64]
    needs: [build-{zephyr_commit}-{sample}]
    outputs:
      ZEPHYR_COMMIT: ${{{{ steps.get-zephyr-commit.outputs.ZEPHYR_COMMIT }}}}
    env:
      SAMPLE_NAME: {sample}
      RENODE_VERSION: {RENODE_VERSION}
      NUMBER_OF_THREADS: {NUMBER_OF_THREADS_SIMULATE}
      GHA_SA: "gh-sa-gcp-distributed-job-buck"
      GHA_MACHINE_TYPE: "n2-standard-32"
    steps:
    - uses: actions/checkout@v2
    - name: Get sargraph
      uses: actions/checkout@v2
      with:
        repository: antmicro/sargraph
        path: sargraph
        fetch-depth: 0
    - name: Get artifacts
      uses: actions/download-artifact@v2
      with:
        name: build-{zephyr_commit}-{sample}
        path: artifacts/
    - name: Prepare environment
      run: ./scripts/prepare_environment.sh
    - name: Prepare Renode
      run: ./scripts/download_renode.sh
    - name: Start sargraph
      run: ./sargraph/sargraph.py simulate start
    - name: Simulate
      run: ./scripts/simulate.py
    - name: Stop sargraph
      run: |
        ./sargraph/sargraph.py simulate stop
        mv plot.png artifacts/simulate_{sample}_plot.png
    - name: Get Zephyr commit
      id: get-zephyr-commit
      run: |
        ZEPHYR_COMMIT=$(cat artifacts/zephyr.version)
        echo "::set-output name=ZEPHYR_COMMIT::$ZEPHYR_COMMIT"
    - name: Install dependencies
      run: ./scripts/prepare_gcp.sh
    - name: Upload artifacts
      run: |
        mv artifacts/ ${{{{ steps.get-zephyr-commit.outputs.ZEPHYR_COMMIT }}}}
        gsutil -m cp -r ${{{{ steps.get-zephyr-commit.outputs.ZEPHYR_COMMIT }}}} gs://gcp-distributed-job-test-bucket''')
    tasks.append(f'''
  results:
    container: ubuntu:{UBUNTU_VERSION}
    runs-on: [self-hosted, Linux, X64]
    needs: [{", ".join([f'simulate-{zephyr_commit}-{sample}' for zephyr_commit, sample in commit_sample_product])}]
    if: always()
    steps:
    - uses: actions/checkout@v2
    - name: Delete artifacts
      uses: geekyeggo/delete-artifact@v1
      with:
        name: |
          {newline.join([f"zephyr-{i}" for i in range(MAX_NUMBER_OF_COMMITS)])}
          {newline.join([f"build-{commit}-{sample}" for commit, sample in commit_sample_product])}
    - name: Update latest Zephyr commit
      run: echo ${{{{ needs.simulate-0-hello_world.outputs.ZEPHYR_COMMIT }}}} > {LAST_ZEPHYR_COMMIT_FILE}
    - name: Commit latest Zephyr commit
      uses: stefanzweifel/git-auto-commit-action@v4
      with:
        commit_message: Update latest Zephyr commit ${{{{ needs.simulate-0-hello_world.outputs.ZEPHYR_COMMIT }}}}
        file_pattern: {LAST_ZEPHYR_COMMIT_FILE}''')
    with open(WORKFLOW_FILE, 'w') as file:
        file.write(f'''name: {WORKFLOW_NAME}
on:
  push:
    paths-ignore:
      - '{LAST_ZEPHYR_COMMIT_FILE}'
  schedule:
    - cron: '0 3 * * *'
  workflow_dispatch:
jobs:''')
        file.write("".join(tasks))

if __name__ == '__main__':
    generate()

