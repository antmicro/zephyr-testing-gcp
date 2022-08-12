#!/bin/bash
mkdir -p artifacts/$1-$4
cd zephyrproject/zephyr

build_path="build.$1.$4"
rm -rf $build_path
RESULT=1

log_path="../../artifacts/$1-$4/$1-$4-zephyr.log"
west spdx --init -d $build_path | tee -a "$log_path"
west build --pristine -b $1 -d $build_path $2 $3 | tee -a "$log_path"
west spdx -d $build_path | tee -a "$log_path"
cd -

FILE_LIST=("zephyr/zephyr.elf" "zephyr/zephyr.dts" "zephyr/.config" "spdx/app.spdx" "spdx/build.spdx" "spdx/zephyr.spdx")

for fname in ${FILE_LIST[@]} ; do
    FILENAME="zephyrproject/zephyr/$build_path/$fname"
    BASENAME=${FILENAME##*/}
    if [ -e $FILENAME ] ; then
        if [[ "$fname" == "spdx/"* ]] ; then
            cp $FILENAME artifacts/$1-$4/$1-$4-$BASENAME
        fi
        if [[ "$fname" == "zephyr/.config" ]] ; then
            cp $FILENAME artifacts/$1-$4/$1-$4-config
        fi
        if [[ "$fname" == "zephyr/zephyr.elf" ]] ; then
            cp $FILENAME artifacts/$1-$4/$1-zephyr-$4.elf
            RESULT=0
        fi
        if [[ "$fname" == "zephyr/zephyr.dts" ]] ; then
            cp $FILENAME artifacts/$1-$4/$1-$4.dts

            # also copy dts without sample_name in it; this is done for legacy
            # purposes, and the dts for hello_world sample is the least likely
            # to be modified by our hacks
            if [[ "$4" == "hello_world" ]] ; then
                cp $FILENAME artifacts/$1.dts
            fi
        fi
    fi
done

rm -rf zephyrproject/zephyr/$build_path

exit $RESULT
