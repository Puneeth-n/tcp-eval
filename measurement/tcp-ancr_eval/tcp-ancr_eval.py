#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vi:et:sw=4 ts=4

# Copyright (C) 2007 - 2011 Arnd Hannemann <arnd@arndnet.de>
# Copyright (C) 2013 Alexander Zimmermann <alexander.zimmermann@netapp.com>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms and conditions of the GNU General Public License,
# version 2, as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.

# python imports
import textwrap
from twisted.internet import defer, reactor
from collections import defaultdict
from logging import info
import sys
import time
import ConfigParser

# tcp-eval imports
from measurement import measurement, tests

# common options used for all ntests
opts = dict(fg_bin="~/bin/flowgrind", duration=10, dump=None)

delay = 20
# repeat loop
iterations = range(10)

# inner loop with different scenario settings
scenarios = [dict(scenario_label="New Reno", cc="reno"),
             dict(scenario_label="Cubic", cc="cubic")
             #dict( scenario_label = "Native Linux DS",flowgrind_cc="reno",flowgrind_opts=["-O","s=TCP_REORDER_MODULE=native","-A","s"] ),
             #dict( scenario_label = "Native Linux TS",flowgrind_cc="reno",flowgrind_opts=["-O","s=TCP_REORDER_MODULE=native","-A","s"] ),
             #dict( scenario_label = "TCP-aNCR CF", flowgrind_cc="reno",flowgrind_opts=["-O","s=TCP_REORDER_MODULE=ancr",   "-O", "s=TCP_REORDER_MODE=1","-A","s"]),
             #dict( scenario_label = "TCP-aNCR AG", flowgrind_cc="reno",flowgrind_opts=["-O","s=TCP_REORDER_MODULE=ancr",   "-O", "s=TCP_REORDER_MODE=2","-A","s"]),
]


class TcpaNCRMeasurement(measurement.Measurement):
    """This Measurement will run tests of several scenarios:
       - Each scenario is defined by it's flowgrind options.
       - One test of a scenario consists of parallel runs (flows)
         between all pairs defined in the pairs file.
       - One measurement-iteration will run one test of each scenario.
       - The number of iterations is determined by the "iterations" variable.
    """

    def __init__(self):
        """Constructor of the object"""
        """Creates a new TcpEvaluationMeasurement object"""

        # create top-level parser
        description = textwrap.dedent("""\
                Creates successively four TCP flows with four different TCP
                reordering algorithms: Linux TS, Linux DS, TCP-aNCR Agressive
                careful limited retransmit. On all TCP senders all reordering algorithms
                must be available and be allowable to be set . Run 'sudo sysctl
                -a | grep reordering' to check.""")
        measurement.Measurement.__init__(self, description=description)
        self.logprefix = ""
        self.parser.add_argument("pairfile", metavar="FILE", type=str,
                                 help="Set file to load node pairs from")
        self.delay = delay
        self.later_args_list = []

        # initialization of the config parser
        self.config = ConfigParser.RawConfigParser()
        self.dictCharIp = dict()
        self.dictIpCount = defaultdict(list)

    def apply_options(self):
        """Set options"""

        measurement.Measurement.apply_options(self)
        self.config.readfp(open(self.args.pairfile))

        if not (self.config.has_section("PAIRS") and self.config.has_section("CONFIGURATION")):
            print ('SECTION(s) missing in config file')
            exit(1)

        self.runs = list()

        #check for all non duplicate pairs from file
        for src, dst in self.config.items("PAIRS"):
            self.runs.append(dict(src=src,dst=dst,run_label=(lambda src,dst: r"%s\\sra%s"%(src,dst))(src,dst)))

        self.dictCharIp = {char:ip for char, ip in self.config.items("CONFIGURATION")}
        print self.dictCharIp

        for char,ip in self.dictCharIp.items():
            self.dictIpCount[ip].append(char)

        for ip, char in self.dictIpCount.items():
            print ip
            print char
        #print self.dictIpCount.items()
        #print self.dictIpCount.keys()
        #print self.dictIpCount.values()
        #self.run_netem

    @defer.inlineCallbacks
    def run_netem(self, reorder, ackreor, rdelay, delay, ackloss, limit, bottleneckbw, mode):
        fwd_cmd = "sudo tc qdisc %s dev eth0 parent 1:2 handle 20: netem" %mode
        bck_cmd = "sudo tc qdisc %s dev eth0 parent 1:1 handle 10: netem" %mode

        info("Setting netem..")

        for ip, chars in self.dictIpCount.items():

            #forward path delay
            if 'fdnode' in chars and not delay == None:
                fwd_cmd += " delay %ums %ums 20%%" %(delay, (int)(delay * 0.1))

            #forward path reordering
            if reorder == 0:
                fwd_cmd += " reorder 0%%"
            elif 'fdnode' in chars and not reorder == None:
                fwd_cmd += " reorder %u%% reorderdelay %ums %ums 20%%" %(reorder, (rdelay + delay), (int)(rdelay * 0.1))

            if 'qlnode' in chars and not limit == None:
                fwd_cmd += " limit %u" %limit
                bck_cmd += " limit %u" %limit

            #bottleneck bandwidth
            if 'qlnode' in chars and not bottleneckbw == None:
                tc_cmd = "sudo tc class %s dev eth0 parent 1: classid 1:1 htb rate %umbit; \
                    sudo tc class %s dev eth0 parent 1: classid 1:2 htb rate %umbit" %(mode, bottleneckbw, mode, bottleneckbw)
                rc = yield self.remote_execute(ip, tc_cmd, log_file=sys.stdout)
                info(rc)

            #Reverse path reordering
            if ackreor == 0:
                bck_cmd += " reorder 0%%"
            elif 'rrnode' in chars and not ackreor == None:
                bck_cmd += " reorder %u%% reorderdelay %ums %ums 20%%" %(ackreor, (rdelay + delay), (int)(rdelay * 0.1))

            #Reverse path delay
            if 'rdnode' in chars and not delay == None:
                # if .5 values are used for delay, account for it by setting forward path one too low, and reverse path one too high
                if (delay % 1) != 0:
                    delay += 1
                bck_cmd += " delay %ums %ums 20%%" %(delay, (int)(delay * 0.1))

            #ack loss
            if ackloss == 0:
                bck_cmd = " drop 0%%"
            elif 'alnode' in chars and not ackloss == None:
                bck_cmd = " drop %u%%" %(ackloss)

            rc = yield self.remote_execute(ip, fwd_cmd, log_file=sys.stdout)
            info(rc)
            rc = yield self.remote_execute(ip, bck_cmd, log_file=sys.stdout)
            info(rc)

    def run_periodically(self, count = -1):
        """change netem settings every <later_args_time> seconds"""

        if len(self.later_args_list) == 0:
            return

        if count >= 0 and count < len(self.later_args_list):
            self.run_netem(*self.later_args_list[count])

        settings = [count+1]
        reactor.callLater(self.later_args_time, self.run_periodically, *settings)

    @defer.inlineCallbacks
    def run_measurement(self, reorder_mode, var, reorder, ackreor, rdelay, delay, ackloss, limit, bottleneckbw):
        print reorder_mode, var, reorder, ackreor, rdelay, delay, ackloss, limit, bottleneckbw
        for it in iterations:
            for scenario_no in range(len(scenarios)):
#                tasks = list()
                logs = list()
                for run_no in range(len(self.runs)):
                    kwargs = dict()

                    kwargs.update(opts)
                    kwargs.update(self.runs[run_no])

                    kwargs['flowgrind_src'] = kwargs['src']
                    kwargs['flowgrind_dst'] = kwargs['dst']

                    # use a different port for every test
                    kwargs['bport'] = int("%u%u%02u" %(scenario_no + 1, it, run_no))

                    # set logging prefix, tests append _testname
                    self.logprefix="i%03u_s%u_r%u" % (it, scenario_no, run_no)
                    logs.append(self.logprefix)

                    # merge parameter configuration for the tests
                    kwargs.update(scenarios[scenario_no])

                    # Timestamps.. dirty solution
                    ts_cmd = ""
                    if (scenarios[scenario_no]["scenario_label"] == "Native Linux TS"):
                        ts_cmd = "sudo sysctl -w net.ipv4.tcp_timestamps=1"
                    else:
                        ts_cmd = "sudo sysctl -w net.ipv4.tcp_timestamps=0"

                    print ts_cmd
                    print self.runs[run_no].get('src')
                    print self.runs[run_no].get('dst')

                    rc = yield self.remote_execute(self.runs[run_no].get('src'), ts_cmd)
                    info(rc)
                    rc = yield self.remote_execute(self.runs[run_no].get('dst'), ts_cmd)
                    info(rc)

                    # set source and dest for tests
                    # actually run tests
                    info("run test %s" %self.logprefix)
#                    if self.parallel:
#                        tasks.append(self.run_test(tests.test_flowgrind, **kwargs))
#                    else:
#                        yield self.run_netem(reorder, ackreor, rdelay, delay, ackloss, limit, bottleneckbw, "change")
#                        self.run_periodically()

                    yield self.run_netem(reorder, ackreor, rdelay, delay, ackloss, limit, bottleneckbw, "change")
                    yield self.run_test(tests.test_flowgrind, **kwargs)

#                if self.parallel:
#                    yield self.run_netem(reorder, ackreor, rdelay, delay, ackloss, limit, bottleneckbw, "change")
#                    self.run_periodically()

#                    yield defer.DeferredList(tasks)

                # header for analyze script
                for prefix in logs:
                    logfile = open("%s/%s_test_flowgrind" %(self.args.log_dir, prefix), "r+")
                    old = logfile.read() # read everything in the file
                    logfile.seek(0) # rewind
                    logfile.write("""testbed_param_qlimit=%u\n""" \
                        """testbed_param_rdelay=%u\n"""           \
                        """testbed_param_rrate=%u\n"""            \
                        """testbed_param_delay=%f\n"""            \
                        """testbed_param_ackreor=%u\n"""          \
                        """testbed_param_ackloss=%u\n"""          \
                        """testbed_param_reordering=%s\n"""       \
                        """testbed_param_variable=%s\n"""         \
                        """testbed_param_bottleneckbw=%u\n"""       %(limit, rdelay, reorder, delay, ackreor, ackloss, reorder_mode, var, bottleneckbw))
                    logfile.write(old)
                    logfile.close()

                info("Sleeping ..")
                time.sleep(2)

        yield self.tear_down()
        reactor.stop()

            # count overall iterations
#            self.count += 1

    @defer.inlineCallbacks
    def run(self):
        pass

#    @defer.inlineCallbacks
#    def run_all(self):
#        """Main method"""
#
#        yield self.run()
#
    #    reactor.stop()

    def main(self):
        self.parse_options()
        self.apply_options()
#        self.run_all()
        self.run()
        print 'After Run'
        reactor.run()

if __name__ == "__main__":
    TcpaNCRMeasurement().main()
