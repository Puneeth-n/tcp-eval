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
import ConfigParser
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

        # load config file or generate initial config file
        self.config = self.make_config()
        
        # create top-level parser and subparser
        description = textwrap.dedent("""\
                This program can create/shutdown/destroy an arbitrary number of
                XEN VMs (domUs) either locally or on a remote XEN host (dom0).
                Further, it can list all current running VMs in a network.""")
        # create a epilog
        epilog = textwrap.dedent("""\
                Configuration File: You can generate a initial-configuration file 
                in the same directory by executing the script with no arguments. In 
                this configuration file you can specify all the default values 
                used by this programm. Just delete vmnode.conf if you want to 
                generate a new initial-configuration file.""")
        Application.__init__(self, description=description, epilog=epilog)
        
        subparsers = self.parser.add_subparsers(title="subcommands",
                dest="action", help="additional help")

        # shared parser for "create/shutdown/destroy" command
        shared_parser = argparse.ArgumentParser(add_help=False)
        shared_parser.add_argument("vm_ids", metavar="id", type=int, nargs="+",
                help="execute command for domU with ID '%(metavar)s'. The ID "\
                        "will be used as a network-wide unique domU identifier")
        shared_parser.add_argument("-s", "--host", metavar="HOST", dest="host",
                action="store", default=self.config.get('SharedConf', 'host'), help="execute command "\
                        "on dom0 '%(metavar)s' (default: %(default)s)")
        shared_parser.add_argument("-p", "--prefix", metavar="PRE",
                action="store", default=self.config.get('SharedConf', 'prefix'), help="use '%(metavar)s' as "\
                        "prefix for domU's hostname (default: %(default)s). "\
                        "As suffix the domU ID will be used")
        shared_parser.add_argument("-r", "--range", action="store_true",
                default=self.config.getboolean('SharedConf', 'range'), help="interprete the given domU IDs as an 'ID "\
                        "range' from 'id1' to 'id2' (default: %(default)s)")

        # create parser for "create" command
        parser_create = subparsers.add_parser("create",
                parents=[shared_parser], help="create multiple XEN domUs "\
                        "simultaneously")
        parser_create.add_argument("-o", "--root", metavar="PATH",
                action="store", default=self.config.get('Create', 'root'), help = "root file system "\
                        "for domU (default: %(default)s)")
        parser_create.add_argument("-k", "--kernel", metavar="FILE",
                action="store",  default =self.config.get('Create', 'kernel'), help = "kernel for "\
                        "domU (default: %(default)s)")
        parser_create.add_argument("-i", "--initrd", metavar="FILE",
                action="store", default=self.config.get('Create', 'initrd'), help="initial "\
                        "ramdisk for domU (default: %(default)s)")
        parser_create.add_argument("-m", "--memory", metavar="#",
                action="store", type=int, default=self.config.getint('Create', 'memory'), help="amount of RAM "\
                        "in MB to allocate to domU (default: %(default)s)")
        parser_create.add_argument("-b", "--boot", metavar="(c|d|n)", choices=("c", "d", "n"),
                action="store", default=self.config.get('Create', 'boot'), help="sets the boot "\
                        "device which is \"c\" for cd-rom, \"d\" for disk and \"n\" for network (default: %(default)s)")
        parser_create.add_argument("-z", "--cpus", metavar="RANGE",
                action="store", default=self.config.get('Create', 'cpus'), help="list of which "\
                        "cpus the the guest is allowed to run on (default: %(default)s)")
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
        parser_list.add_argument("-i", "--ip-prefix", metavar="PRE",
                action="store", default=self.config.get('List', 'ip_prefix'),dest="ip_prefix", 
                help="use '%(metavar)s' as "\
                        "prefix for domU's hostname (default: %(default)s). "\
                        "As suffix the domU ID will be used")
        parser_list.add_argument("-t", "--vm-host", metavar="HOST", dest="vm_host",
                action="store", default=self.config.get('List', 'host'), help="execute command "\
                        "on dom0 '%(metavar)s' (default: %(default)s)")
        parser_list.add_argument("-x", "--vm-prefix", metavar="PRE", dest="vm_prefix",
                action="store", default=self.config.get('List', 'prefix'), help="use '%(metavar)s' as "\
                        "prefix for domU's hostname (default: %(default)s). "\
                        "As suffix the domU ID will be used")

    def make_config(self):
        Config = ConfigParser.ConfigParser()
        if os.path.isfile('vmnode.conf'):
            Config.read('vmnode.conf')
        else:
            cfgfile = open('vmnode.conf','w+')
            
            Config.add_section('SharedConf')
            Config.set('SharedConf','host','localhost')
            Config.set('SharedConf','prefix','prefix-')
            Config.set('SharedConf','range','False')
            
            Config.add_section('Create')
            Config.set('Create','root','/dev/nfs nfsroot=<server>:/<root-file-system> ro boot=nfs')
            Config.set('Create','kernel','./vmlinuz')
            Config.set('Create','initrd','./initrd.img')
            Config.set('Create','memory','128')
            Config.set('Create','boot','n')
            Config.set('Create','cpus','2-15')
    
            Config.add_section('List')
            Config.set('List','listing','dom0')
            Config.set('List','ip_prefix','192.186.0.')
            Config.set('List','host','localhost')
            Config.set('List','prefix','prefix-')
            
            Config.write(cfgfile)
            Config.readfp(cfgfile)
            cfgfile.flush()
            cfgfile.close()

        
        return Config
        
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
                if vm_id < 2:
                    error("A domU ID must be greater than zero and greater than 1 because 1 is reserved for the host becaus of an ip-matter")
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
            if type(self.args.vm_host) == str:
                self.args.vm_host = str(self.args.vm_host).split()

    #This is muclab specific and should be replaced by a more generic way
    def get_host(self):
        hostname = socket.gethostname()
        
        host = None
        
        if "one" in hostname:
            host = 1
        elif "two" in hostname:
            host = 2
        elif "three" in hostname:
            host = 3
        elif "four" in hostname:
            host = 4
        elif "five" in hostname:
            host = 5
        elif "six" in hostname:
            host = 6
        
        return host
        

    def create(self):
        """Start the desired number of domUs"""

        #FIXME
        if not self.args.host == "localhost":
            raise NotImplementedError

        host = self.get_host()

        # only a dry run require no root privileges
        if not self.args.dry_run:
            requireroot()

        # create desired domUs
        for index, vm_id in enumerate(self.__vm_ids):
            # build hostname
            vm_hostname = "%s%s-%i" %(self.args.prefix, host, vm_id)

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
            xen_config = textwrap.dedent("""\
                    name    = '%s'
                    ramdisk = '%s'
                    kernel  = '%s'
                    memory  = %s
                    boot    = '%s'
                    cpus    = '%s'
                    root    = '%s'
                    dhcp    = 'on'
                    vif     = ['mac=00:16:3E:%02x:%02x:00, bridge=br0']
                    extra   = 'xencons=tty root-ro=aufs '"""
                    %(vm_hostname, self.args.initrd, self.args.kernel,
                        self.args.memory,self.args.boot,self.args.cpus, self.args.root, 
                        host, vm_id))

            # dry run - only print config file and continue
            if self.args.dry_run:
                print xen_config
                if not index == len(self.__vm_ids) - 1:
                    print ""
                continue

            # write config into a file
            cfg_fd, cfg_file = tempfile.mkstemp(suffix = "-%s.cfg" %(vm_hostname))
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
            vm_hostname = "%s%s-%i" %(self.args.prefix, self.get_host(), vm_id)

            # create XEN command
            cmd = "xl shutdown %s" %(vm_hostname)

            # shutdown vm
            try:
                info("Shutting down %s" %(vm_hostname))
                call(cmd, shell=True)
                info("Successfully shut down %s" % (vm_hostname))
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
            vm_hostname = "%s%s-%i" % (self.args.prefix, self.get_host(), vm_id)

            # create XEN command
            cmd = "xl destroy %s" % (vm_hostname)

            # shutdown vm
            try:
                info("Destroying down %s" %(vm_hostname))
                call(cmd, shell=True)
                info("Successfully destroyed %s"%(vm_hostname))
            except CommandFailed, exception:
                error("Error while destroying %s" %(vm_hostname))
                error(exception)

    def list(self):
        """Show information about domOs/domUs"""
        requireroot()
        print "DOM0".rjust(10), "VM-Name".rjust(20) , "IP".rjust(20), "MAC".rjust(20)
        
        stdout = None
        #if it is not localhost we first have to determine which ip-adresses the hosts have
        if self.args.vm_host[0] != "localhost":
            for host in self.args.vm_host[0].split(','):
                #search for the ip-adresses of the hosts
                try:
                    (stdout,stderr) = execute(['host',host],shell=False)
                except CommandFailed,e:
                    error("Something went wrong with the call of host!")
                    error(e)
                    error(stderr)
                #get the ip-address out of the response
                ip_address = re.findall(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', stdout )
                # scan the management network the dom0 is in
                try:
                    cmd = ["nmap", "%s/%s" % (ip_address[0],24),"-sn"]
                    (stdout,stderr) = execute(cmd, shell=False)
                except CommandFailed,e:
                    error("Something went wrong with the call of nmap!")
                    error(e)
                
                ips = re.findall(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', stdout )
                macs = re.findall(r'(([0-9A-F]{2}:){5}([0-9A-F]{2}))', stdout )
                
                for ip,mac in zip(ips,macs):
                    if ip.endswith("1"):
                        print "host".rjust(10), "".rjust(20),str(ip).rjust(20),str(mac[0]).rjust(20)
                    elif not ip.endswith("254") or ip.endswith("255"):
                        print "".rjust(10), "".rjust(20), str(ip).rjust(20), str(mac[0]).rjust(20)
        else:
            print "host".rjust(10), "is".rjust(20),"local".rjust(20),"host".rjust(20)
            try:
                cmd = ["nmap", "%s%s/%s" % (self.args.ip_prefix,1,24),"-sn"]
                (stdout,stderr) = execute(cmd, shell=False)
            except CommandFailed,e:
                error("Something went wrong with the call of nmap!")
                error(e)
            
            ips = re.findall(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', stdout )
            macs = re.findall(r'(([0-9A-F]{2}:){5}([0-9A-F]{2}))', stdout )
            
            for ip,mac in zip(ips,macs):
                if not ip.endswith("254") or ip.endswith("255"):
                    print "".rjust(10), "".rjust(20), str(ip).rjust(20), str(mac[0]).rjust(20)
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

