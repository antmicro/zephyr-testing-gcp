#!/usr/bin/env python3
import itertools

WORKFLOW_FILE = 'workflow.yaml'
WORKFLOW_NAME = 'workflow'
SAMPLES = ['hello_world', 'shell_module', 'philosophers', 'micropython', 'tensorflow_lite_micro']
NUMBER_OF_THREADS_BUILD = 32
MAX_NUMBER_OF_COMMITS = 30
UBUNTU_VERSION = 'jammy'
ZEPHYR_SDK_VERSION = '0.15.0'
RENODE_VERSION = '1.13.1+20220918git57f09419'
LAST_ZEPHYR_COMMIT_FILE = 'last_zephyr_commit'

ENV = f'''
  ZEPHYR_SDK_VERSION: {ZEPHYR_SDK_VERSION}
  RENODE_VERSION: {RENODE_VERSION}
  MICROPYTHON_VERSION: 97a7cc243b
  GHA_SA: gh-sa-gcp-distributed-job-buck
  DEBIAN_FRONTEND: noninteractive
  TZ: Europe/Warsaw'''

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
    outputs:
      COMMIT_ALREADY_BUILT: ${{{{ steps.download-zephyr.outputs.COMMIT_ALREADY_BUILT }}}}
    steps:
    - uses: actions/checkout@v2
    - name: Prepare environment
      run: ./scripts/environment_prepare.sh
    - name: Download Zephyr
      id: download-zephyr
      run: ./scripts/download_zephyr.sh
    - name: Pass Zephyr as artifact
      if: steps.download-zephyr.outputs.COMMIT_ALREADY_BUILT == 'false'
      run: ./scripts/archive_zephyr.sh''')
    for zephyr_commit, sample in commit_sample_product:
        tasks.append(f'''
  build-{zephyr_commit}-{sample}:
    container: ubuntu:{UBUNTU_VERSION}
    runs-on: [self-hosted, Linux, X64]
    needs: [prepare-zephyr-{zephyr_commit}]
    if: needs.prepare-zephyr-{zephyr_commit}.outputs.COMMIT_ALREADY_BUILT == 'false'
    env:
      SAMPLE_NAME: {sample}
      NUMBER_OF_THREADS: {NUMBER_OF_THREADS_BUILD}
      GHA_MACHINE_TYPE: "n2-standard-32"
    steps:
    - uses: actions/checkout@v2
    - name: Prepare environment
      run: ./scripts/environment_build.sh
    - name: Get Zephyr
      run: gsutil cp gs://gcp-distributed-job-test-bucket/job-artifacts/prepare-zephyr-{zephyr_commit}/zephyr.tar.gz .
    - name: Prepare Zephyr
      run: ./scripts/prepare_zephyr.sh
    - name: Prepare Micropython
      run: ./scripts/prepare_micropython.sh
    - name: Build boards
      run: ./scripts/build.py
    - name: Upload load graphs
      uses: actions/upload-artifact@v2
      with:
        name: plots
        path: |
          **/plot_*.svg
    - name: Upload artifacts
      run: |
        mkdir -p job-artifacts/build-{zephyr_commit}-{sample}
        mv artifacts/ job-artifacts/build-{zephyr_commit}-{sample}
        gsutil -m cp -r job-artifacts/ gs://gcp-distributed-job-test-bucket''')
        tasks.append(f'''
  simulate-{zephyr_commit}-{sample}:
    container: ubuntu:{UBUNTU_VERSION}
    runs-on: [self-hosted, Linux, X64]
    needs: [build-{zephyr_commit}-{sample}]
    outputs:
      ZEPHYR_COMMIT: ${{{{ steps.get-zephyr-commit.outputs.ZEPHYR_COMMIT }}}}
    env:
      SAMPLE_NAME: {sample}
    steps:
    - uses: actions/checkout@v2
    - name: Prepare environment
      run: ./scripts/environment_simulate.sh
    - name: Get artifacts
      run: gsutil -m cp -r gs://gcp-distributed-job-test-bucket/job-artifacts/build-{zephyr_commit}-{sample}/artifacts .
    - name: Prepare Renode
      run: ./scripts/download_renode.sh
    - name: Simulate
      run: ./scripts/simulate.py
    - name: Get Zephyr commit
      id: get-zephyr-commit
      run: |
        ZEPHYR_COMMIT=$(cat artifacts/zephyr.version)
        echo "::set-output name=ZEPHYR_COMMIT::$ZEPHYR_COMMIT"
    - name: Upload load graphs
      uses: actions/upload-artifact@v2
      with:
        name: plots
        path: |
          **/plot_*.svg
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
    - name: Prepare environment
      run: ./scripts/environment_results.sh
    - name: Delete artifacts
      run: gsutil -m rm -r gs://gcp-distributed-job-test-bucket/job-artifacts
    - name: Gather results
      run: ./scripts/gather_results.py {' '.join([f'${{{{ needs.simulate-{commit}-hello_world.outputs.ZEPHYR_COMMIT }}}}' for commit in range(MAX_NUMBER_OF_COMMITS)])}
    - name: Update latest Zephyr commit
      id: update-last-zephyr-commit
      run: ./scripts/save_commit.sh {' '.join([f'${{{{ needs.simulate-{commit}-hello_world.outputs.ZEPHYR_COMMIT }}}}' for commit in range(MAX_NUMBER_OF_COMMITS)])}
    - name: Commit latest Zephyr commit
      uses: stefanzweifel/git-auto-commit-action@v4
      with:
        commit_message: Update latest Zephyr commit ${{{{ steps.update-last-zephyr-commit.outputs.LAST_ZEPHYR_COMMIT }}}}
        file_pattern: {LAST_ZEPHYR_COMMIT_FILE}''')
    print(f'''name: {WORKFLOW_NAME}
on:
  push:
    paths-ignore:
      - '{LAST_ZEPHYR_COMMIT_FILE}'
  schedule:
    - cron: '0 3 * * *'
  workflow_dispatch:
env:{ENV}
jobs:''')
    print("".join(tasks))

if __name__ == '__main__':
    generate()

