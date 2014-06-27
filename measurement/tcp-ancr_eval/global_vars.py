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

class global_vars:
    def __init__(self):
        self.testbed_profile = "muclab_puneeth"

        # this must be adjusted for the specific measurement
        self.node_type = "fas3270"

        # repeat loop
        #self.iterations  = range(10)

        # inner loop with different scenario settings
        self.scenarios = [
                           dict( scenario_label = "Native Linux DS",flowgrind_cc="reno",flowgrind_opts=["-O","s=TCP_REORDER_MODULE=native","-A","s"] ),
                           dict( scenario_label = "Native Linux TS",flowgrind_cc="reno",flowgrind_opts=["-O","s=TCP_REORDER_MODULE=native","-A","s"] ),
                           dict( scenario_label = "TCP-aNCR CF", flowgrind_cc="reno",flowgrind_opts=["-O","s=TCP_REORDER_MODULE=ancr",   "-O", "s=TCP_REORDER_MODE=1","-A","s"]),
                           dict( scenario_label = "TCP-aNCR AG", flowgrind_cc="reno",flowgrind_opts=["-O","s=TCP_REORDER_MODULE=ancr",   "-O", "s=TCP_REORDER_MODE=2","-A","s"]),
                         ]
