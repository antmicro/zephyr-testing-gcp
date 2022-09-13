#!/bin/bash

for commit in "$@"; do
	if [ ! -z "${commit// }" ]; then
        	echo $commit
		#echo $commit > last_zephyr_commit
		break
	fi
done
