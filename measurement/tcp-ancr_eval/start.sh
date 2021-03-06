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


#MEASUREMENTS="scenario-2 scenario-3 scenario-3-rd10 scenario-3-rd20 scenario-4 scenario-4-rd10 scenario-4-rd20 scenario-5 scenario-6 scenario-7 scenario-8 scenario-9 scenario-10 scenario-1"
MEASUREMENTS="scenario-5 scenario-6 scenario-7 scenario-8 scenario-9 scenario-10 scenario-1"



if [ "$1" = "init" ]; then
	echo -e "\nCreating topology\n=========================" | tee $LOG
    build-net /home/puneeth/test/reset_dumbbell.conf
fi

if [ "$1" = "measure" ]; then
    FOLDER=$2/$(date +%Y%m%d%H%M%S)
    LOG=$FOLDER/measurement-a.log
    ITR=$3
    ONE=1
    mkdir $FOLDER
	echo -e "\nmeasurements\n=========================" | tee -a $LOG
#    for i in {1..$ITR}
#    do
        for measurement in `echo $MEASUREMENTS`;
        do
            echo -e "----- measurement: $FOLDER/$measurement ------" | tee -a $LOG
            mkdir $FOLDER/${measurement}
            #reset topology
            build-net /home/puneeth/test/reset_dumbbell.conf
#            ~/Development/tcp-eval/measurement/tcp-ancr_eval/$measurement.py pair.conf --iterations $ONE -l $FOLDER/${measurement} 2>&1 | tee -a $FOLDER/${measurement}/${measurement}.log
            ~/Development/tcp-eval/measurement/tcp-ancr_eval/$measurement.py pair.conf --iterations $ITR -l $FOLDER/${measurement} 2>&1 | tee -a $FOLDER/${measurement}/${measurement}.log
            #ssh puneeth@192.168.5.1 "cd /tmp && nohup tar -czvf ${measurement}.tar.gz *.pcap && cd - && cp /tmp/${measurement}.tar.gz $FOLDER/${measurement}"
            ssh puneeth@192.168.5.1 "cd /tmp && nohup tar -czvf ${measurement}.tar.gz *.pcap && rm *.pcap"
        done
#    done
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
