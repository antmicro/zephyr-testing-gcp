#!/usr/bin/env bash
set -e
set -u
set -x

mkdir -p artifacts/results
apt -qqy update
echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections
apt -qqy install curl git cmake ninja-build gperf ccache dfu-util device-tree-compiler wget python3-dev python3-pip python3-setuptools python3-tk python3-wheel xz-utils file make gcc gcc-multilib g++-multilib libsdl2-dev
pip3 install scikit-build
pip3 install setuptools_scm
