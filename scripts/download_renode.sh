#!/bin/bash

mkdir -p renode_portable && cd renode_portable
curl -kL https://dl.antmicro.com/projects/renode/builds/renode-${RENODE_VERSION}.linux-portable.tar.gz | tar xz --strip 1
ln -s ../artifacts artifacts
#export PATH=`pwd`:$PATH
cd -
ls -la ronode_portable/
