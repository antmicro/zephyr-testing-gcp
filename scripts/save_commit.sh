#!/bin/bash

for commit in "$@"; do
	if [ ! -z "${commit// }" ]; then
		echo $commit > last_zephyr_commit
		break
	fi
done
echo "::set-output name=LAST_ZEPHYR_COMMIT::$(cat last_zephyr_commit)"
