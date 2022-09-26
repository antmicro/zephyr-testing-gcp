#!/usr/bin/env bash
set -e
set -u
set -x

apt -qqy update
echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections
apt -qqy install curl gnupg git cmake wget python3-dev python3-pip python3-setuptools python3-tk python3-wheel
pip3 install --upgrade pip
pip3 install -r requirements_results.txt
${BASH_SOURCE%/*}/prepare_gcp.sh
mkdir plots
