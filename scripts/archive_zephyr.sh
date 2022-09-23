#!/usr/bin/env bash
set -u
set -e
set -x

mkdir -p job-artifacts/prepare-zephyr-${ZEPHYR_COMMIT}
mv zephyr.tar.gz job-artifacts/prepare-zephyr-${ZEPHYR_COMMIT}/
gsutil -m cp -r job-artifacts/ gs://gcp-distributed-job-test-bucket
