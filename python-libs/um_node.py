#!/usr/bin/env python
# -*- coding: utf-8 -*-

# python imports
import os, re
from socket import gethostname

# umic-mesh imports
from um_config import *

class Node(object):
    "Provides access to configuration infos about a certain host (or a node type)"

    def __init__(self, hostname = None, type = None):
        """ Creates a new Node object.

        If hostname is None, gethostname() is used. The "NODETYPE" will
        derived from the hostname and can be overriden by setting the
        parameter nodetype.

        If no nodetype can be derived, a NodeTypeException is raised.
        """

        # object variables
        self._hostname = ''
        self._type = ''

        if hostname:
            self._hostname = hostname
        else:
            self._hostname = socket.gethostname()


        if type:

            if type in nodeinfos:
                self._type = type
            else:
                raise NodeTypeException('Invalid value for NODETYPE'
                        'Please set it to one of %s.'% nodeinfos.keys())

        else:
            # Compute list of nodetypes which match for hostname
            type_list = []
            for (nodetype, nodeinfo) in nodeinfos.iteritems():
                if re.match(nodeinfo['hostnameprefix'], self._hostname):
                    type_list.append(nodetype)

            if len(type_list) == 1:
                self._type = type_list[0]
            elif len(type_list) == 0:
                raise NodeTypeException('Cannot derived NODETYPE from'
                        ' hostname, as there are no types with fitting'
                        ' "hostnameprefix" entries: %s' % type_list)
            else:
                raise NodeTypeException('Cannot derived NODETYPE from'
                        ' hostname, as there are multiple types with fitting'
                        ' hostnameprefix" entries: %s' % type_list)


    def type(self):
        "Returns the nodetype of the node"

        return self._type


    def hostname(self):
        "Returns the hostname of the node"

        return self._hostname


    def info(self):
        "Returns the nodeinfos of the node"

        return nodeinfos[self._type]


    def hostnameprefix(self):
        "Derives the hostnameprefix from the hostname"

        return self.info()['hostnameprefix']


    def number(self):
        "Derives the nodenumber from the hostname"

        return re.sub(self.hostnameprefix(), '', self.hostname())


    def ipconfig(self, device = 'ath0'):
        "Get the IP of a specific device including the netmask in slashed notation"

        meshdevs   = self.info()['meshdevices']
        devicecfg  = meshdevs[device]
        activecfg  = deviceconfig[devicecfg]
        address    = re.sub('@NODENR', self.number(), activecfg['address'])

        return address


    def ipaddress(self, device = 'ath0'):
        "Get the IP of a specific device without the netmask of the node"

        ipconfig = self.ipconfig()
        raw_address = ipconfig[:ipconfig.find('/')]

        return raw_address


    def imageinfo(self):
        "Returns the imageinfos for the node"

        return imageinfos[self.info()['imagetype']]


    def imagepath(self):
        "Returns the imagepath for the node"

        nodeinfo = self.info()
        return "%s/%s.img/%s" % (imageprefix, nodeinfo['imagetype'], nodeinfo['imageversion'])



class NodeTypeException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return repr(self.msg)
