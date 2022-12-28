#!/usr/bin/env python
import itertools

WORKFLOW_FILE = 'workflow.yaml'
WORKFLOW_NAME = 'workflow'
SAMPLES = ['hello_world', 'shell_module', 'philosophers', 'micropython', 'tensorflow_lite_micro']
NUMBER_OF_THREADS_BUILD = 32
NUMBER_OF_THREADS_SIMULATE = 28
MAX_NUMBER_OF_COMMITS = 30
UBUNTU_VERSION = 'jammy'
ZEPHYR_SDK_VERSION = '0.15.0'
RENODE_VERSION = '1.13.1+20220909git3e7a1aa7'
LAST_ZEPHYR_COMMIT_FILE = 'last_zephyr_commit'

def generate():
    commit_sample_product = list(itertools.product(range(MAX_NUMBER_OF_COMMITS), SAMPLES))
    tasks = []
    for zephyr_commit in range(MAX_NUMBER_OF_COMMITS):
        tasks.append(f'''
  prepare-zephyr-{zephyr_commit}:
    container: ubuntu:{UBUNTU_VERSION}
    runs-on: [self-hosted, Linux, X64]
    env:
      ZEPHYR_COMMIT: {zephyr_commit}
      ZEPHYR_SDK_VERSION: {ZEPHYR_SDK_VERSION}
      GHA_SA: "gh-sa-gcp-distributed-job-buck"
    steps:
    - uses: actions/checkout@v2
    - name: Prepare environment
      run: ./scripts/environment_prepare.sh
    - name: Download Zephyr
      run: ./scripts/download_zephyr.sh
    - name: Pass Zephyr as artifact
      if: env.SKIP != 'true'
      run: ./scripts/save_artifacts.sh zephyr.tar.gz job-artifacts/prepare-zephyr-{zephyr_commit}''')
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
      GHA_SA: "gh-sa-gcp-distributed-job-buck"
    steps:
    - uses: actions/checkout@v2
    - name: Prepare environment
      run: ./scripts/environment_build.sh
    - name: Check for skip
      run: ./scripts/check_for_skip.sh {zephyr_commit}
    - name: Get Zephyr
      if: env.SKIP != 'true'
      run: gsutil cp gs://gcp-distributed-job-test-bucket/job-artifacts/prepare-zephyr-{zephyr_commit}/zephyr.tar.gz .
    - name: Prepare Zephyr
      if: env.SKIP != 'true'
      run: ./scripts/prepare_zephyr.sh
    - name: Prepare Micropython
      if: env.SKIP != 'true'
      run: ./scripts/prepare_micropython.sh
    - name: Build boards
      if: env.SKIP != 'true'
      run: ./scripts/build.py
    - name: Upload load graphs
      if: env.SKIP != 'true'
      uses: actions/upload-artifact@v2
      with:
        name: plots
        path: |
          **/plot_*.svg
    - name: Upload artifacts
      if: env.SKIP != 'true'
      run: ./scripts/save_artifacts.sh artifacts/ job-artifacts/build-{zephyr_commit}-{sample}''')
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
    - name: Prepare environment
      run: ./scripts/environment_simulate.sh
    - name: Check for skip
      run: ./scripts/check_for_skip.sh {zephyr_commit}
    - name: Get artifacts
      if: env.SKIP != 'true'
      run: gsutil -m cp -r gs://gcp-distributed-job-test-bucket/job-artifacts/build-{zephyr_commit}-{sample}/artifacts .
    - name: Prepare Renode
      if: env.SKIP != 'true'
      run: ./scripts/download_renode.sh
    - name: Simulate
      if: env.SKIP != 'true'
      run: ./scripts/simulate.py
    - name: Get Zephyr commit
      if: env.SKIP != 'true'
      id: get-zephyr-commit
      run: |
        ZEPHYR_COMMIT=$(cat artifacts/zephyr.version)
        echo "::set-output name=ZEPHYR_COMMIT::$ZEPHYR_COMMIT"
    - name: Upload load graphs
      if: env.SKIP != 'true'
      uses: actions/upload-artifact@v2
      with:
        name: plots
        path: |
          **/plot_*.svg
    - name: Upload artifacts
      if: env.SKIP != 'true'
      run: ./scripts/save_artifacts.sh artifacts/ ${{{{ steps.get-zephyr-commit.outputs.ZEPHYR_COMMIT }}}}''')
    tasks.append(f'''
  results:
    container: ubuntu:{UBUNTU_VERSION}
    runs-on: [self-hosted, Linux, X64]
    needs: [{", ".join([f'simulate-{zephyr_commit}-{sample}' for zephyr_commit, sample in commit_sample_product])}]
    env:
      GHA_SA: "gh-sa-gcp-distributed-job-buck"
      DEBIAN_FRONTEND: noninteractive
      TZ: Europe/Warsaw
    if: always()
    steps:
    - uses: actions/checkout@v2
    - name: Install gcp
      run: ./scripts/prepare_gcp.sh
    - name: Delete artifacts
      run: ./scripts/delete_artifacts.sh
    - name: Update latest Zephyr commit
      id: update-last-zephyr-commit
      run: |
        ./scripts/save_commit.sh {' '.join([f'${{{{ needs.simulate-{commit}-{sample}.outputs.ZEPHYR_COMMIT }}}}' for commit, sample in commit_sample_product])}
        echo "::set-output name=LAST_ZEPHYR_COMMIT::$(cat last_zephyr_commit)"
    - name: Commit latest Zephyr commit
      uses: stefanzweifel/git-auto-commit-action@v4
      with:
        commit_message: Update latest Zephyr commit ${{{{ steps.update-last-zephyr-commit.outputs.LAST_ZEPHYR_COMMIT }}}}
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

