#!/usr/bin/env bash
set -u
set -x

gsutil -m rm -r gs://gcp-distributed-job-test-bucket/skip-artifacts || true
gsutil -m rm -r gs://gcp-distributed-job-test-bucket/job-artifacts || true

exit 0
