#!/usr/bin/env bash
set -e
set -u
set -x

TARGET=$1
ARTIFACTS_DIR=$2

mkdir -p $ARTIFACTS_DIR

mv $TARGET $ARTIFACTS_DIR
gsutil -m cp -r "$(echo $ARTIFACTS_DIR | cut -d/ -f1)/" gs://gcp-distributed-job-test-bucket
