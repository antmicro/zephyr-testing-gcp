#!/usr/bin/env python
import itertools
from git.repo import Repo
from git.exc import NoSuchPathError

WORKFLOW_FILE = 'workflow.yaml'
WORKFLOW_NAME = 'workflow'
SAMPLES = ['hello_world', 'shell_module', 'philosophers', 'micropython', 'tensorflow_lite_micro']
SAMPLES = ['hello_world', 'shell_module'] # test

def get_zephyr_commits(first_commit, commit_num):
    try:
        repo = Repo("zephyrproject/zephyr")
        repo.remotes.origin.fetch()
    except NoSuchPathError:
        repo = Repo.clone_from("https://github.com/zephyrproject-rtos/zephyr.git", "zephyr")
    return [repo.commit(f"{first_commit}~{i}").hexsha[:10] for i in range(commit_num)]

def generate():
    zephyr_commits = get_zephyr_commits("6cfb18686e", 2)
    commit_sample_product = list(itertools.product(zephyr_commits, SAMPLES))
    tasks = []
    for zephyr_commit in zephyr_commits:
        tasks.append(f'''
  prepare-zephyr-{zephyr_commit}:
    runs-on: ubuntu-20.04
    env:
      ZEPHYR_COMMIT: {zephyr_commit}
      ZEPHYR_SDK_VERSION: 0.14.2
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
        path: zephyrproject.tar''')
    for zephyr_commit, sample in commit_sample_product:
        tasks.append(f'''
  build-{zephyr_commit}-{sample}:
    runs-on: ubuntu-20.04
    needs: [prepare-zephyr-{zephyr_commit}]
    env:
      ZEPHYR_COMMIT: {zephyr_commit}
      SAMPLE_NAME: {sample}
    steps:
    - name: Get Zephyr
      uses: actions/download-artifact@v2
      with:
        name: zephyr-{zephyr_commit}
        path: zephyr-artifact
    - name: Test
      run: ls -la zephyr-artifact''')
        tasks.append(f'''
  simulate-{zephyr_commit}-{sample}:
    runs-on: ubuntu-20.04
    needs: [build-{zephyr_commit}-{sample}]
    env:
       SAMPLE_NAME: {sample}
    steps:
    - name: Test simulate
      run: echo $SAMPLE_NAME''')
    with open(WORKFLOW_FILE, 'w') as file:
        file.write(f"name: {WORKFLOW_NAME}\n")
        file.write("on: [push]\n\n")
        file.write("jobs:")
        file.write("".join(tasks))
        file.write(f'''
  results:
    runs-on: ubuntu-20.04
    needs: [{", ".join([f'simulate-{zephyr_commit}-{sample}' for zephyr_commit, sample in commit_sample_product])}]
    steps:
    - name: Test results
      run: echo "Working!!"''')

if __name__ == '__main__':
    generate()

