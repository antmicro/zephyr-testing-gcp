#!/usr/bin/env bash
set -e
set -u
set -x

mkdir -p artifacts/results
apt -qqy update
echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections
apt -qqy install curl gnupg git python3-dev python3-pip python3-setuptools python3-tk python3-wheel
${BASH_SOURCE%/*}/prepare_gcp.sh
pip3 install --upgrade pip
pip3 install -r requirements_simulate.txt
