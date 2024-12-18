#!/usr/bin/env bash

# Copy *.md files from docs/ if it doesn't have a Chinese translation

for filename in $(find ../en/ -name '*.md' -printf "%P\n");
do
    mkdir -p $(dirname $filename)
    cp -n ../en/$filename ./$filename
    cp -n ../../README_zh.md ./copy_quickstart.md
    cp -n ../../evaluation/README_zh.md ./copy_precision.md
done
