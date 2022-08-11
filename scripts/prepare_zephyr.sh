tar xvf zephyr.tar
mkdir -p zephyr-sdk && cd zephyr-sdk
curl -kL --no-progress-meter https://dl.antmicro.com/projects/renode/zephyr-sdk-${ZEPHYR_SDK_VERSION}_linux-x86_64.tar.gz | tar xz --strip 1
./setup.sh -t all -h -c
cd -
export ZEPHYR_SDK_INSTALL_DIR=$(pwd)/zephyr-sdk
pip3 install --user -U west

pip uninstall -y devicetree
west init zephyrproject # 1>artifacts/build.log 2>&1
cd zephyrproject/zephyr
git checkout ${ZEPHYR_COMMIT}
echo "[+] Git Apply"
git apply ../../patches/zephyr/*.patch
echo "[+] pip3 install reqs"
pip3 install -r scripts/requirements.txt 1>>../../artifacts/build.log 2>&1
cd scripts/dts/python-devicetree
echo "[+] python setup"
sudo python3 setup.py install
cd ../../../../
echo "[+] west update"
for i in $(seq 1 5); do west update 1>>../artifacts/build.log 2>&1 && break || sleep 5; done
echo "[+] west espressif"
west espressif install 1>>../artifacts/build.log 2>&1
cd ..

