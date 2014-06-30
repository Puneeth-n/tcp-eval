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

        # App limit 20 Mbit/s
        for scenario in self.scenarios:
            scenario['flowgrind_opts'] += ' -R s=20Mb'

        for itr in range(self.iterations):
            # Variate RRate, no congestion
            for reorder in [0,1,2,3,5,7,10,15,20,25,30,35,40]:
                self.run_measurement("reordering", "rrate", reorder, 0, 20, 20, 0, 1000, 100)

if __name__ == "__main__":
    Measurement().main()
