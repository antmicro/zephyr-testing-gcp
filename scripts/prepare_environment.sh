#!/usr/bin/env bash
set -e
set -u
set -x

mkdir -p artifacts/results
apt -qqy update
apt -qqy install software-properties-common
echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections
apt -qqy install curl git cmake ninja-build gperf ccache dfu-util device-tree-compiler wget python3-dev python3-pip python3-setuptools python3-tk python3-wheel xz-utils file make gcc gcc-multilib g++-multilib libsdl2-dev
pip3 install --upgrade pip
ls -la /usr/bin/pyth*
#update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1
