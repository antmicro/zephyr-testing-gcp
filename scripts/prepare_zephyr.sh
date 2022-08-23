#!/usr/bin/env bash
set -e
set -u
set -x

tar xf zephyr-artifact/zephyr.tar
pip3 install -r requirements.txt
cd zephyr-sdk
./setup.sh -t all -h -c
cd -
cd zephyrproject/zephyr
pip3 install -r scripts/requirements.txt 1>>../../artifacts/build.log 2>&1
cd -
rm -rf zephyr-artifact

