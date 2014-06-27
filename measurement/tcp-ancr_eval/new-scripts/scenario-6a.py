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

from measurement_class_new import TcpaNCRMeasurement

class Measurement(TcpaNCRMeasurement):
    def run(self):
        self.first_run = True
        self.gvars.opts["flowgrind_duration"] = 45

        qlen = int((2 * self.delay * self.bnbw)/11.44)+1

        # reorder, ackreor, rdelay, delay, ackloss, limit, bottleneckbw, mode
        self.later_args_list = [[40, 0, self.delay, self.delay, 0, None, None, "change"]]
        self.later_args_time = 15

        # reorder_mode, var, reorder, ackreor, rdelay, delay, ackloss, limit, bottleneckbw
        self.run_measurement("reordering", "rrate", 1, 0, self.delay, self.delay, 0, qlen, self.bnbw)

if __name__ == "__main__":
    Measurement().main()
