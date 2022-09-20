#!/usr/bin/env python
import matplotlib.pyplot as plt
import subprocess
import numpy as np
import os
import sys
import json
from colorama import init, Style

sample_names = ['hello_world', 'shell_module', 'philosophers', 'micropython', 'tensorflow_lite_micro']
zephyr_repo_path = "zephyrproject/zephyr"
result_path = "artifacts/{commit}/results-{sample_name}_all.json"
diff_file = 'artifacts/{commit}/diff-{sample_name}.json'
color_map = ["#F0902B", "#688FF0", "#B3BAB5"]


def bold(text):
    return Style.BRIGHT + (text or '') + Style.RESET_ALL


def check_revision(commit, revision=1):
    return subprocess.check_output(f"git -C {zephyr_repo_path} rev-parse --short {commit}~{revision}".split(" ")).decode().strip()

def sort_commits(commit):
    return len(subprocess.check_output(f"git -C {zephyr_repo_path} log --format='%h' {commit}..HEAD".split(" ")).decode().split("\n"))

def list_revisions():
    #revisions = [i for i in subprocess.check_output(f"gsutil ls gs://gcp-distributed-job-test-bucket".split(" ")).split("\n") if "job-artifacts" not in i]
    #for rev in revisions:
        #    subprocess.check_output(f"gsutil cp {rev} artifacts/".split(" "))
    revisions = ['gs://gcp-distributed-job-test-bucket/b11ba9ddc8/', 'gs://gcp-distributed-job-test-bucket/0d4ff38fa2/', 'gs://gcp-distributed-job-test-bucket/79f864028d/', 'gs://gcp-distributed-job-test-bucket/bf845a273b/']
    return sorted([i[-11:-1] for i in revisions], key=sort_commits, reverse=True)

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
            current_path = result_path.format(sample_name=sample, commit=current_rev)
            previous_path = result_path.format(sample_name=sample, commit=previous_rev)
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

def create_plots():
    for sample in sample_names:
        stats = {}
        revisions = list_revisions()
        for rev in revisions:
            path = result_path.format(sample_name=sample, commit=rev)
            if not os.path.exists(path):
                continue
            result_file = load_result_file(path)
            stats[rev] = {
                "passed": len([1 for i in result_file if i['status'] == 'PASSED']),
                "built": len([1 for i in result_file if i['status'] == 'BUILT']),
                "all": len(result_file)
            }
        if stats == {}:
            continue
        x = range(len(stats))
        ay = [stats[i]['built'] for i in stats]
        by = [stats[i]['passed'] for i in stats]
        cy = [stats[i]['all'] - stats[i]['built'] - stats[i]['passed'] for i in stats]

        ay = [250, 311, 315, 400]
        by = [100, 90, 50, 11]
        cy = [66, 10, 50, 0]

        print(f"passed: {ay}\nbuilt: {by}")
        _, ax = plt.subplots()
        #ax.stackplot(x, ay, by, cy, colors=color_map, labels=["Passed", "Built", "Not built"])
        ax.plot(x, ay, linewidth=2.0)
        ax.plot(x, by, linewidth=2.0)
        plt.xticks(range(len(revisions)), revisions, size='small', rotation='vertical')
        #plt.legend(loc="lower left")
        plt.legend(["Passed", "Built"], loc="lower left")
        plt.savefig(f"artifacts/{sample}.png", bbox_inches="tight")


if __name__ == '__main__':
    if len(sys.argv) <= 1:
        print("No commits passed!")
        exit(1)
    init()
    create_diff_file()
    create_plots()

