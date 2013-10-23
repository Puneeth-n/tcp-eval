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

from measurement_class import MeasurementClass
from twisted.internet import defer

class Measurement(MeasurementClass):
    @defer.inlineCallbacks
    def run(self):

        # App limit 20 Mbit/s
        for scenario in self.gvars.scenarios:
            scenario['flowgrind_opts'].extend(['-R', 's=20M'])

        # Variate ACKLoss, no congestion
        for ackloss in [0,1,2,3,5,7,10,15,20,25,30,35,40]:

            # reorder_mode, var, reorder, ackreor, rdelay, delay, ackloss, limit, bottleneckbw
            yield self.run_measurement("reordering", "ackloss", 2, 0, self.delay, self.delay, ackloss, 1000, 100)

if __name__ == "__main__":
    Measurement().main()
