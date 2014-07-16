#!/bin/bash
USAGE="Usage: $0 duration log-folder"

if [ $# -lt 2 ]; then
    echo $USAGE
    exit 1
fi

DURATION=$1
FOLDER=$2

./test.py pair.conf -l $FOLDER -o 0 -i 1 -t $DURATION
