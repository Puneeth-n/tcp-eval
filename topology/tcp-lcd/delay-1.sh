#!/bin/bash

#
#    100M, 2ms                                                                            100M, 3ms
# K1------------                                                                        ------------ K2
#    100M, 5ms |                                                                        | 100M,10ms
# K3------------      100M       100M       2M          2M        100M       100M       ------------ K4
#    100M,20ms |- K9 ------ K10 ------ K11 ------ K12 ------ K13 ------ K14 ------ K15 -| 100M,20ms
# K5------------ delay     loss      reorder     limit     reorder     loss       delay ------------ K6
#    100M,20ms |  -->       -->        -->        <->        <--        <--        <--  | 100M,20ms
# K7------------                                  7,7                                   ------------ K8
#

# für K9
#------------------

# --------- CHANGE HERE ------------
VMROUTER1=vmrouter281
VMROUTER3=vmrouter283
VMROUTER5=vmrouter285
VMROUTER7=vmrouter287
# ----------------------------------

#alle filter entfernen
tc filter del dev eth0 parent 1: prio 16

#richtige wieder hinzufügen
IPVMROUTER1=`host $VMROUTER1 | cut -d' ' -f4`
IPVMROUTER3=`host $VMROUTER3 | cut -d' ' -f4`
IPVMROUTER5=`host $VMROUTER5 | cut -d' ' -f4`
IPVMROUTER7=`host $VMROUTER7 | cut -d' ' -f4`

tc filter add dev eth0 parent 1: protocol ip prio 16 u32  match ip protocol 47 0xff flowid 1:1  match ip dst $IPVMROUTER1
tc filter add dev eth0 parent 1: protocol ip prio 16 u32  match ip protocol 47 0xff flowid 1:2  match ip dst $IPVMROUTER3
tc filter add dev eth0 parent 1: protocol ip prio 16 u32  match ip protocol 47 0xff flowid 1:3  match ip dst $IPVMROUTER5
tc filter add dev eth0 parent 1: protocol ip prio 16 u32  match ip protocol 47 0xff flowid 1:4  match ip dst $IPVMROUTER7

#zusätzliche queues/classes für src abhängiges delay
tc class add dev eth0 parent 1: classid 1:51 htb rate 100Mbit
tc class add dev eth0 parent 1: classid 1:52 htb rate 100Mbit
tc class add dev eth0 parent 1: classid 1:53 htb rate 100Mbit
tc class add dev eth0 parent 1: classid 1:54 htb rate 100Mbit

tc qdisc add dev eth0 parent 1:51 handle 51: netem delay 2ms
tc qdisc add dev eth0 parent 1:52 handle 52: netem delay 5ms
tc qdisc add dev eth0 parent 1:53 handle 53: netem delay 20ms
tc qdisc add dev eth0 parent 1:54 handle 54: netem delay 20ms

tc qdisc add dev eth0 parent 51:1 pfifo limit 1000
tc qdisc add dev eth0 parent 52:1 pfifo limit 1000
tc qdisc add dev eth0 parent 53:1 pfifo limit 1000
tc qdisc add dev eth0 parent 54:1 pfifo limit 1000

#filter für die marks
tc filter add dev eth0 protocol ip parent 1: prio 1 handle 1 fw flowid 1:51
tc filter add dev eth0 protocol ip parent 1: prio 1 handle 3 fw flowid 1:52
tc filter add dev eth0 protocol ip parent 1: prio 1 handle 5 fw flowid 1:53
tc filter add dev eth0 protocol ip parent 1: prio 1 handle 7 fw flowid 1:54

#iptables netfilter MARKs
iptables -F PREROUTING -t mangle

iptables -A PREROUTING -t mangle -s $VMROUTER1 -j MARK --set-mark 1
iptables -A PREROUTING -t mangle -s $VMROUTER3 -j MARK --set-mark 3
iptables -A PREROUTING -t mangle -s $VMROUTER5 -j MARK --set-mark 5
iptables -A PREROUTING -t mangle -s $VMROUTER7 -j MARK --set-mark 7
