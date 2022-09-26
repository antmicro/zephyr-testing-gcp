#!/usr/bin/env python3
import subprocess
import os
import sys
import json
import matplotlib.pyplot as plt
import numpy as np
from colorama import init, Style

sample_names = ['hello_world', 'shell_module', 'philosophers', 'micropython', 'tensorflow_lite_micro']
zephyr_repo_path = "zephyr"
results_path = "results/{commit}"
results_sample_path = f"{results_path}/results-{{sample_name}}_all.json"
diff_file = f'{results_path}/diff-{{sample_name}}.json'
plot_data_file = f'{results_path}/plot-{{sample_name}}.json'
gcp_bucket = "gs://gcp-distributed-job-test-bucket"
color_map = ["#F0902B", "#688FF0", "#B3BAB5"]


def bold(text):
    return Style.BRIGHT + (text or '') + Style.RESET_ALL

def check_revision(commit, revision=1):
    return subprocess.check_output(f"git -C {zephyr_repo_path} rev-parse --short {commit}~{revision}".split(" ")).decode().strip()

def download_zephyr():
    try:
        subprocess.check_output(f"git clone https://github.com/zephyrproject-rtos/zephyr.git".split(" "))
    except subprocess.CalledProcessError:
        pass

def download_revisions(commit):
    os.makedirs(f"results/{commit}", exist_ok=True)
    try:
        subprocess.check_output(f"gsutil -q -m cp -r {gcp_bucket}/{commit}/results/* results/{commit}/".split(" "))
    except subprocess.CalledProcessError:
        pass

def sort_commits(commit):
    return len(subprocess.check_output(f"git -C {zephyr_repo_path} log --format='%h' {commit}..HEAD".split(" ")).decode().split("\n"))

def list_revisions():
    revisions = [i for i in subprocess.check_output(f"gsutil ls gs://gcp-distributed-job-test-bucket".split(" ")).decode().split("\n") if "job-artifacts" not in i and "plots" not in i and i != '']
    revisions = sorted([i[-11:-1] for i in revisions], key=sort_commits, reverse=True)
    for rev in revisions:
        download_revisions(rev)
    return revisions

def upload_file_to_gcp(file_to_upload, destination):
    try:
        subprocess.check_output(f"gsutil -q -m cp -r {file_to_upload} {gcp_bucket}/{destination}".split(" "))
    except subprocess.CalledProcessError:
        pass

def load_result_file(file_path):
    with open(file_path) as file:
        result = json.loads(file.read())
    return [{"name": i["board_name"], "status": i["status"]} for i in result]

def create_diff_file():
    for commit in sys.argv[1:]:
        current_rev = check_revision(commit, 0)
        previous_rev = check_revision(commit, 1)
        for sample in sample_names:
            print(f"\nCommit: {commit}, Sample: {sample}")
            changed = 0
            current_path = results_sample_path.format(sample_name=sample, commit=current_rev)
            previous_path = results_sample_path.format(sample_name=sample, commit=previous_rev)
            if not os.path.exists(current_path) or not os.path.exists(previous_path):
                print("------ SKIPPED ------")
                continue
            current_result = load_result_file(current_path)
            previous_result = load_result_file(previous_path)
            diff = []
            for result in current_result:
                elem_status = next((res for res in previous_result if res['name'] == result['name']), None)
                elem_status = elem_status["status"] if elem_status is not None else "NONE"
                changed += result['status'] != elem_status
                diff.append({"name": result["name"], "previous": elem_status, "current": result["status"] })
                print(f"{bold(result['name'])}: {elem_status} -> {result['status']}")
            print(f"\nChanged: {changed}/{len(current_result)}")
            with open(diff_file.format(sample_name=sample, commit=commit), "w") as file:
                file.write(json.dumps(diff))
            upload_file_to_gcp(diff_file.format(sample_name=sample, commit=commit), f'{commit}/results/')

def create_plot_data():
    for sample in sample_names:
        for rev in sys.argv[1:]:
            path = results_sample_path.format(sample_name=sample, commit=rev)
            if not os.path.exists(path):
                continue
            result_file = load_result_file(path)
            stats = {
                "all": len(result_file),
                "built": len([1 for i in result_file if i['status'] == 'BUILT' or i['status'] == 'PASSED']),
                "passed": len([1 for i in result_file if i['status'] == 'PASSED']),
            }
            with open(plot_data_file.format(sample_name=sample, commit=rev), 'w') as file:
                file.write(json.dumps(stats))
            upload_file_to_gcp(plot_data_file.format(sample_name=sample, commit=rev), f'{rev}/results/')

def create_plot():
    revisions = list_revisions()
    for sample in sample_names:
        stats = {}
        current_revisions = []
        for rev in revisions:
            path = results_sample_path.format(sample_name=sample, commit=rev)
            if not os.path.exists(path):
                continue
            result_file = load_result_file(path)
            stats[rev] = {
                "passed": len([1 for i in result_file if i['status'] == 'PASSED']),
                "built": len([1 for i in result_file if i['status'] == 'BUILT']),
                "all": len(result_file)
            }
            current_revisions.append(rev)
        if stats == {}:
            continue
        ay = np.array([stats[i]['built'] for i in stats])
        by = np.array([stats[i]['passed'] for i in stats])
        cy = np.array([stats[i]['all'] - stats[i]['built'] - stats[i]['passed'] for i in stats])

        _, ax = plt.subplots()
        ax.bar(current_revisions, ay, 0.35, color=color_map[0])
        ax.bar(current_revisions, by, 0.35, bottom=ay, color=color_map[1])
        ax.bar(current_revisions, cy, 0.35, bottom=ay+by, color=color_map[2])
        plt.xticks(range(len(revisions)), revisions, size='small', rotation='vertical')
        plt.legend(["Built", "Passed", "Not built"], loc="lower left")
        plt.savefig(f"plots/{current_revisions[-1]}-{sample}.png", bbox_inches="tight")
    upload_file_to_gcp("plots/", "")


if __name__ == '__main__':
    if len(sys.argv) <= 1:
        print("No commits passed!")
        exit(1)
    init()
    download_zephyr()
    for rev in sys.argv[1:]:
        download_revisions(rev)
    create_diff_file()
    create_plot_data()
    create_plot()

