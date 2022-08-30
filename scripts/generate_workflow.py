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
      NUMBER_OF_THREADS: {NUMBER_OF_THREADS}
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
    - name: Echo Zephyr commit
      run: cat artifacts/zephyr.version
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
    outputs:
      ZEPHYR_COMMIT: ${{{{ steps.get-zephyr-commit.outputs.ZEPHYR_COMMIT }}}}
    env:
      SAMPLE_NAME: {sample}
      RENODE_VERSION: {RENODE_VERSION}
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
        name: build-{zephyr_commit}
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
        echo $ZEPHYR_COMMIT
        echo "::set-output name=ZEPHYR_COMMIT::$ZEPHYR_COMMIT"
    - name: Debug zephyr_commit
      run: echo ${{{{ steps.get-zephyr-commit.outputs.ZEPHYR_COMMIT }}}}
    - name: Upload artifacts
      uses: actions/upload-artifact@v2
      with:
        name: ${{{{ steps.get-zephyr-commit.outputs.ZEPHYR_COMMIT }}}}
        path: artifacts/''')
    tasks.append(f'''
  results:
    container: ubuntu:{UBUNTU_VERSION}
    runs-on: [self-hosted, Linux, X64]
    needs: [{", ".join([f'simulate-{zephyr_commit}-{sample}' for zephyr_commit, sample in commit_sample_product])}]
    if: always()
    env:
      GHA_SA: "gh-sa-gcp-distributed-job-buck"
    steps:
    - uses: actions/checkout@v2
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
        echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
        curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
        apt -qqy update && apt -qqy install google-cloud-cli
    - name: Upload artifacts
      run: gsutil cp -r results/* gs://gcp-distributed-job-test-bucket
    - name: Delete the rest of the artifacts
      uses: geekyeggo/delete-artifact@v1
      with:
        name: |
          {newline.join([f"${{{{ needs.simulate-{i}-hello_world.outputs.ZEPHYR_COMMIT }}}}" for i in range(MAX_NUMBER_OF_COMMITS)])}
    - name: Update latest Zephyr commit
      run: echo ${{{{ needs.simulate-0-hello_world.outputs.ZEPHYR_COMMIT }}}} > {LAST_ZEPHYR_COMMIT_FILE}
    - name: Commit latest Zephyr commit
      uses: stefanzweifel/git-auto-commit-action@v4
      with:
        commit_message: Update latest Zephyr commit
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

