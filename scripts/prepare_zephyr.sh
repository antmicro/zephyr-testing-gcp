#!/usr/bin/env bash
set -e
set -u
set -x

pip3 install -r requirements.txt
mkdir -p zephyr-sdk && cd zephyr-sdk
curl -kL https://dl.antmicro.com/projects/renode/zephyr-sdk-${ZEPHYR_SDK_VERSION}_linux-x86_64.tar.gz | tar xz --strip 1
./setup.sh -t all -h -c
cd -
export ZEPHYR_SDK_INSTALL_DIR=$(pwd)/zephyr-sdk

tar xvf zephyr-artifact/zephyrproject.tar
rm -rf zephyr-artifact
cd zephyrproject/zephyr
git checkout ${ZEPHYR_COMMIT}
git apply ../../patches/zephyr/*.patch
pip3 install -r scripts/requirements.txt 1>>../../artifacts/build.log 2>&1
cd ../
for i in $(seq 1 5); do west update 1>>../artifacts/build.log 2>&1 && break || sleep 5; done
west espressif install 1>>../artifacts/build.log 2>&1
cd ..

