#!/usr/bin/env bash
set -e
set -u
set -x

git clone https://github.com/micropython/micropython
cd micropython
git checkout ${MICROPYTHON_VERSION}
git apply ../patches/micropython/*.patch
cd ..
