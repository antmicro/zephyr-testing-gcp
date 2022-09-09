#!/bin/bash

if [ $# > 0 -a ! -z "${1// }" ]; then
        echo $1 > last_zephyr_commit
fi

