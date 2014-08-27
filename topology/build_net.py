#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vi:et:sw=4 ts=4

# Copyright (C) 2014 Puneeth Nanjundaswamy <puneeth@netapp.com>
# Copyright (C) 2009 - 2013 Alexander Zimmermann <alexander.zimmermann@netapp.com>
# Copyright (C) 2007 Arnd Hannemann <arnd@arndnet.de>
# Copyright (C) 2007 Lars Noschinski <lars.noschinski@rwth-aachen.de>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms and conditions of the GNU General Public License,
# version 2, as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.

#TODO:
#add sanity check on if ip address and interface reallllllllllllllllllly match. just one
#interface check is enough for now

# python imports
import re
import socket
import sys
import os
import argparse
import string
import textwrap
import ConfigParser
from logging import info, warn, error
#import netifaces as ni

# fabric imports (pip install fabric)
from fabric.api import *
from fabric import tasks
from fabric.colors import green, red, yellow
from fabric.api import env, run, sudo, task, hosts, execute
from fabric.context_managers import cd, settings, hide
from fabric.network import disconnect_all
import fabric.state

# tcp-eval imports
from common.application import Application
from common.functions import *

pairs = []
nodes = []
env.hosts = []
env.username = 'puneeth'
env.password = 'test'
env.key_filename = "~/.ssh/id_rsa"
env.colorize_errors = True
env.warn_only = False

class BuildNet(Application):

    def __init__(self):
        """Creates a new BuildVmesh object"""
        # object variables
        self.conf = None
        self.linkinfo = dict()
        self.ipcount = dict()
        self.hosts_m = dict()
        self.hosts_e = dict()

#values for "match ip protocol <protocol number> 0xff"
#protocol id: 17 for UDP
#protocol id: 47 for GRE
#protocol id: 6 for TCP
#protocol id: 1 for ICMP
#cat /etc/protocols for more protocol numbers
        self.shapecmd_multiple = textwrap.dedent("""\
                tc class add dev %(iface)s parent 1: classid 1:%(parentNr)d%(nr)02d htb rate %(rate)smbit; \
                tc filter add dev %(iface)s parent 1: protocol ip prio 16 u32 \
                match ip protocol 1 0xff flowid 1:%(parentNr)d%(nr)02d \
                match ip dst %(dst)s""")
        self.shapecmd = textwrap.dedent("""\
                tc class add dev %(iface)s parent 1: classid 1:%(nr)d htb rate %(rate)smbit && \
                tc filter add dev %(iface)s parent 1: protocol ip prio 16 u32 \
                flowid 1:%(nr)d \
                match ip src %(src)s""")
#                match ip protocol 1 0xff flowid 1:%(nr)d \
#                match ip dst %(dst)s""")

        self._rtoffset = 300

        # initialization of the config parser
        self.config = ConfigParser.RawConfigParser()

        # create top-level parser
        description = textwrap.dedent("""\
                This program creates a virtual network based netem and a GRE tunnel. The
                topology of the virtual network is specified in a config file as an adjacency
                matrix. The config file syntax looks like the following
                    1: 2[10,,,100] 3 5-6[0.74,20,,10]
                    2: ...

                VM 1 reaches all VMs listed after the colon, every VM listed after the colon
                reaches VM 1. Link information may be given in brackets after every entry with
                the syntax [rate, limit, delay, loss], where:
                    * Rate: in mbps as float
                    * Queue limit: in packets as int
                    * Delay: in ms as int
                    * Loss: in percent as int

                The link information given for an entry are just a limit for ONE direction, so
                that it is possible to generate asynchronous lines. Empty lines and lines
                starting with # are ignored.""")
        Application.__init__(self,
                formatter_class=argparse.RawDescriptionHelpFormatter,
                description=description)
        self.parser.add_argument("config_file", metavar="configfile",
                help="Topology of the virtual network")
        self.parser.add_argument("-i", "--interface", metavar="IFACE",
                action="store", default="eth0", help="Interface to use for "\
                        "the experiment (default: %(default)s)")
        self.parser.add_argument("-m", "--mcast", metavar="IP",
                action="store", default="224.66.66.66", help="Multicast IP to "\
                        "use for the experiment (default: %(default)s)")
        self.parser.add_argument("-o", "--offset", metavar="NUM",
                action="store", type=int, default="0", help="Add this offset "\
                        "to all node IDs in the config file")
        self.parser.add_argument("-u", "--user-scripts", metavar="PATH",
                action="store", nargs="?", const="./user-script",
                dest="user_scripts",
                help="Execute user scripts for every node (default: %(const)s)")
        self.parser.add_argument("-s", "--static-routes", action="store_true",
                dest="static_routes", default=False, help="Setup static routing "\
                 "according to topology")
        self.parser.add_argument("-t", "--traffic-shape", action="store_true",
                dest="tc", default=False, help="""Setup traffic shaping on the 
                topology""")
        self.parser.add_argument("-p", "--multipath", metavar="NUM",
                action="store", nargs="?", type=int, const="2", default=False,
                help="Set up equal cost multipath routes with maximal "\
                        "'%(metavar)s' of parallel paths (default: %(const)s)")
        self.parser.add_argument("-R", "--rate", metavar="RATE", action="store",
                default="1000",help="Rate limit in mbps")
        self._topology_group=self.parser.add_mutually_exclusive_group()
        self._topology_group.add_argument("-e", "--multiple-topology",
                action="store_true", default=False, dest="multiple_topology",
                help = "Activate multiple toplogy support. Is neccessary if "\
                        "you want to deploy serveral topolgies at once")
        self._topology_group.add_argument("-E", "--multiple-topology-reset",
                action="store_true", default=False,
                dest="multiple_topology_reset", help="Activate multiple "\
                        "toplogy support. Is neccessary if you want to "\
                        "deploy serveral topolgies at once and reset the "\
                        "root node")
        self.parser.add_argument("-y", "--dry-run", action="store_true",
                default=False, dest="dry_run",
                help="Test the config only without setting it up")

    def apply_options(self):
        """Set the options for the BuildVmesh object"""

        Application.apply_options(self)

        self.conf = self.parse_config(self.args.config_file)

        try:
            self.config.readfp(open(self.args.config_file))
        except (OSError, IOError) as e:
            error("configuration file not found")
            error("no such file or directory: %s " %self.args.config_file)
            exit(1)

        if not self.config.has_section("TOPOLOGY"):
            print (red("Error: TOPOLOGY Section missing"))
            exit(1)

        if len(self.config.sections()) == 1:
            print (red("Error: Please give me some info on nodes "))
            exit(1)

        for key in self.conf.keys():
            try:
                self.hosts_m[key] = self.config.get(str(key),"mip")
                self.hosts_e[key] = self.config.get(str(key),"eip")
                env.hosts.append(self.hosts_m[key])
                if self.config.get(str(key),"type") not in ('src', 'dst'):
                    nodes.append(self.hosts_m[key])
                else:
                    pairs.append(self.hosts_m[key])
            except:
                print(red("In Node %s some/all option(s) missing"%(key)))
                exit(1)

        #this sort is necessary to ensure that even if the nodes are not
        #entered in-sequence in the config file, we still have a sorted list
        env.hosts.sort()

        if self.args.debug:
            print yellow("Node: Management IP Address: "), self.hosts_m
            print yellow("Node: Experiment IP Address: "), self.hosts_e
            print yellow("Host list for fabric: "), env.hosts

        #sanity check to see if the node details and those in the topology match
        if (len(self.conf) > len(self.hosts_m)):
            print(red("The number of nodes declared is less than the number of nodes in the topology"))
            exit(1)

        if len(set(self.hosts_e.values())) != len(self.hosts_e) or \
           len(set(self.hosts_m.values())) != len(self.hosts_m):
            print(red("Duplicate ip addresses declared for two different nodes"))
            exit(1)

#        cmd = "ifconfig %s | awk -F':' '/inet addr/&&!/127.0.0.1/{split($2,_," ");print _[1]}'"%(self.args.interface)

    def parse_config(self, file):
        """Returns an hash which maps host number -> set of reachable host numbers

           Config file syntax: Each line either begins with a # (comment)
           or has a form like

                host1: host2 host3 host5-host6

           where host* are numbers.

                host1: host2

           means, that host1 reaches host2 and vice versa.

                host1: host2 host3

           is equivalent to

               host1: host2
               host1: host3

           and

               host1: host2-host4

           is equivalent to

               host1: host2, host3, host4

           Note that the reachability relation defined by the config file is
           always symmetric.
        """

        # match comments
        comment_re = re.compile('^\s*#')

        # line syntax:
        # LINE = HOST (COUNT)":" REACHES
        # HOST = DIGITS
        # REACHES = DIGITS REACHES | DIGITS "-" DIGITS " " REACHES
        # additional spaces are allowed everywhere, except around the "-"
        digits_str = r"""
                [0-9]+                              # INT
                """
        float_str = r"""
                %s(?:\.%s)?                         # INT "." INT
                """ % (digits_str,digits_str)
        line_str = r"""
                ^(?P<host>%s)\ *\(?(?P<count>%s)?\)?:             # HOST ":"
                \ *                                 # optional spaces
                (?P<reaches>( %s )+)                         # REACHES
                $"""
        reaches_str = r"""
                (%s)(?:-(%s))?                      # DIGITS | DIGITS "-" DIGITS
                (?:\[(%s)?(?:,(%s)?)?(?:,(%s)?)?(?:,(%s)?)?\])?    # [ "[" FLOAT,INT,INT,INT "]" ]
                (?:\ +|$)                           # optional spaces
                """ % (digits_str,digits_str,float_str,digits_str,digits_str,digits_str)

        line_re    = re.compile(line_str % (digits_str, digits_str, reaches_str), re.VERBOSE)
        reaches_re = re.compile(reaches_str, re.VERBOSE)

        # read (asymmetric) reachability information from the config file
        asym_map = {}

        fd = open(file, 'r')

        #for-loop fast forwards >> to the topology section

        for line in fd:
            if '[TOPOLOGY]' not in line:
                continue
            else:
                break

        for line in fd:

            # strip trailing spaces
            line = line.strip()

            # ignore empty lines and comments
            if line is '' or comment_re.match(line):
                continue

            # parse line, skip on syntax error
            lm = line_re.match(line)
            if not lm:
                warn("Syntax error in line %s. Skipping." %line)
                continue

            # get linkinfos
            # offset has to be added to every host
            offset = self.args.offset
            host = int(lm.group('host')) + offset
            reaches = set()
            for m in reaches_re.findall(lm.group('reaches')):
                first = int(m[0]) + offset
                if m[1]: last = int(m[1]) + offset
                else: last = first
                info_rate = m[2]
                info_limit = m[3]
                info_delay = m[4]
                info_loss = m[5]
                if last:
                    reaches.update(range(first, last+1))
                else:
                    reaches.add(first)

                if not self.linkinfo.has_key(host):
                    self.linkinfo[host] = dict()
                for i in range(first, last+1):
                    self.linkinfo[host][i] = dict()
                    self.linkinfo[host][i]['rate'] = info_rate
                    self.linkinfo[host][i]['limit'] = info_limit
                    self.linkinfo[host][i]['delay'] = info_delay
                    self.linkinfo[host][i]['loss'] = info_loss

            asym_map[host] = reaches
            if (lm.group('count') is None) or (lm.group('count') < 1):
                self.ipcount[host] = 1
            else:
                self.ipcount[host] = lm.group('count')

        # Compute symmetric hull
        hosts = set(asym_map.keys()).union(reduce(lambda u,v: u.union(v), asym_map.values(), set()))
        reachability_map = dict(map(lambda x: (x, set()), hosts))
        for (host, reaches) in asym_map.iteritems():
            for r in reaches:
                reachability_map[host].add(r)
                reachability_map[r].add(host)

        return reachability_map

    #Give this function a management ip address and it will give back the hostnum
    def get_host(self,hostaddr):
        return [hostnum for hostnum, ipaddr in self.hosts_m.items() if ipaddr == hostaddr][0]

    #Give this function a hostnum and it will give back the host's experiment ip address
    def get_eip(self,hostnum):
        return self.hosts_e[hostnum]

    def visualize(self, graph):
        """Visualize topology configuration"""
        info(yellow("Configured with the following topology:"))
        dot_content = list()
        dot_content.append("digraph G {")
        for host in graph:
             for neigh in graph[host]:
               dot_content.append("%s -> %s" %(host, neigh))
        dot_content.append("}")
        try:
            call("graph-easy --as=ascii", input="\n".join(dot_content))
        except CommandFailed, inst:
            warn("Visualizing topology failed.")
            warn("Visualizing failed: RC=%s, Error=%s" % (inst.rc, inst.stderr))

    def net_num(self, interface):
        num = interface.lstrip(string.letters)
        return int(num)

    def setup_trafficcontrol(self):
        #puneeth : why was this being set at eth0?????
        iface = self.args.interface
        parent_num = self.net_num(self.args.interface) + 1

        # Add qdisc
        if self.args.multiple_topology or self.args.multiple_topology_reset:
            if self.args.multiple_topology_reset:
                cmd_1 = "tc qdisc del dev %s root " % iface
                cmd_2 = "tc qdisc add dev %s root handle 1: htb default 1100;" % iface
            else:
                cmd_1 = "tc qdisc ls dev %(iface)s | grep root | grep -o pfifo_fast | xargs --replace=STR bash -c \" \
                    tc qdisc del dev %(iface)s root;" % {'iface' : iface}
                cmd_2 = "tc qdisc add dev %(iface)s root handle 1: htb default 1100;" % {'iface' : iface}
        else:
            cmd_1 = "tc qdisc del dev %s root " % iface
            cmd_2 = "tc qdisc add dev %s root handle 1: htb default 100" % iface

        # It is ok if the deletion of queuing discipline fails. If the intended
        #queueing discipline wasn't created by the script, the deletion fails.
        with settings(
                hide('stdout'),
                show('warnings', 'running', 'stderr'),
                warn_only=True):
            tasks.execute(self.exec_sudo, cmd=cmd_1, hosts=nodes)
            tasks.execute(self.exec_sudo, cmd=cmd_1, hosts=pairs)
        #cmd_2 shouldn't fail. Abort if any of the fabric scripts fail in the script
        tasks.execute(self.exec_sudo, cmd=cmd_2, hosts=nodes)

        for hostaddr in nodes:

            self.hostnum = self.get_host(hostaddr)
            peers = self.conf.get(self.hostnum, set())

        # Add class and filter for each peer
            i = 0
            for p in sorted(peers):
                if self.linkinfo.has_key(self.hostnum) and self.linkinfo[self.hostnum].has_key(p) \
                        and self.linkinfo[self.hostnum][p]['rate'] != '':
                    rate = self.linkinfo[self.hostnum][p]['rate']
                elif self.args.rate:
                    rate = self.args.rate
                else:
                    continue

                i+=1

                info(yellow("Limiting rate of link %s -> %s to %s mbit" % (self.hostnum,p,rate)))

                netem_str = ''
                if self.args.multiple_topology or self.args.multiple_topology_reset:
                    #TODO: Can lead to problems if one destionation is reachable from serveral devices!
                    #Need to check for such links and combine them to one
                    cmd = self.shapecmd_multiple % {
                        'iface' : iface,
                        'nr' : i,
                        'parentNr' : parent_num,
                        'dst' : self.hosts_e[p],
                        'rate' : rate}
                    if self.args.debug:
                        info(yellow("Node No. %d : IP Address %s" %(self.hostnum,self.hosts_e[self.hostnum])))
                        info(yellow("Node No. %d : IP Address %s" %(p,self.hosts_e[p])))
                    tasks.execute(self.exec_sudo, cmd=cmd, hosts=hostaddr)
                    netem_str = 'tc qdisc add dev %s parent 1:%d%02d handle %d%02d: netem' % (iface, parent_num, i, parent_num, i)
                else:
                    if self.hostnum < p:
                        addr = self.hosts_e[min(map(int,self.hosts_e))]
                    else:
                        #Puneeth: this is the shittiest solution. remove it!
                        #I wonder why I did it this way!
                        #Use the config file type to assign values
                        addr = self.hosts_e[max(map(int,self.hosts_e))]

                    cmd = self.shapecmd % {
                        'iface' : iface,
                        'nr' : i,
#                        'dst' : self.hosts_e[p],
                        'src' : addr,
                        'rate' : rate}
                    if self.args.debug:
                        info(yellow("Node No. %d : IP Address %s" %(self.hostnum,self.hosts_e[self.hostnum])))
                        info(yellow("Node No. %d : IP Address %s" %(p,self.hosts_e[p])))
                    tasks.execute(self.exec_sudo, cmd=cmd, hosts=hostaddr)
                    netem_str = 'tc qdisc add dev %s parent 1:%s handle %s0: netem' % (iface, i, i)


                # netem for queue length, delay and loss
                if self.linkinfo[self.hostnum][p]['limit'] != '':
                    netem_str += ' limit %s' %self.linkinfo[self.hostnum][p]['limit']
                if self.linkinfo[self.hostnum][p]['delay'] != '':
                    netem_str += ' delay %sms' %self.linkinfo[self.hostnum][p]['delay']
                if self.linkinfo[self.hostnum][p]['loss'] != '':
                    netem_str += ' drop %s' %self.linkinfo[self.hostnum][p]['loss']

                # create netem queue only if one of the parameter is given
                if self.linkinfo[self.hostnum][p]['limit'] != '' or self.linkinfo[self.hostnum][p]['delay'] != '' \
                        or self.linkinfo[self.hostnum][p]['loss'] != '':
                    info(yellow("      Adding netem queue, limit:\'%s\', delay:\'%s\', loss:\'%s\'"
                         % (self.linkinfo[self.hostnum][p]['limit'],self.linkinfo[self.hostnum][p]['delay'],\
                            self.linkinfo[self.hostnum][p]['loss'])))
                    tasks.execute(self.exec_sudo, cmd=netem_str, hosts=hostaddr)

    @staticmethod
    def find_shortest_path(graph, start, end, path=[]):
        path = path + [start]
        if start == end:
            return path
        if not graph.has_key(start):
            return None
        shortest = None
        for node in graph[start]:
            if node not in path:
                newpath = BuildNet.find_shortest_path(graph, node, end, path)
                if newpath:
                    if not shortest or len(newpath) < len(shortest):
                        shortest = newpath
        return shortest

    @staticmethod
    def find_k_equal_cost_paths(graph, start, end, paths=[]):
        for node in graph[start]:
            newpath = BuildNet.find_shortest_path(graph, node, end)
            if newpath == None:
                continue
            if len(paths)==0 or len(newpath) < len(paths[0]):
                paths = [newpath]
            if len(newpath) == len(paths[0]) and newpath not in paths:
                paths += [newpath]
        return paths

    def set_sysctl(self, key, val):
        arg = "%s=%s" %(key,val)
        cmd = "sysctl -w " + arg
        tasks.execute(self.exec_sudo, cmd=cmd, hosts=env.hosts)

    def setup_routing(self):
        iface   = self.args.interface

        # disable send_redirects and accept redirects
        #self.set_sysctl("net.ipv4.conf.all.send_redirects",0)
        #self.set_sysctl("net.ipv4.conf.all.accept_redirects",0)
        self.set_sysctl("net.ipv4.conf.%s.send_redirects" %iface,0)
        self.set_sysctl("net.ipv4.conf.%s.accept_redirects" %iface,0)
        self.set_sysctl("net.ipv4.conf.%s.forwarding" %iface, 1)

        for hostaddr in env.hosts:
            self.hostnum = self.get_host(hostaddr)

            for host in self.conf.keys():
                # skip localhost
                if host==self.hostnum:
                    continue

                paths = BuildNet.find_k_equal_cost_paths(self.conf, self.hostnum, host)
                # not all hosts may be reachable from this hosts ignore them
                if len(paths) == 0:
                    continue

                # calculate distance unlike the single path version we don't need to subtract 1 as the node itself isn't saved in the list
                dist = len(paths[0]) #equal cost so the dist from the first path suffices

                # ignore direct neighbors for now as network mask should cover them
                if dist==1:
                    continue

                for i in range(0, int(self.ipcount[host])):
                    host_ip = self.get_eip(host)

                    cmd = "ip route replace %s " %host_ip
                    if self.args.multipath:
                        for i in range(min(len(paths),self.args.maxpath)):
                            nexthop = self.get_eip(paths[i][0])
                            cmd += "nexthop via %s dev %s" %(nexthop,iface)
                    else:
                        nexthop = self.get_eip(paths[0][0])
                        cmd += "dev %s via %s metric %s" % (iface, nexthop, str(dist))
                    tasks.execute(self.exec_sudo, cmd=cmd, hosts=hostaddr)

                    # to have more control over multipath routes, add entries to distinct
                    # routing tables
                    if self.args.multipath:
                        for i in range(min(len(paths),self.args.maxpath)):
                            nexthop = self.get_eip(paths[i][0], mask=False)
                            table = self._rtoffset+i
                            cmd  ="ip route replace %s" %host_ip
                            cmd += "via %s table %s" %(nexthop,str(table))
                            tasks.execute(self.exec_sudo, cmd=cmd, hosts=hostaddr)

    def setup_user_helper(self):
        if self.args.user_scripts:
            cmd = ["%s/%s" %(self.args.user_scripts, self.hostname)]
            if os.path.isfile(cmd[0]):
                info(yellow("Executing user-provided helper program..."))
                try:
                    execute(cmd)
                except CommandFailed, inst:
                    error("Execution of %s failed." % cmd[0])
                    error("Return code %s, Error message: %s" % (inst.rc, inst.stderr))
            else:
                info(red("%s does not exist." % cmd[0]))
                info(red("Skipping user-provided helper program"))

    @parallel
    def exec_sudo(self,cmd, ok2fail=False):
        if self.args.dry_run:
            print (green(cmd))
        else:
            sudo(cmd)


    def run(self):
        """Main method of the Buildmesh object"""

        # don't print graph option --quiet was given
        if self.args.verbose or self.args.debug or self.args.dry_run:
            self.visualize(self.conf)

        if self.args.tc or self.args.dry_run:
            info(yellow("Setting up traffic shaping ... "))
            self.setup_trafficcontrol()

        if self.args.static_routes or self.args.dry_run:
            info(yellow("Setting up static routing..."))
            self.setup_routing()

        self.setup_user_helper()

    def main(self):
        sys.path.append("$HOME/Development/tcp-eval/library/")
        self.parse_options()
        self.apply_options()
        self.run()


if __name__ == "__main__":
    BuildNet().main()
