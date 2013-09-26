#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim:softtabstop=4:shiftwidth=4:expandtab

from measurement_class import MeasurementClass
from twisted.internet import defer

class Measurement(MeasurementClass):
    @defer.inlineCallbacks
    def run(self):
        self.gvars.opts["flowgrind_duration"] = 30

        qlen = int((2 * self.delay * self.bnbw)/11.44)+1

        # reorder, ackreor, rdelay, delay, ackloss, limit, bottleneckbw, mod
        self.later_args_list = [[2, 0, 30, self.delay, 0, None, None, "change"]]
        self.later_args_time = 15

        # reorder_mode, var, reorder, ackreor, rdelay, delay, ackloss, limit, bottleneck
        self.run_measurement("reordering", "rdelay",  2, 0, 5, self.delay, 0, qlen, self.bnbw)

if __name__ == "__main__":
    Measurement().main()
