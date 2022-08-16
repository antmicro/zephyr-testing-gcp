#!/bin/bash

mkdir -p renode_portable && cd renode_portable
curl -kL https://dl.antmicro.com/projects/renode/builds/renode-${RENODE_VERSION}.linux-portable.tar.gz | tar xz --strip 1
pip3 install -r tests/requirements.txt
ln -s ../artifacts artifacts
echo `pwd` >> $GITHUB_PATH
cd -
