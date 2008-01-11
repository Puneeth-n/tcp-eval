#!/bin/bash

if [ "$1" = "--sendtoall" ]; then
    shift; kpid=$1; shift
    while read -rep "All systems> " line; do
        for x; do
            echo "Sending to [konsole-$kpid $x]."
            dcop konsole-$kpid $x sendSession "$line"
        done
    done
    exit 0
fi

case "$*" in
    group1)
        set host1 host2 gateway_host3 gateway_host4
        ;;
    group2)
        ssh -t gateway trapdoor
        set gateway_host{1,2,3,4}
        ;;
    ""|-*)
        echo "Usage: $0 host1 host2 host3 ..."
        echo "       $0 { group1 | group2 }"
        exit 1
        ;;
esac

konsole --script >/dev/null 2>&1 &
kpid=$!

echo -n "Waiting for konsole..."
while [ -z "$(dcop konsole-$kpid konsole currentSession 2> /dev/null)" ]; do
    echo -n "."; sleep 1
done; echo " done."

ctrl=$(dcop konsole-$kpid konsole currentSession)

i=0
for x; do
    v[i]=$(dcop konsole-$kpid konsole newSession)
    (( i++ ))
done

sleep 1

i=0
for x; do
    dcop konsole-$kpid ${v[i]} renameSession "${x##*_}"
    dcop konsole-$kpid ${v[i]} sendSession "exec ssh -t ${x//_/ ssh -t }"
    (( i++ ))
done

dcop konsole-$kpid $ctrl renameSession "Master"
dcop konsole-$kpid $ctrl sendSession "exec $( type -p $0 ) --sendtoall $kpid ${v[*]}"
