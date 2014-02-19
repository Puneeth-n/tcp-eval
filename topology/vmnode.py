#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vi:et:sw=4 ts=4

# Copyright (C) 2007 Lars Noschinski <lars.noschinski@rwth-aachen.de>
# Copyright (C) 2009 - 2013 Alexander Zimmermann <alexander.zimmermann@netapp.com>
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
import os
import re
import sys
import argparse
import textwrap
import tempfile
import socket
from logging import info, debug, warn, error

# tcp-eval imports
from common.application import Application
from common.functions import requireroot, call, execute, CommandFailed

class VMNode(Application):
    """Class to start virtual nodes on the basis of Xen"""

    def __init__(self):
        """Creates a new VMNode object"""
        
        # other object variables
        self.__vm_ids = None

        # create top-level parser and subparser
        description = textwrap.dedent("""\
                This program can create/shutdown/destroy an arbitrary number of
                XEN VMs (domUs) either locally or on a remote XEN host (dom0).
                Further, it can list all current running VMs in a network
                together with their respected owner (requires a MySQL
                database connection).""")
        Application.__init__(self, description=description)
        
        subparsers = self.parser.add_subparsers(title="subcommands",
                dest="action", help="additional help")

        # shared parser for "create/shutdown/destroy" command
        shared_parser = argparse.ArgumentParser(add_help=False)
        shared_parser.add_argument("vm_ids", metavar="id", type=int, nargs="+",
                help="execute command for domU with ID '%(metavar)s'. The ID "\
                        "will be used as a network-wide unique domU identifier")
        shared_parser.add_argument("-s", "--host", metavar="HOST",
                action="store", default="localhost", help="execute command "\
                        "on dom0 '%(metavar)s' (default: %(default)s)")
        shared_parser.add_argument("-p", "--prefix", metavar="PRE",
                action="store", default="xen-128-", help="use '%(metavar)s' as "\
                        "prefix for domU's hostname (default: %(default)s). "\
                        "As suffix the domU ID will be used")
        shared_parser.add_argument("-r", "--range", action="store_true",
                default=False, help="interprete the given domU IDs as an 'ID "\
                        "range' from 'id1' to 'id2' (default: %(default)s)")

        # create parser for "create" command
        parser_create = subparsers.add_parser("create",
                parents=[shared_parser], help="create multiple XEN domUs "\
                        "simultaneously")
        parser_create.add_argument("-o", "--root", metavar="PATH",
                action="store", default="/dev/nfs nfsroot=192.168.0.1:/usr/local/muclab/image/debian-wheezy ro boot=nfs", help = "root file system "\
                        "for domU (default: %(default)s)")
        parser_create.add_argument("-k", "--kernel", metavar="FILE",
                action="store",  default = "/mnt/boot/kernel/vmlinuz-3.13.0.david+", help = "kernel for "\
                        "domU (default: %(default)s)")
        parser_create.add_argument("-i", "--initrd", metavar="FILE",
                action="store", default="/mnt/boot/initrd/initrd.img-3.13.0.david+", help="initial "\
                        "ramdisk for domU (default: %(default)s)")
        parser_create.add_argument("-m", "--memory", metavar="#",
                action="store", type=int, default=128, help="amount of RAM "\
                        "in MB to allocate to domU (default: %(default)s)")
        create_group = parser_create.add_mutually_exclusive_group()
        create_group.add_argument("-c", "--console", action="store_true",
                default=False, help="attaches to domU console (xl -c)")
        create_group.add_argument("-y","--dry-run", action="store_true",
                default=False, help="do not start domUs automatically; "\
                        "create start file (XEN config file) only")

        # create parser for "shutdown" command
        parser_shutdown = subparsers.add_parser("shutdown",
                parents=[shared_parser], help="shutdown multiple XEN domUs "\
                        "simultaneously")

        # create parser for "destroy" command
        parser_destroy = subparsers.add_parser("destroy",
                parents=[shared_parser], help="destroy multiple XEN domUs "\
                        "simultaneously")

        # create parser for "list" command
        parser_list = subparsers.add_parser("list", help="list XEN domOs/domUs")
        parser_list.add_argument("listing", action="store", nargs="?",
                choices=("dom0", "domU", "both"), default="dom0",
                help="which node information will be show (default: "\
                        "%(default)s)")
        parser_list.add_argument("-s", "--host", metavar="HOST", nargs="+",
                action="store", default="localhost", help="hosts (dom0s) "\
                        "on which the command will be executed "\
                        "(default: %(default)s)")
        parser_list.add_argument("-p", "--prefix", metavar="PRE",
                action="store", default="xen-128-", help="use '%(metavar)s' as "\
                        "prefix for domU's hostname (default: %(default)s). "\
                        "As suffix the domU ID will be used")
        parser_list.add_argument("-i", "--ip-prefix", metavar="PRE",
                action="store", default="192.168.128.",dest="ip_prefix", 
                help="use '%(metavar)s' as "\
                        "prefix for domU's hostname (default: %(default)s). "\
                        "As suffix the domU ID will be used")

    def apply_options(self):
        """Configure XEN object based on the options form the argparser.
        On the given options perform some sanity checks
        """

        # for all commands
        Application.apply_options(self)

        # for all commands except "list"
        if not self.args.action == "list":
            # VM IDs are never negative
            for vm_id in self.args.vm_ids:
                if vm_id < 0:
                    error("A domU ID must be greater than zero")
                    sys.exit(1)

            # if desired build a range of domU IDs
            if self.args.range:
                # can only generate a range if exact two IDs are given
                if not len(self.args.vm_ids) == 2:
                    error("Can only generate an 'ID range' if exact two domU "\
                            "IDs are given")
                    sys.exit(1)
                else:
                    self.__vm_ids = range(self.args.vm_ids[0],
                            self.args.vm_ids[1] + 1)
            # for convinced copy domU IDs
            else:
                self.__vm_ids = self.args.vm_ids

        # for command "create" only
        if self.args.action == "create":
            # cannot attach console if we start multiple VMs
            if self.args.console and len(self.args.vm_ids) > 1:
                warn("Starting more than VMs with attached console is almost "\
                        "certainly not what you want. Console option is "\
                        "deactivated")
                self.args.console = False

        # for command "list" only
        if self.args.action == "list":
            # default values are strings, a command line option given by the
            # user is a list. In oder to access the argument always in the same
            # way, we convert the string into a list
            if type(self.args.host) == str:
                self.args.host = str(self.args.host).split()

    def create(self):
        """Start the desired number of domUs"""

        #FIXME
        if not self.args.host == "localhost":
            raise NotImplementedError

        # only a dry run require no root privileges
        if not self.args.dry_run:
            requireroot()

        # create desired domUs
        for index, vm_id in enumerate(self.__vm_ids):
            # build hostname
            vm_hostname = "%s%i" %(self.args.prefix, vm_id)

            # test if domU is already running
            try:
                cmd = ["ping",  vm_hostname , "-w 1"]
                execute(cmd, shell=False)
                warn("%s seems to be already running." %(vm_hostname))
                continue
            except CommandFailed:
                pass

            # create XEN config file
            info("Creating config file for domU %s" %(vm_hostname))
            first_byte = vm_id / 256
            rest_2bytes = vm_id % 256
            xen_config = textwrap.dedent("""\
                    name    = '%s'
                    ramdisk = '%s'
                    kernel  = '%s'
                    memory  = %s
                    boot    = 'n'
                    cpus    = '2-15'
                    root    = '%s'
                    dhcp    = 'on'
                    vif     = ['mac=00:16:3E:00:%02x:%02x, bridge=br0']
                    extra   = 'xencons=tty root-ro=aufs '"""
                    %(vm_hostname, self.args.initrd, self.args.kernel,
                        self.args.memory, self.args.root, 
                        first_byte, rest_2bytes))

            # dry run - only print config file and continue
            if self.args.dry_run:
                print xen_config
                if not index == len(self.__vm_ids) - 1:
                    print ""
                continue

            # write config into a file
            cfg_fd, cfg_file = tempfile.mkstemp(suffix = "-%s.cfg"
                    %(vm_hostname))
            f = open(cfg_file, "w")
            f.write(xen_config)
            f.flush()

            # create XEN command
            if self.args.console:
                cmd = "xl create -c -f %s" %(cfg_file)
            else:
                cmd = "xl create -f %s" %(cfg_file)

            # start VM
            try:
                info("Starting %s" %(vm_hostname))
                call(cmd, shell=True)
            except CommandFailed, exception:
                error("Error while starting %s" %(vm_hostname))
                error(exception)

            # close and remove config file
            f.close()
            os.remove(cfg_file)

    def shutdown(self):
        """Shutdown the desired number of domUs"""

        #FIXME
        if not self.args.host == "localhost":
            raise NotImplementedError

        # must be root
        requireroot()

        # shudown the desired number of VMs
        for vm_id in self.__vm_ids:

            # build hostname
            vm_hostname = "%s%i" %(self.args.prefix, vm_id)

            # create XEN command
            cmd = "xl shutdown %s" %(vm_hostname)

            # shutdown vm
            try:
                info("Shutting down %s" %(vm_hostname))
                call(cmd, shell=True)
            except CommandFailed, exception:
                error("Error while shutting down %s" %(vm_hostname))
                error(exception)

    def destroy(self):
        """Destroy the desired number of domUs"""

        #FIXME
        if not self.args.host == "localhost":
            raise NotImplementedError

        # must be root
        requireroot()

        # destroy the desired number of VMs
        for vm_id in self.__vm_ids:

            # build hostname
            vm_hostname = "%s%i" %(self.args.prefix, vm_id)

            # create XEN command
            cmd = "xl destroy %s" %(vm_hostname)

            # shutdown vm
            try:
                info("Destroying down %s" %(vm_hostname))
                call(cmd, shell=True)
            except CommandFailed, exception:
                error("Error while destroying %s" %(vm_hostname))
                error(exception)

    def list(self):
        """Show information about domOs/domUs"""
            
        print "VM-Name".rjust(12) , "IP".rjust(15)
        
        stdout = None

        # test if domU is already running
        try:
            cmd = ["nmap", "%s%i/%i" % (self.args.ip_prefix,1,24),"-sn"]
            stdout = execute(cmd, shell=False)
        except CommandFailed,e:
            error("Something went wrong with the call of nmap!")
            error(e)
        
        stdout = stdout[0].split('\n')
        
        name = re.findall(r'%s.\b'%self.args.prefix,str(stdout))
        ip = re.findall(r'%s.\b'%self.args.ip_prefix,str(stdout))
        for item,address in zip(name,ip):
            print str(item).rjust(12), str(address).rjust(15)
#        for line in ret.splitlines():
#        	
#        # helper function
#        def vmr_compare(x, y):
#            # only compare numerical part, works for our purpose
#            x_nr = int(filter(lambda c: c.isdigit(), x))
#            y_nr = int(filter(lambda c: c.isdigit(), y))
#            return cmp(x_nr, y_nr)
#        # show information about all dom0s
#        if self.args.listing == "dom0" or self.args.listing == "both":
#            print "Host           #Nodes     Mem   VCPUs"
#            print "-------------------------------------"
#
#            info("Collecting stats...")
#            for host in self.args.host:
#                # connect to xen on 'host' and get domains
#                self.xen_connect(host, False)
#                domains = self.xen_getDomains(True, False, False)
#
#                # in case of an error, skip this host
#                if not domains: continue
#
#                # print dom0 informations
#                print "%s \t %s \t %s \t %s" %(host, len(domains) - 1, \
#                        domains[0][11][1], domains[0][5][1])
#
#        # show information about all domUs
#        if self.args.listing == "domU" or self.args.listing == "both":
#            info("Collecting stats...")
#            
#            vm_all = dict()
#            for host in self.args.host:
#                # connect to xen on 'host' and get domains
#                self.xen_connect(host, False)
#                domains = self.xen_getDomains(True, False, False)
#
#                # in case of an error, skip this host
#                if not domains: continue
#
#                # extend list of all vmrouters by new ones
#                for entry in domains:
#                    d = dict()
#                    # skip first elem in entry
#                    for elem in entry[1:]:
#                        (key, value) = elem
#                        d[key] = value
#                    # add server name to entry
#                    d["host"] = host
#                    # skip dom0
#                    if d["domid"] == 0: continue
#                    # initialize user field
#                    d["user"] = "None"
#                    # use domain name as key
#                    key = d["name"]
#                    vm_all[key] = d
#
#            #sort by hostname
#            sorted_keyset = vm_all.keys()
#            sorted_keyset.sort(vmr_compare)
#
#            # get domU ownerships:
#            if self.args.database:
#                nodeset = ",".join(map(lambda s: "'"+s+"'", sorted_keyset))
#                if nodeset != "":
#                    cursor = self.dbconn.cursor()
#                    cursor.execute("SELECT nodes.name,created_by "\
#                            "FROM nodes,nodes_vmesh "\
#                            "WHERE nodes.nodeID=nodes_vmesh.nodeID "\
#                                "AND nodes.name IN (%s)" %(nodeset))
#                    for row in cursor.fetchall():
#                        (key, value) = row
#                        vm_all[key]["user"] = value
#
#        # print domU informations
#        print "Name          Host      User                 Mem State  Time"
#        print "------------------------------------------------------------------------------------"
#        for key in sorted_keyset:
#            entry = vm_all[key]
#            print "%s %s %s %3s %6s %s" %(entry["name"].ljust(13),\
#                    entry["host"].ljust(9), entry["user"].ljust(20),\
#                    entry["maxmem"], entry["state"], entry["cpu_time"])

    def run(self):
        # run command (create,shutdown,destroy,list)
        eval("self.%s()" %(self.args.action))

    def main(self):
        self.parse_options()
        self.apply_options()
        self.run()

if __name__ == "__main__":
    VMNode().main()

