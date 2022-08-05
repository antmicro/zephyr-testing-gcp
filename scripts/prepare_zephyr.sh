pip uninstall -y devicetree
west init zephyrproject # 1>artifacts/build.log 2>&1
cd zephyrproject/zephyr
git checkout ${ZEPHYR_VERSION}
git apply ../../patches/zephyr/*.patch
pip3 install -r scripts/requirements.txt 1>>../../artifacts/build.log 2>&1
cd scripts/dts/python-devicetree
python3 setup.py install
cd ../../../../
for i in $(seq 1 5); do west update 1>>../artifacts/build.log 2>&1 && break || sleep 5; done
west espressif install 1>>../artifacts/build.log 2>&1
cd ..

