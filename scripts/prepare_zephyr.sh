#!/usr/bin/env bash
set -e
set -u
set -x

tar xf zephyr-artifact/zephyr.tar
pip install -r requirements.txt
cd zephyr-sdk
./setup.sh -t all -h -c
cd -
cd zephyrproject/zephyr
pip install -r scripts/requirements.txt 1>>../../artifacts/build.log 2>&1
cd -
rm -rf zephyr-artifact

