#!/usr/bin/env bash
set -u
set -x

if gsutil stat gs://gcp-distributed-job-test-bucket/skip-artifacts/commit_skipped-$1; then
    echo "SKIP=true" >> "$GITHUB_ENV";
fi
exit 0
