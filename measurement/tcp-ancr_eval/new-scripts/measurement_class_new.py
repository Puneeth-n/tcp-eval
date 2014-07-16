#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vi:et:sw=4 ts=4

# Copyright (C) 2014 Puneeth Nanjundaswamy <puneeth@netapp.com>
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
import sys, os
import time
import ConfigParser

# fabric imports (pip install fabric)
from fabric.api import *
from fabric import tasks
from fabric.colors import green, red, yellow
from fabric.api import env, run, sudo, task, hosts, execute
from fabric.context_managers import cd, settings, hide
from fabric.network import disconnect_all
import fabric.state

# tcp-eval imports
from measurement import measurement, tests
# common options used for all ntests
opts = dict(fg_bin="~/bin/flowgrind", dump=True)

# repeat loop
iterations = range(1)

# inner loop with different scenario settings
scenarios = [
             dict( scenario_label = "Native Linux DS",cc="reno"),
             dict( scenario_label = "Native Linux TS",cc="reno"),
]

env.username = 'puneeth'
env.key_filename = "~/.ssh/id_rsa"
env.password = 'test'
env.colorize_errors = True
env.warn_only = False
env.skip_bad_hosts = True

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
        self.parser.add_argument("-i", "--iterations", metavar="NUM",
                action="store", type=int, default="1", help="Iterations (default: 10)")
        self.parser.add_argument("-t", "--time", metavar="NUM",
                action="store", type=int, default="120", help="Flowgrind time (default: 120s)")
        self.parser.add_argument("-o", "--offset", metavar="NUM",
                action="store", type=int, default="0", help="""offset used to
                prefix log files(default: 0) Should be SET when iterating on all
                scenarios repeatedly to ensure log files are not overwritten.""")
        self.parser.add_argument("-n", "--netperf", action="store_true",
                default=False, dest="netperf",
                help="Use netperf instead of flowgrind (default: False")
        self.parser.add_argument("-y", "--dry-run", action="store_true",
                default=False, dest="dry_run",
                help="Test the pairs file without starting the experiment")

        self.later_args_list = []

        # initialization of the config parser
        self.config = ConfigParser.RawConfigParser()
        self.dictCharIp = dict()
        self.dictIpCount = defaultdict(list)
        self.dictExpMgt = dict()
        self.listPairs = list()
        self.runs = list()
        self.count = 0
        self.delay = 20
        self.bnbw = 20

    def apply_options(self):
        """Set options"""

        measurement.Measurement.apply_options(self)
        self.config.readfp(open(self.args.pairfile))

        if not (self.config.has_section("PAIRS") and self.config.has_section("CONFIGURATION") and self.config.has_section("MANAGEMENT")):
            print (red('SECTION(s) missing in config file'))
            exit(1)

        #check for all non duplicate pairs from pairs file
        for src, dst in self.config.items("PAIRS"):
            self.runs.append(dict(flowgrind_src=src,flowgrind_dst=dst,run_label=(lambda src,dst: r"%s\\sra%s"%(src,dst))(src,dst)))
            if src not in self.listPairs: self.listPairs.append(src)
            if dst not in self.listPairs: self.listPairs.append(dst)

        self.dictCharIp = {char:ip for char, ip in self.config.items("CONFIGURATION")}
        #print self.dictCharIp
        self.dictExpMgt = {exp:mgt for exp, mgt in self.config.items("MANAGEMENT")}

        #Each node has a characteristic. The list of characteristics are mentioned in the pairs file.
        #The idea of this for loop is to group all characteristics of a particular node so that 
        #traffic shaping can be performed cumulatively!
        for char,ip in self.dictCharIp.items():
            self.dictIpCount[ip].append(char)

        #for ip, char in self.dictIpCount.items():
            #print ip
            #print char
            #print self.dictIpCount.items()
            #print self.dictIpCount.keys()
            #print self.dictIpCount.values()

        self.scenarios = scenarios
        self.iterations = self.args.iterations
        self.offset = self.args.offset

    def reset_sysctl(self):
        cmd = ("sysctl -w "
                    "net.ipv4.tcp_no_metrics_save=1 "
                    "net.ipv4.tcp_congestion_control=reno "
                    "net.ipv4.tcp_sack=1 "
                    "net.ipv4.tcp_dsack=1 "
                    "net.ipv4.tcp_timestamps=0 "
                    "net.ipv4.tcp_fack=0 "
                    "net.ipv4.tcp_ecn=0 "
                    "net.ipv4.tcp_mtu_probing=0 "
                    "net.ipv4.tcp_frto=0"
                )
        tasks.execute(self.exec_sudo, cmd=cmd, hosts=self.listPairs)

    def configure_NIC(self):
        #Turn off segment offloading
        cmd = ("ethtool --offload eth0 rx off tx off gso off gro off")
        with settings(warn_only=True):
            tasks.execute(self.exec_sudo, cmd=cmd, hosts=self.listPairs)


    def run_netem(self, reorder, ackreor, rdelay, delay, ackloss, limit, bottleneckbw, mode, **kwargs):

        info("Setting netem..")

        if mode == 'add':
            cmd = 'tc qdisc del dev eth0 root'
            with settings(warn_only=True):
                tasks.execute(self.exec_sudo, cmd=cmd, hosts=self.dictExpMgt.values())

            cmd = 'tc qdisc add dev eth0 root handle 1: htb'
            tasks.execute(self.exec_sudo, cmd=cmd, hosts=set(self.dictCharIp.values()))

            cmd = """tc class add dev eth0 parent 1: classid 1:1 htb rate 1000mbit &&
                    tc filter add dev eth0 parent 1: protocol ip prio 1 u32 flowid 1:1 match ip src %s""" %(kwargs['flowgrind_dst'])
            tasks.execute(self.exec_sudo, cmd=cmd, hosts=set(self.dictCharIp.values()))

            cmd = """tc class add dev eth0 parent 1: classid 1:2 htb rate 1000mbit &&
                    tc filter add dev eth0 parent 1: protocol ip prio 1 u32 flowid 1:2 match ip src %s""" %(kwargs['flowgrind_src'])
            tasks.execute(self.exec_sudo, cmd=cmd, hosts=set(self.dictCharIp.values()))

        for ip, chars in self.dictIpCount.items():

            fwd_cmd = "tc qdisc %s dev eth0 parent 1:2 handle 20: netem" %(mode)
            bck_cmd = "tc qdisc %s dev eth0 parent 1:1 handle 10: netem" %(mode)
            set_fwd_cmd = False
            set_bck_cmd = False

            #bottleneck bandwidth
            if 'qlnode' in chars:
                if bottleneckbw:
                    tc_cmd = """tc class change dev eth0 parent 1: classid 1:1 htb rate %umbit &&
                            tc class change dev eth0 parent 1: classid 1:2 htb rate %umbit""" %(bottleneckbw, bottleneckbw)
                    tasks.execute(self.exec_sudo, cmd=tc_cmd, hosts=self.dictExpMgt[ip])

                if limit:
                    fwd_cmd = "tc qdisc %s dev eth0 parent 1:2 handle 20: pfifo limit %u " %(mode, limit)
                    bck_cmd = "tc qdisc %s dev eth0 parent 1:1 handle 10: pfifo limit %u " %(mode, limit)
                    #assuming that the qlnode has just bottleneck and queue limit constraints, the command is executed here
                    tasks.execute(self.exec_sudo, cmd=fwd_cmd, hosts=self.dictExpMgt[ip])
                    tasks.execute(self.exec_sudo, cmd=bck_cmd, hosts=self.dictExpMgt[ip])
                continue

            #forward path delay
            if 'fdnode' in chars:
                if delay:
                    fwd_cmd += " rate 1000mbit delay %ums %ums 20%%" %(delay, (0.1*delay))
                else:
                    fwd_cmd += " rate 1000mbit delay %ums %ums 20%%" %(self.delay, (0.1*self.delay))
                set_fwd_cmd = True

            #forward path reordering
            #Assuming that I am booting a reorder only kernel in one of the nodes which exclusively does reordering.
            if 'frnode' in chars and reorder:
                fwd_cmd += " reorder %u%% reorderdelay %ums %ums 20%%" %(reorder, (rdelay), (int)(rdelay * 0.1))
                set_fwd_cmd = True

            #Reverse path delay
            if 'rdnode' in chars:
                # if .5 values are used for delay, account for it by setting forward path one too low, and reverse path one too high
                if delay:
                    if (delay % 1) != 0:
                        delay += 1
                        bck_cmd += " rate 1000mbit delay %ums %ums 20%%" %((delay+1), (0.1*delay))
                    else:
                        bck_cmd += " rate 1000mbit delay %ums %ums 20%%" %((delay), (0.1*delay))
                else:
                    bck_cmd += " rate 1000mbit delay %ums %ums 20%%" %((self.delay), (0.1*self.delay))
                set_bck_cmd = True

            #Reverse path reordering
            if 'rrnode' in chars and ackreor:
                bck_cmd += " reorder %u%% reorderdelay %ums %ums 20%%" %(ackreor, (rdelay + delay), (int)(rdelay * 0.1))
                set_bck_cmd = True

            #ack loss
            if 'alnode' in chars and ackloss:
                bck_cmd += " drop %u%%" %(ackloss)
                set_bck_cmd = True

            if set_bck_cmd:
                tasks.execute(self.exec_sudo, cmd=bck_cmd, hosts=self.dictExpMgt[ip])
            if set_fwd_cmd:
                tasks.execute(self.exec_sudo, cmd=fwd_cmd, hosts=self.dictExpMgt[ip])

    def start_test(self, log_file, flowgrind_src, flowgrind_dst, src_ctrl, dst_ctrl, duration=120, warmup=0, cc=None, dump=None,
            bport=5999, opts=[], flowgrind_opts = [], fg_bin="flowgrind", **kwargs):
        """This test performs a simple flowgrind (new, aka dd version) test with
          one tcp flow from src to dst.

             required arguments:
                  log_file: file descriptor where the results are written to
                  src     : sender of the flow
                  dst     : receiver of the flow

             optional arguments:
                  duration : duration of the flow in seconds
                  cc       : congestion control method to use
                  warmup   : warmup time for flow in seconds
                  dump     : turn tcpdump on src and dst on iface 'dump' on
                  bport    : flowgrind base port
                  opts     : additional command line arguments
                  fg_bin   : flowgrind binary
        """
        # path of executable
        cmd = fg_bin

        # add -p for numerical output
        #cmd += " -p"

        # test duration
        cmd += " -T s=%.2f" % (duration)

        # inital delay
        if warmup:
            cmd += " -Y s=%.2f" % (warmup)

        # which tcp congestion control module
        if cc:
            cmd += " -O s=TCP_CONG_MODULE=%s" % (cc)

        # build host specifiers
        cmd += " -H s=%s/%s,d=%s/%s" %(flowgrind_src, src_ctrl, flowgrind_dst, dst_ctrl)

        # just add additional parameters
        if opts:
            cmd += opts

        if flowgrind_opts:
            cmd += flowgrind_opts

        if dump:
            # set tcpdump at dest for tests
            time.sleep(2)
            dump_cmd = '(nohup tcpdump -pni eth0 -w /tmp/D%s.pcap) & sleep 2' %(self.logprefix)
            tasks.execute(self.exec_sudo, cmd=dump_cmd, hosts=dst_ctrl)
            dump_cmd = '(nohup tcpdump -pni eth0 -w /tmp/S%s.pcap) & sleep 2' %(self.logprefix)
            tasks.execute(self.exec_sudo, cmd=dump_cmd, hosts=src_ctrl)
            # set tcpdump at dest for tests

        if self.args.netperf:
            cmd = 'netperf -l 120 -D 0.05 -L %s -H %s -t TCP_STREAM' %(flowgrind_src,flowgrind_dst)
            if self.args.dry_run:
                print(yellow(cmd))
            else:
                # start netperf
                print (green("Starting Netperf\n"))
                result = local(cmd, capture=True)
                if not result.return_code == 0:
                    print (red("Error executing netperf\n"))
                else:
                    log_file.write(result.stdout)
                    log_file.flush()

        else:
            if self.args.dry_run:
                print (yellow(cmd))
            else:
                # start flowgrind
                print (green("Starting Flowgrind\n"))
                result = local(cmd, capture=True)
                if not result.return_code == 0:
                    print (red("Error executing flowgrind\n"))
                else:
                    log_file.write(result.stdout)
                    log_file.flush()

        if dump:
            time.sleep(5)
            dump_cmd = "killall tcpdump"
            with settings(warn_only=True):
                tasks.execute(self.exec_sudo, cmd=dump_cmd, hosts=[src_ctrl,dst_ctrl])
        if not result.return_code == 0:
            exit(1)
        print (green("Finished test."))

    def prepare_test(self, append=False, **kwargs):
        """Runs a test method with arguments self, logfile, args"""

        if not os.path.exists(self.args.log_dir):
            info("%s does not exist, creating. " % self.args.log_dir)
            os.mkdir(self.args.log_dir)

        log_name = "%s_test_flowgrind" %(self.logprefix)
        log_path = os.path.join(self.args.log_dir, log_name)

        if append:
            log_file = open(log_path, 'a')
        else:
            log_file = open(log_path, 'w')

        # write config into logfile
        for item in kwargs.iteritems():
            log_file.write("%s=%s\n" %item)
        log_file.write("test_start_time=%s\n" %time.time())
        log_file.write("BEGIN_TEST_OUTPUT\n")
        log_file.flush()

        # actually run test
        info("Starting test test_flowgrind with: %s", kwargs)
        self.start_test(log_file, **kwargs)
        #self._update_stats("test_flowgrind",rc)
        log_file.close()

    def run_measurement(self, reorder_mode, var, reorder, ackreor, rdelay, delay, ackloss, limit, bottleneckbw):
        print reorder_mode, var, reorder, ackreor, rdelay, delay, ackloss, limit, bottleneckbw
        for it in iterations:
            for scenario_no in range(len(self.scenarios)):
                logs = list()
                for run_no in range(len(self.runs)):
                    kwargs = dict()
                    pairs = list()

                    kwargs.update(opts)
                    kwargs.update(self.runs[run_no])

                    # use a different port for every test
                    kwargs['bport'] = int("%u%u%02u" %(scenario_no + 1, self.count, run_no))
                    kwargs['duration'] = self.args.time

                    # set logging prefix, tests append _testname
                    self.logprefix="i%u%03u_s%u_r%u" % (self.offset,self.count, scenario_no, run_no)
                    logs.append(self.logprefix)

                    # merge parameter configuration for the tests
                    kwargs.update(self.scenarios[scenario_no])
                    #print self.scenarios[scenario_no]

                    # Timestamps.. dirty solution
                    ts_cmd = ""
                    if (self.scenarios[scenario_no]["scenario_label"] == "Native Linux TS"):
                        ts_cmd = "sysctl -w net.ipv4.tcp_timestamps=1"
                    else:
                        ts_cmd = "sysctl -w net.ipv4.tcp_timestamps=0"

                    kwargs['src_ctrl'] = self.dictExpMgt[kwargs['flowgrind_src']]
                    kwargs['dst_ctrl'] = self.dictExpMgt[kwargs['flowgrind_dst']]

                    pairs.append(self.dictExpMgt[kwargs['flowgrind_src']])
                    pairs.append(self.dictExpMgt[kwargs['flowgrind_dst']])

                    tasks.execute(self.exec_sudo, cmd=ts_cmd, hosts=pairs)

                    # set source and dest for tests
                    # actually run tests
                    info("run test %s" %self.logprefix)

                    if self.first_run:
                        self.run_netem(reorder, ackreor, rdelay, delay, ackloss, limit, bottleneckbw, "add", **kwargs)
                        self.first_run = False
                    else:
                        self.run_netem(reorder, ackreor, rdelay, delay, ackloss, limit, bottleneckbw, "change", **kwargs)

                    if not self.args.dry_run:
                        self.prepare_test(**kwargs)

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
        self.count += 1

    def run(self):
        pass

    def run_all(self):
        self.run()

        disconnect_all()

    @parallel
    def exec_sudo(self,cmd):
        print (yellow(cmd))
        sudo(cmd)

    def main(self):
        self.parse_options()
        self.apply_options()
        self.reset_sysctl()
        self.configure_NIC()
        self.run_all()

if __name__ == "__main__":
    TcpaNCRMeasurement().main()
