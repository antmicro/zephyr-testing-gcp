#!/usr/bin/env bash
set -e
set -u
set -x

mkdir -p artifacts/results
apt -qqy update
apt -qqy install curl gnupg
echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
apt -qqy update
apt -qqy install git python3-dev python3-pip python3-setuptools python3-tk python3-wheel google-cloud-cli
pip3 install --upgrade pip
pip3 install -r requirements_simulate.txt
