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
        self.gvars.opts["flowgrind_duration"] = 45

        rdelay = 20
        delayStart = 100
        delayLater = 25

        qlen = int((2 * delayLater * self.bnbw)/11.44)+1

        # reorder, ackreor, rdelay, delay, ackloss, limit, bottleneckbw, mode
        self.later_args_list = [[2, 0, rdelay, delayLater, 0, qlen, self.bnbw, "change"]]
        self.later_args_time = 30

        qlen = int((2 * delayStart * self.bnbw)/11.44)+1

        # reorder_mode, var, reorder, ackreor, rdelay, delay, ackloss, limit, bottleneckbw
        yield self.run_measurement("both", "delay", 2, 0, rdelay, delayStart, 0, qlen, self.bnbw)

if __name__ == "__main__":
    Measurement().main()
