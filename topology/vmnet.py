#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vi:et:sw=4 ts=4

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

# python imports
import re
import socket
import sys
import os
import argparse
import string
import subprocess
import textwrap
import getpass
from logging import info, debug, warn, error, critical

# tcp-eval imports
from common.application import Application
from common.functions import *

class BuildVmesh(Application):
    """Setup GRE tunnels and iptables rules to simulate a mesh network with
    vmeshrouters. This script has to be executed on each vmeshrouter, which
    shall be part of the simulated network"""

    def __init__(self):
        """Creates a new BuildVmesh object"""
        # object variables
        self.conf = None
        self.confstr = None
        self.linkinfo = dict()
        self.ipcount = dict()
        self.confremote = True
        self.shapecmd_multiple = textwrap.dedent("""\
                tc class add dev %(iface)s parent 1: classid 1:%(parentNr)d%(nr)02d htb rate %(rate)smbit; \
                tc filter add dev %(iface)s parent 1: protocol ip prio 16 u32 \
                match ip protocol 47 0xff flowid 1:%(parentNr)d%(nr)02d \
                match ip dst %(dst)s""")
        self.shapecmd = textwrap.dedent("""\
                tc class add dev %(iface)s parent 1: classid 1:%(nr)d htb rate %(rate)smbit && \
                tc filter add dev %(iface)s parent 1: protocol ip prio 16 u32 \
                match ip protocol 47 0xff flowid 1:%(nr)d \
                match ip dst %(dst)s""")
        self.fabfile = textwrap.dedent("""\
                from fabric.api import *

                @parallel
                def copy_files():
                        put('%(config)s','/tmp/%(configname)s')
                
                def run_vmnet():
                        sudo('%(cmdline)s')
                
                def clean():
                        run('rm -f /tmp/*')
                """)
        self._dnsttl = 300
        self._dnskey = "o2bpYQo1BCYLVGZiafJ4ig=="
        # used routing table ids for multipath
        self._rtoffset = 300

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
        self._setting_group=self.parser.add_mutually_exclusive_group()
        self._setting_group.add_argument("-r", "--remote", action="store_true",
                default=self.confremote, help="Apply settings for all hosts in config "\
                        "(default: %(default)s)")
        self._setting_group.add_argument("-t", "--node-prefix", action="store_true",
                dest="node_prefix", default="xen-128-", 
                help="Prefix of all nodes in the topology (default: %(default)s)")
        self._setting_group.add_argument("-l", "--local", action="store_true",
                default=False,
                help="Apply just the settings for localhost")
        self.parser.add_argument("-i", "--interface", metavar="IFACE",
                action="store", default="eth1", help="Interface to use for "\
                        "the GRE tunnel (default: %(default)s)")
        self.parser.add_argument("-m", "--mcast", metavar="IP",
                action="store", default="224.66.66.66", help="Multicast IP to "\
                        "use for GRE tunnel (default: %(default)s)")
        self.parser.add_argument("-o", "--offset", metavar="NUM",
                action="store", type=int, default=0, help="Add this offset "\
                        "to all node IDs in the config file")
        self.parser.add_argument("-u", "--user-scripts", metavar="PATH",
                action="store", nargs="?", const="./config/vmnet-helper",
                dest="user_scripts",
                help="Execute user scripts for every node (default: %(const)s)")
        self.parser.add_argument("-s", "--static-routes", action="store_true",
                                 dest="static_routes",
                default=False, help="Setup static routing according to "\
                        "topology")
        self.parser.add_argument("-p", "--multipath", metavar="NUM",
                action="store", nargs="?", type=int, const=2, default=False,
                help="Set up equal cost multipath routes with maximal "\
                        "'%(metavar)s' of parallel paths (default: %(const)s)")
        self.parser.add_argument("-R", "--rate", metavar="RATE", action="store",
                help="Rate limit in mbps")
        self.parser.add_argument("-n", "--ip-prefix", metavar="PRE",
                action="store", default="192.168.128.", dest="ip_prefix", 
                help="Use to select different IP address ranges (default: %(default)s)")
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
        if self.args.local:
            self.conf = self.parse_config(self.args.config_file)

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
        
        #get the hostname of the machine where the script is executed
        self.hostname = socket.gethostname()
        # set the own number according to the hostname
        self.hostnum = int(re.findall(r'\d+',self.hostname)[0])

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
        if file == "-":
            fd = sys.stdin
        else:
            fd = open(file, 'r')

        self.confstr = list()
        for line in fd:
            self.confstr.append(line)

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

    def visualize(self, graph):
        """Visualize topology configuration"""
        info("Configured with the following topology:")
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


    def gre_ip(self, hostnum, mask = False, offset = 0):
        """Gets the gre ip for host with number "hostnum" """
        ip_address_prefix = self.args.ip_prefix

        if mask:
            return "%s.%s/16" %( ip_address_prefix, (hostnum - 1) % 254 + 1 )
        else:
            return "%s.%s" %( ip_address_prefix, (hostnum - 1) % 254 + 1 )

#necessary ?????
    def gre_net(self, mask = True):
        """Gets the gre network address"""
        ip_address_prefix = self.args.ip_prefix

        if mask:
            return "%s.0/16" %( ip_address_prefix )
        else:
            return "%s.0" %( ip_address_prefix )
#deleted mask in arguments
    def gre_broadcast(self):
        """Gets the gre broadcast network address"""
        ip_address_prefix = self.args.ip_prefix
        return "%s.255" %( ip_address_prefix )

    def gre_multicast(self, multicast, interface):
        last_ip_block = multicast[multicast.rfind('.') + 1:len(multicast)]
        net_count = self.net_num(interface)

        new_ip_block = (int(last_ip_block) + net_count - 1)%254 + 1
        return "%s.%s" %(multicast[:multicast.rfind('.')], str(new_ip_block))
    
    def getIPaddress(self, device = None):
        """Get the IP address of a specific device without the netmask. If device
           is None only the hostname will be looked up.
        """

        if device is None:
            name = self.hostname
        else:
            name = "%s.%s" %(device, self.hostname)
            
        try:
            address = socket.gethostbyname(name)
        except socket.gaierror, inst:
            error("Could not get the ipaddress of %s" % name)
            error("Return code %s, Error message: %s" % (inst.rc, inst.stderr))

        return address

    def setup_gre(self):
        public_ip = self.getIPaddress(device = None)
        gre_ip = self.gre_ip(self.hostnum, mask = True)
        gre_broadcast = self.gre_broadcast()

        try:
            iface = self.args.interface
            gre_multicast = self.gre_multicast(self.args.mcast, iface)

            info("setting up GRE Broadcast tunnel for %s" % self.hostnum )
            execute('ip tunnel del %s' % iface, True, False)
            execute('ip tunnel add %(iface)s mode gre local %(public)s remote %(mcast)s ttl 1 \
                     && ip addr add %(gre)s broadcast %(broadcast)s dev %(iface)s \
                     && ip link set %(iface)s up' %
                     {"public": public_ip, "gre": gre_ip, "iface": iface, "broadcast": gre_broadcast,
                      "mcast": gre_multicast}, True)
            for i in range(1,int(self.ipcount[self.hostnum])):
                add_gre_ip = self.gre_ip(self.hostnum, mask = True, offset = i)
                info("setting up additional GRE address %s" % add_gre_ip)
                execute('ip addr add %(gre)s broadcast %(broadcast)s dev %(iface)s' %
                        {'gre': add_gre_ip, 'iface': iface, 'broadcast': gre_broadcast}, True)
        except CommandFailed, inst:
            error("Setting up GRE tunnel %s (%s, %s) failed." % (self.hostnum, public_ip, gre_ip))
            error("Return code %s, Error message: %s" % (inst.rc, inst.stderr))


    def chorder(self, address):
        """changes the order of an ip address"""
        sa = address.split('.')
        sa.reverse()
        return ".".join(sa)

    def setup_dns(self):
        # update dns
        iface = self.args.interface
        address = self.gre_ip(self.hostnum, mask=False)
        prefix = self.args.node_prefix

        update_dns1 = "echo \"update delete %s.%s%s.umic-mesh.net A\\nupdate add %s.%s%s.umic-mesh.net %u A %s\\nsend\" | nsupdate -y rndc-key:%s" %(iface,prefix, self.hostnum, iface,prefix, self.hostnum, self._dnsttl, address, self._dnskey)
        try:
                (stdout, stderr) = execute(update_dns1)
        except CommandFailed, inst:
                error("Updating DNS entry for %s.%s%s failed." % (iface,prefix,self.hostnum))
                error("Return code %s, Error message: %s" % (inst.rc, inst.stderr))

        chaddress = self.chorder(address)
        update_dns2 = "echo \"update delete %s.in-addr.arpa PTR\\nupdate add %s.in-addr.arpa %u PTR %s.vmrouter%s\\nsend\" | nsupdate -y rndc-key:%s" %(chaddress, chaddress, self._dnsttl, iface, self.hostnum, self._dnskey)
        try:
                (stdout, stderr) = execute(update_dns2)
        except CommandFailed, inst:
                error("Updating DNS entry for %s.in-addr.arpa failed." % (chaddress))
                error("Return code %s, Error message: %s" % (inst.rc, inst.stderr))

    def setup_trafficcontrol(self):
        iface = "eth0"
        peers = self.conf.get(self.hostnum, set())
        prefix = self.args.node_prefix
        parent_num = self.net_num(self.args.interface) + 1

        # Add qdisc
        try:
            if self.args.multiple_topology or self.args.multiple_topology_reset:
                if self.args.multiple_topology_reset:
                    execute("tc qdisc del dev %s root; " % iface +
                            "tc qdisc add dev %s root handle 1: htb default 1100;" % iface
                            , True)
                else:
                    execute("tc qdisc ls dev %(iface)s | grep root | grep -o pfifo_fast | xargs --replace=STR bash -c \" \
                            tc qdisc del dev %(iface)s root; \
                            tc qdisc add dev %(iface)s root handle 1: htb default 1100;\"" % {'iface' : iface}, True)
            else:
                execute("tc qdisc del dev %s root; " % iface +
                        "tc qdisc add dev %s root handle 1: htb default 100" % iface
                        ,True)
        except CommandFailed, inst:
            error('Could not install queuing discipline')
            error("Return code %s, Error message: %s" % (inst.rc, inst.stderr))
            raise

        # Add class and filter for each peer
        i = 0
        for p in sorted(peers):
            try:
                if self.linkinfo.has_key(self.hostnum) and self.linkinfo[self.hostnum].has_key(p) and self.linkinfo[self.hostnum][p]['rate'] != '':
                    rate = self.linkinfo[self.hostnum][p]['rate']
                elif self.args.rate:
                    rate = self.args.rate
                else:
                    continue

                i+=1

                info("Limiting rate of link %s -> %s to %s mbit" % (self.hostnum,p,rate))

                netem_str = ''
                if self.args.multiple_topology or self.args.multiple_topology_reset:
                    #TODO: Can lead to problems if one destionation is reachable from serveral devices!
                    #Need to check for such links and combine them to one
                    execute(self.shapecmd_multiple % {
                        'iface' : iface,
                        'nr' : i,
                        'parentNr' : parent_num,
                        'dst' : socket.gethostbyname('%s%s' % (prefix,p)),
                        'rate' : rate}
                        ,True)
                    netem_str = 'tc qdisc add dev %s parent 1:%d%02d handle %d%02d: netem' % (iface, parent_num, i, parent_num, i)

                else:
                    execute(self.shapecmd % {
                        'iface' : iface,
                        'nr' : i,
                        'dst' : socket.gethostbyname('%s%s' % (prefix,p)),
                        'rate' : rate}
                        ,True)
                    netem_str = 'tc qdisc add dev %s parent 1:%s handle %s0: netem' % (iface, i, i)


                # netem for queue length, delay and loss
                if self.linkinfo[self.hostnum][p]['limit'] != '':
                    netem_str += ' limit %s' %self.linkinfo[self.hostnum][p]['limit']
                if self.linkinfo[self.hostnum][p]['delay'] != '':
                    netem_str += ' delay %sms' %self.linkinfo[self.hostnum][p]['delay']
                if self.linkinfo[self.hostnum][p]['loss'] != '':
                    netem_str += ' drop %s' %self.linkinfo[self.hostnum][p]['loss']

                # create netem queue only if one of the parameter is given
                if self.linkinfo[self.hostnum][p]['limit'] != '' or self.linkinfo[self.hostnum][p]['delay'] != '' or self.linkinfo[self.hostnum][p]['loss'] != '':
                    info("      Adding netem queue, limit:\'%s\', delay:\'%s\', loss:\'%s\'"
                        % (self.linkinfo[self.hostnum][p]['limit'],self.linkinfo[self.hostnum][p]['delay'],self.linkinfo[self.hostnum][p]['loss']))
                    execute(netem_str, True)

            except CommandFailed, inst:
                error('Failed to add tc classes and filters for link %s -> %s' % (self.hostnum, p))
                error("Return code %s, Error message: %s" % (inst.rc, inst.stderr))
                raise

    def setup_iptables(self):
        peers = self.conf.get(self.hostnum, set())
        prefix = self.args.node_prefix
        mcast = self.args.mcast
        iface = self.args.interface
        gre_multicast = self.gre_multicast(mcast, iface)

        mesh_name = "mesh_gre_%s_in" %(iface)


        try:
            execute('iptables -D INPUT -j %s -d %s;' %( mesh_name, gre_multicast)
                    + 'iptables -F %s;' % mesh_name
                    + 'iptables -X %s;' % mesh_name
                    + 'iptables -N %s' % mesh_name, True)
        except CommandFailed, inst:
            error('Could not create iptables chain "%s"' % mesh_name)
            error("Return code %s, Error message: %s" % (inst.rc, inst.stderr))
            raise

        for p in peers:
            try:
                info("Add iptables entry: %s reaches %s" % (p, self.hostnum))
                execute('iptables -A %s -s %s%s -j ACCEPT' %(mesh_name, prefix, p), True)
            except CommandFailed, inst:
                error('Adding iptables entry "%s reaches %s" failed.' % (p, self.hostnum))
                error("Return code %s, Error message: %s" % (inst.rc, inst.stderr))
                raise

        try:
            execute("iptables -A %s -j DROP &&" % mesh_name
                    + "iptables -A INPUT -d %s -j %s" %(gre_multicast, mesh_name), True)
        except CommandFailed, inst:
            error("Inserting iptables chain into INPUT failed.")
            error("Return code %s, Error message: %s" % (inst.rc, inst.stderr))
            raise

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
                newpath = BuildVmesh.find_shortest_path(graph, node, end, path)
                if newpath:
                    if not shortest or len(newpath) < len(shortest):
                        shortest = newpath
        return shortest

    @staticmethod
    def find_k_equal_cost_paths(graph, start, end, paths=[]):
        for node in graph[start]:
            newpath = BuildVmesh.find_shortest_path(graph, node, end)
            if newpath == None:
                continue
            if len(paths)==0 or len(newpath) < len(paths[0]):
                paths = [newpath]
            if len(newpath) == len(paths[0]) and newpath not in paths:
                paths += [newpath]
        return paths

    def set_sysctl(self, key, val):
        arg = "%s=%s" %(key,val)
        cmd = ["sysctl","-w",arg]
        try:
            execute(cmd, shell=False)
        except CommandFailed, inst:
            error('Failed sysctl %s failed.' %arg)
            error("Return code %s, Error message: %s" % (inst.rc, inst.stderr))
            raise

    def setup_routing(self):
        iface   = self.args.interface

        # disable send_redirects and accept redirects
        self.set_sysctl("net.ipv4.conf.all.send_redirects",0)
        self.set_sysctl("net.ipv4.conf.all.accept_redirects",0)
        self.set_sysctl("net.ipv4.conf.%s.send_redirects" %iface,0)
        self.set_sysctl("net.ipv4.conf.%s.accept_redirects" %iface,0)
        self.set_sysctl("net.ipv4.conf.%s.forwarding" %iface, 1)

        for host in self.conf.keys():
            # skip localhost
            if host==self.hostnum:
                continue

            paths = BuildVmesh.find_k_equal_cost_paths(self.conf, self.hostnum, host)
            # not all hosts may be reachable from this hosts ignore them
            if len(paths) == 0:
                continue

            # calculate distance unlike the single path version we don't need to subtract 1 as the node itself isn't saved in the list
            dist = len(paths[0]) #equal cost so the dist from the first path suffices

            # ignore direct neighbors for now as network mask should cover them
            if dist==1:
                continue

            for i in range(0, int(self.ipcount[host])):
                host_ip = self.gre_ip(host, mask = False, offset = i)

                cmd = ["ip", "route", "replace", host_ip]
                if self.args.multipath:
                    for i in range(min(len(paths),self.args.maxpath)):
                        nexthop = self.gre_ip(paths[i][0], mask=False)
                        cmd += ["nexthop", "via", nexthop, "dev", iface]
                else:
                    nexthop = self.gre_ip(paths[0][0], mask=False)
                    cmd += ["dev", iface, "via", nexthop, "metric", str(dist)]
                try:
                    execute(cmd, shell=False)
                except CommandFailed, inst:
                    error('Adding routing entry for host %s failed.' % host_ip)
                    error("Return code %s, Error message: %s" % (inst.rc, inst.stderr))
                    raise

                # to have more control over multipath routes, add entries to distinct
                # routing tables
                if self.args.multipath:
                    for i in range(min(len(paths),self.args.maxpath)):
                        nexthop = self.gre_ip(paths[i][0], mask=False)
                        table = self._rtoffset+i
                        cmd  = ["ip", "route", "replace", host_ip]
                        cmd += ["via", nexthop, "table", str(table)]
                        try:
                            execute(cmd, shell=False)
                        except CommandFailed, inst:
                            error('Failed adding entry for host %s to table %s.' % (host_ip, table))
                            error("Return code %s, Error message: %s" % (inst.rc, inst.stderr))
                            raise

    def setup_user_helper(self):
        if self.args.user_scripts:
            cmd = ["%s/%s" %(self.args.user_scripts, self.hostname)]
            if os.path.isfile(cmd[0]):
                info("Executing user-provided helper program...")
                try:
                    execute(cmd)
                except CommandFailed, inst:
                    error("Execution of %s failed." % cmd[0])
                    error("Return code %s, Error message: %s" % (inst.rc, inst.stderr))
            else:
                info("%s does not exist." % cmd[0])
                info("Skipping user-provided helper program")
                

    def run(self):
        """Main method of the Buildmesh object"""

        # Apply settings on remote hosts
        if self.args.remote and not self.args.local:
            requireNOroot()

            # don't print graph option --quiet was given
            if self.args.verbose or self.args.debug:
                self.visualize(self.conf)
            # stop here if it's a dry run
            if self.args.dry_run:
                sys.exit(0)
            hosts = list()
            #base cmd line to execute on the remote machine
            fabcmd = 'python $HOME/tcp-eval/topology/vmnet.py /tmp/%s -i %s -l' % (os.path.basename(self.args.config_file),self.args.interface)
            # call script on all vmrouter involved
            for host in self.conf.keys():
                h = "%s%s" % (self.args.node_prefix,host)
                info("Configuring host %s" % h)
                hosts.append(h)
            
            if self.args.debug:
                fabcmd += " --debug"

            if self.args.static_routes:
                fabcmd += " --staticroutes"

            if self.args.multipath:
                fabcmd += " --multipath"
                fabcmd += " --maxpath"
                fabcmd += " "+str(self.args.maxpath)

            if self.args.rate:
                fabcmd += " -R"
                fabcmd += " "+self.args.rate

            if self.args.user_scripts:
                fabcmd += " --userscripts-path=%s" %self.args.user_scripts

            if self.args.offset:
                fabcmd += " -o"
                fabcmd += " "+str(self.args.offset)

            if self.args.ip_prefix > 0:
                 fabcmd += " --ipprefix"
                 fabcmd += " "+str(self.args.ip_prefix)

            if self.args.multiple_topology:
                fabcmd += " -e"

            if self.args.multiple_topology_reset:
                fabcmd += " -E"
            
            #clean up old fabric file before building the new one if existend
            if os.path.isfile('/tmp/fabfile.py'):
                os.remove('/tmp/fabfile.py')
            
            fabricfile = open('/tmp/fabfile.py','w')
            fabricfile.write(self.fabfile % {
                            'config' : os.path.abspath(self.args.config_file),
                            'configname' :  os.path.basename(self.args.config_file),
                            'cmdline' : fabcmd})
            fabricfile.flush()
            fabricfile.close()
            
            #ask for password to make the execution more comfortable
            passwd = getpass.getpass("Please enter your sudo password for execution: ")
            
            #copy the configuration file on every host
            info('Calling: %s' % ('fab -f /tmp/fabfile.py  -H %s -P copy_files' % ",".join(hosts)))
            call('fab -f /tmp/fabfile.py -p %s -H %s copy_files' % (passwd, ",".join(hosts)))
            
            #execute this script on every given node
            info('Calling: %s' % ('fab -f /tmp/fabfile.py -H %s run_vmnet' % ",".join(hosts)))
            call('fab -f /tmp/fabfile.py -p %s -H %s run_vmnet' % (passwd, ",".join(hosts)))
        # Apply settings on local host
        else:
            info("Setting up GRE tunnel ...")
            self.setup_gre()

            info("Update DNS entries ...")
            self.setup_dns()

            info("Setting up iptables rules ... ")
            self.setup_iptables()

            info("Setting up traffic shaping ... ")
            self.setup_trafficcontrol()

            if self.args.staticroutes:
                info("Setting up static routing...")
                self.setup_routing()

            self.setup_user_helper()

    def main(self):
        sys.path.append("$HOME/tcp-eval/library/")
        self.parse_options()
        self.apply_options()
        self.run()


if __name__ == "__main__":
    BuildVmesh().main()
