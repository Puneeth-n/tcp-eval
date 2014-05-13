#!/bin/bash

USAGE="Usage: $0 [init|measure|analyze] [folder] [offset]"

if [ $# -lt 3 ]; then
    echo $USAGE
    exit 1
fi
FOLDER=$2
OFFSET=$3
LOG=$FOLDER/measurement-a.log

#MEASUREMENTS="scenario-1 scenario-2 scenario-3 scenario-3-rd10 scenario-3-rd20 scenario-4 scenario-4-rd10 scenario-4-rd20 scenario-5 scenario-6 scenario-7 scenario-8 scenario-9 scenario-10"


MEASUREMENTS="scenario-10"
#scenario-1
#scenario-2
#scenario-3
#scenario-3-rd10
#scenario-3-rd20
#scenario-4
#scenario-4-rd10
#scenario-4-rd20
#scenario-5
#scenario-6
#scenario-7
#scenario-8
#scenario-9
#scenario-10

if [ "$1" = "init" ]; then
	echo -e "starting vmrouter\n=========================" | tee $LOG
	./config/start_dumbbell.pl restart $OFFSET | tee -a $LOG
	echo -e "\nexecuting um_vmesh\n=========================" | tee -a $LOG
	um_vmesh -u -s -q -o $OFFSET config/dumbbell.conf 2>&1 | tee -a $LOG
fi

if [ "$1" = "measure" ]; then
	echo -e "\nmeasurements\n=========================" | tee -a $LOG
    for measurement in `echo $MEASUREMENTS`;
    do
        echo -e "----- measurement: $FOLDER/$measurement ------" | tee -a $LOG
	    ./config/$measurement.py -o $OFFSET -L $FOLDER/${measurement} 2>&1 | tee -a $LOG
    done
fi

if [ "$1" = "analyze" ]; then
	echo -e "\ncreating pdf\n=========================" | tee -a $LOG
    ANALYSIS=~/bin/tcp-ancr
    db=data.sqlite
    for measurement in `echo $MEASUREMENTS`;
    do
        echo -e "----- analyze: $FOLDER/$measurement ------" | tee -a $LOG
	    cd $FOLDER/${measurement}
        #rm data.sqlite
#       echo -e "backing up old database into data.sqlite.old\n"
#       mv data.sqlite data.sqlite.old
#	    $ANALYSIS -V bnbw    -T congestion -O pdf -E
        $ANALYSIS --debug -o test --save -t congestion -e bnbw

#	    $ANALYSIS -V delay   -T congestion -O pdf -E
        $ANALYSIS --debug -o test --save -t congestion -e delay

#       $ANALYSIS -V rrate   -T reordering -O pdf -E
        $ANALYSIS --debug -o test --save -t reordering -e rrate

#	    $ANALYSIS -V rdelay  -T reordering -O pdf -E
        $ANALYSIS --debug -o test --save -t reordering -e rdelay

#	    $ANALYSIS -V delay   -T reordering -O pdf -E
        $ANALYSIS --debug -o test --save -t reordering -e delay

#	    $ANALYSIS -V ackloss -T reordering -O pdf -E
        $ANALYSIS --debug -o test --save -t reordering -e ackloss

#	    $ANALYSIS -V ackreor -T reordering -O pdf -E
        $ANALYSIS --debug -o test --save -t reordering -e ackreor

#       $ANALYSIS -V bnbw    -T both       -O pdf -E
        $ANALYSIS --debug -o test --save -t both -e bnbw

#	    $ANALYSIS -V rrate   -T both       -O pdf -E
        $ANALYSIS --debug -o test --save -t both -e rrate

#       $ANALYSIS -V rdelay  -T both       -O pdf -E
        $ANALYSIS --debug -o test --save -t both -e rdelay

#       $ANALYSIS -V delay   -T both       -O pdf -E
        $ANALYSIS --debug -o test --save -t both -e delay

#       $ANALYSIS -V ackloss -T both       -O pdf -E
        $ANALYSIS --debug -o test --save -t both -e ackloss

#       $ANALYSIS -V ackreor -T both       -O pdf -E
        $ANALYSIS --debug -o test --save -t both -e ackreor

        cd -
    done
fi

if [ "$1" != "init" ] && [ "$1" != "measure" ] && [ "$1" != "analyze" ]; then
	echo $USAGE
fi
