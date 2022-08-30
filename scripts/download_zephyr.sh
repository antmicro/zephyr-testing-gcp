#!/usr/bin/env bash
set -e
set -u
set -x

pip3 install west
west init zephyrproject

mkdir -p zephyr-sdk && cd zephyr-sdk
curl -kL https://dl.antmicro.com/projects/renode/zephyr-sdk-${ZEPHYR_SDK_VERSION}_linux-x86_64.tar.gz | tar xz --strip 1
./setup.sh -t all -h -c
cd -
HEAD=8c55073d59
LAST_COMMIT=$(cat last_zephyr_commit)
COMMITS=$(git -C zephyrproject/zephyr log --pretty=format:'%h' $LAST_COMMIT..$HEAD)

cd zephyrproject/zephyr
CURRENT_COMMIT=$(git rev-parse --short $HEAD~${ZEPHYR_COMMIT})
if [[ ! " ${COMMITS[*]} " =~ $CURRENT_COMMIT ]]; then
	echo "Commit has already been built"
	exit 1
fi
git checkout $CURRENT_COMMIT
git apply ../../patches/zephyr/*.patch
pip3 install -r scripts/requirements.txt
cd ..
for i in $(seq 1 5); do west update 1>>../artifacts/build.log 2>&1 && break || sleep 5; done
west espressif install 1>>../artifacts/build.log 2>&1
cd ..

tar czf zephyr.tar.gz zephyrproject zephyr-sdk
