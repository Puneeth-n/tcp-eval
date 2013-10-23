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
from logging import info, debug, warn, error, critical

# twisted imports
from twisted.web import xmlrpc

class Testrpc(xmlrpc.XMLRPC):
    """Test Class for the RPC Sever"""

    def __init__(self, parent = None):
        # Call super constructor
        xmlrpc.XMLRPC.__init__(self)


    def xmlrpc_add(self, a, b):
        return a + b

    def xmlrpc_times(self, a, b):
        return a * b
