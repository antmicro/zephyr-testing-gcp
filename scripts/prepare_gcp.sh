#!/usr/bin/env bash
set -e
set -u
set -x

apt -qqy update
apt -qqy install curl gnupg
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
curl --fail-with-body --retry 5 https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
apt -qqy update && apt -qqy install google-cloud-cli
