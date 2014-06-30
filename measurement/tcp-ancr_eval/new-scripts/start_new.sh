#!/bin/bash

USAGE="Usage: $0 [init|measure|analyze] [folder] <iterations>"


if [ "$1" = "init" ]; then
    if [ $# -lt 1 ]; then
        echo $USAGE
        exit 1
    fi
elif [ "$1" = "measure" ]; then
    if [ $# -lt 3 ]; then
        echo $USAGE
        exit 1
    fi
else
    if [ $# -lt 2 ]; then
        echo $USAGE
        exit 1
    fi
fi


#MEASUREMENTS="scenario-1 scenario-2 scenario-3 scenario-3-rd10 scenario-3-rd20 scenario-4 scenario-4-rd10 scenario-4-rd20 scenario-5 scenario-6 scenario-7 scenario-8 scenario-9 scenario-10"
#MEASUREMENTS="test"
MEASUREMENTS="scenario-1 scenario-2 scenario-3 scenario-3-rd10 scenario-3-rd20 scenario-4 scenario-4-rd10 scenario-4-rd20 scenario-5 scenario-6 scenario-7 scenario-8"



if [ "$1" = "init" ]; then
	echo -e "\nCreating topology\n=========================" | tee $LOG
    build-net /home/puneeth/test/reset_dumbbell.conf
fi

if [ "$1" = "measure" ]; then
    FOLDER=$2/$(date +%Y%m%d%H%M%S)
    LOG=$FOLDER/measurement-a.log
    ITR=$3
    ONE=1
    ABS=`pwd`
    echo -e "\n Requesting password for destination node. Might be needed if tcpdump is used\n"
    read -s -p "Enter Password: " PASSWD

    if [ -z "$PASSWD" ]; then
        echo -e "\nError: Password is invalid\n"
        exit 1
    fi
    ssh puneeth@192.168.5.1 "echo "$PASSWD"| sudo -S uname -a"

    mkdir $FOLDER
	echo -e "\nmeasurements\n=========================" | tee -a $LOG
    for i in `seq 1 $ITR`
    do
        for measurement in `echo $MEASUREMENTS`;
        do
            echo -e "----- measurement: $FOLDER/$measurement ------" | tee -a $LOG
            if [ $i -eq 1 ]; then
                mkdir $FOLDER/${measurement}
                echo -e "\nCreating Directory: $FOLDER/$measurement\n=========================" | tee -a $LOG | tee $FOLDER/${measurement}/${measurement}.log
            fi

            #reset topology
            build-net /home/puneeth/test/reset_dumbbell.conf

            #start measurement
            ~/Development/tcp-eval/measurement/tcp-ancr_eval/new-scripts/$measurement.py pair.conf --iterations $ONE --offset $i -l $FOLDER/${measurement} 2>&1 | tee -a $FOLDER/${measurement}/${measurement}.log
            ssh puneeth@192.168.5.1 "cd /tmp && nohup tar -czf ${measurement}-$i.tar.gz *.pcap"
            ssh puneeth@192.168.5.1 "echo "$PASSWD"| sudo -S rm /tmp/*.pcap"
            ssh puneeth@192.168.5.1 "mv /tmp/${measurement}-$i.tar.gz $ABS/$FOLDER/${measurement}"
        done
    done
fi

if [ "$1" = "analyze" ]; then
    FOLDER=$2
    LOG=$FOLDER/measurement-a.log
    ANALYSIS=~/bin/analyze
    db=data.sqlite
	echo -e "\ncreating pdf\n=========================" | tee -a $LOG
    cd $FOLDER
    ANALYZE= `ls -d *`
    cd -
    echo $ANALYZE
    exit 0
    for measurement in `echo $ANALYSIS`;
    do
        echo -e "----- analyze: $FOLDER/$measurement ------" | tee -a $LOG
	    cd $FOLDER/${measurement}
        #rm data.sqlite
#       echo -e "backing up old database into data.sqlite.old\n"
#       mv data.sqlite data.sqlite.old

        $ANALYSIS --debug -o test --save -t congestion -e bnbw

        $ANALYSIS --debug -o test --save -t congestion -e delay

        $ANALYSIS --debug -o test --save -t reordering -e rrate

        $ANALYSIS --debug -o test --save -t reordering -e rdelay

        $ANALYSIS --debug -o test --save -t reordering -e delay

        $ANALYSIS --debug -o test --save -t reordering -e ackloss

        $ANALYSIS --debug -o test --save -t reordering -e ackreor

        $ANALYSIS --debug -o test --save -t both -e bnbw

        $ANALYSIS --debug -o test --save -t both -e rrate

        $ANALYSIS --debug -o test --save -t both -e rdelay

        $ANALYSIS --debug -o test --save -t both -e delay

        $ANALYSIS --debug -o test --save -t both -e ackloss

        $ANALYSIS --debug -o test --save -t both -e ackreor

        cd -
    done
fi

if [ "$1" != "init" ] && [ "$1" != "measure" ] && [ "$1" != "analyze" ]; then
	echo $USAGE
fi
