#!/usr/bin/env bash
set -e
set -u
set -x

tar xzf zephyr-artifact/zephyr.tar.gz
pip3 install -r requirements_build.txt
cd zephyr-sdk
./setup.sh -t all -h -c
cd -
cd zephyrproject/zephyr
pip3 install -r scripts/requirements.txt 1>>../../artifacts/build.log 2>&1
cd -
rm -rf zephyr-artifact

