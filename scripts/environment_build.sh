#!/usr/bin/env bash
set -e
set -u
set -x

apt -qqy update
echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections
apt -qqy install git cmake wget ninja-build python3-dev python3-pip python3-setuptools python3-tk python3-wheel xz-utils file make
pip3 install --upgrade pip
pip3 install -r requirements_build.txt
