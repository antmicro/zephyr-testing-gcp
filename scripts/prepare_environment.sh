#!/bin/bash

mkdir -p artifacts
sudo apt -qqy update > /dev/null 2> /dev/null
sudo echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections
sudo apt -qqy install curl git cmake ninja-build gperf ccache dfu-util device-tree-compiler wget python3-dev python3-pip python3-setuptools python3-tk python3-wheel xz-utils file make gcc gcc-multilib g++-multilib libsdl2-dev 1>/dev/null 2>/dev/null
pip3 install -qr requirements.txt
export PATH=$HOME/.local/bin:"$PATH"
sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.8 1

