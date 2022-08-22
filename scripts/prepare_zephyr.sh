#!/usr/bin/env bash
set -e
set -u
set -x

tar xf zephyr-artifact/zephyrproject.tar
pip3 install -r requirements.txt
cd zephyr-sdk
./setup.sh -t all -h -c
cd -
rm -rf zephyr-artifact

