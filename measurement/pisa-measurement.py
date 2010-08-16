#!/usr/bin/env python2.5
# -*- coding: utf-8 -*-
# vim:softtabstop=4:shiftwidth=4:expandtab

# Script to read quota settings from ldap and apply these to the filesystem.
#
# Copyright (C) 2007 Arnd Hannemann <arnd@arndnet.de>
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
from twisted.internet import defer, reactor

#umic-mesh imports
from um_measurement import measurement, tests
from um_node import Node

class PisaMeasurement(measurement.Measurement):
    """This Measurement has serveral scenarios to test: bluberdibbblub"""

    def __init__(self):
        """Constructor of the object"""
        self.logprefix=""
        measurement.Measurement.__init__(self)

    def set_option(self):
        """Set options"""
        measurement.Measurement.set_option(self)

    @defer.inlineCallbacks
    def run(self):
        """Main method"""

        # common options used for all tests
        opts = dict( ping_size        = 100,
                     ping_interval    = 0.2,
                     ping_count       = 30,
                     thrulay_cc       = "reno",
                     thrulay_duration = 15 )

        # all meshrouter in the mesh
        all = map(lambda x: "mrouter%s" %x, range(1,10))

        # inner loop configurations
        runs = [ dict( run_label=r'35\\sra36', src = 35, dst = 36 ),
                 dict( run_label=r'35\\sra27', src = 35, dst = 37 ),
                 ]
        runs.extend(self.generate_pair_permutations([1,2,3,4]))

        # repeat loop
        iterations  = range(1,99)

        # outer loop with different scenario settings
        scenarios   = [ dict( scenario_label = "baserate_1M") ]

        yield self.remote_execute_many(all,"hostname")

        for scenario_no in range(len(scenarios)):
            for it in iterations:
                for run_no in range(len(runs)):
                    # set logging prefix, tests append _testname
                    self.logprefix="i%03u_s%u_r%u" % (it, scenario_no, run_no)

                    # merge parameter configuration for the tests
                    kwargs = dict()
                    kwargs.update(runs[run_no])
                    kwargs.update(opts)
                    kwargs.update(scenarios[scenario_no])

                    # set source and dest for tests
                    kwargs['thrulay_src'] = kwargs['ping_src'] = kwargs['src']
                    kwargs['thrulay_dst'] = kwargs['ping_dst'] = kwargs['dst']

                    # actually run tests
                    yield self.run_test(tests.test_ping, **kwargs)
                    yield self.run_test(tests.test_thrulay, **kwargs)

        yield self.tear_down()
        reactor.stop()

    def main(self):
        self.parse_option()
        self.set_option()
        self.run()
        reactor.run()


if __name__ == "__main__":
    PisaMeasurement().main()

