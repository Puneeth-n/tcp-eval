#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim:softtabstop=4:shiftwidth=4:expandtab

# python imports
import os
import os.path
from logging import info, debug, warn, error
from sqlite3 import dbapi2 as sqlite
import numpy
import scipy.stats
import sys

# umic-mesh imports
from um_functions import call
from um_analysis.analysis import Analysis
from um_gnuplot import UmGnuplot, UmLinePointPlot

class ReorderingAnalysis(Analysis):
    """Application for analysis of flowgrind results.
       It needs flowlogs produced by the -tcp-more-info branch to fully work.
       Usually, you won't call this app directly, but use
       vmesh_dumbbell_flowgrind_complete_test.pl instead."""

    def __init__(self):
        Analysis.__init__(self)

        self.parser.set_usage("Usage:  %prog [options]\n"\
                              "Creates graphs showing thruput, frs and rtos over the "\
                              "variable given by the option -V.\n"\
                              "For this all flowgrind logs out of input folder are used "\
                              "which have the type given by the parameter -T.")

        self.parser.add_option('-V', '--variable', metavar="Variable",
                         action = 'store', type = 'string', dest = 'variable',
                         help = 'The variable of the measurement [bnbw|qlimit|rrate|rdelay].')
        self.parser.add_option('-T', '--type', metavar="Type",
                         action = 'store', type = 'string', dest = 'rotype',
                         help = 'The type of the measurement [reordering|congestion|both].')
        self.parser.add_option('-E', '--plot-error', metavar="PlotError",
                         action = 'store_true', dest = 'plot_error',
                         help = "Plot error bars")

        self.parser.add_option('-d', '--dry-run',
                        action = "store_true", dest = "dry_run",
                        help = "Test the flowlogs only")

        self.plotlabels = dict()
        self.plotlabels["bnbw"]    = r"bottleneck bandwidth [$\\si[per=frac,fraction=nice]{\\Mbps}$]";
        self.plotlabels["qlimit"]  = r"bottleneck queue length [packets]";
        self.plotlabels["rrate"]   = r"reordering rate [$\\si{\\percent}$]";
        self.plotlabels["rdelay"]  = r"reordering delay [$\\si{\\milli\\second}$]";
        self.plotlabels["rtos"]    = r"RTO retransmissions [$\\#$]";
        self.plotlabels["frs"]     = r"fast retransmissions [$\\#$]";
        self.plotlabels["thruput"] = r"throughput [$\\si[per=frac,fraction=nice]{\\Mbps}$]";


    def set_option(self):
        "Set options"
        Analysis.set_option(self)

        if not self.options.variable:
            error("Please provide me with the variable and type of the measurement!")
            sys.exit(1)
        if self.options.variable != "rrate" and self.options.variable != "rdelay" and self.options.variable != "qlimit" and self.options.variable != "bnbw":
            error("I did not recognize the variable you gave me!")
            sys.exit(1)
        if self.options.rotype != "reordering" and self.options.rotype != "congestion" and self.options.rotype != "both":
            error("I did not recognize the type you gave me!")
            sys.exit(1)


    def onLoad(self, record, iterationNo, scenarioNo, runNo, test):
        dbcur = self.dbcon.cursor()

        recordHeader   = record.getHeader()
        src            = recordHeader["flowgrind_src"]
        dst            = recordHeader["flowgrind_dst"]
        run_label      = recordHeader["run_label"]
        scenario_label = recordHeader["scenario_label"]
        variable       = recordHeader["testbed_param_variable"]
        reordering     = recordHeader["testbed_param_reordering"]
        qlimit         = int(recordHeader["testbed_param_qlimit"])
        rrate          = int(recordHeader["testbed_param_rrate"])
        rdelay         = int(recordHeader["testbed_param_rdelay"])

        try:
            bnbw       = int(recordHeader["testbed_param_bottleneckbw"])
        except KeyError:
            bnbw       = "NULL"

        # test_start_time was introduced later in the header, so its not in old test logs
        try:
            start_time = int(float(recordHeader["test_start_time"]))
        except KeyError:
            start_time = 0
        rtos           = record.calculate("total_rto_retransmits")
        frs            = record.calculate("total_fast_retransmits")
        thruput        = record.calculate("thruput")

        if not thruput:
            if not self.failed.has_key(run_label):
                self.failed[run_label] = 1
            else:
                self.failed[run_label] = self.failed[run_label]+1
            return

        try:
            rtos = int(rtos)
        except TypeError, inst:
            rtos = "NULL"

        try:
            frs = int(frs)
        except TypeError, inst:
            frs = "NULL"

        # check for lost SYN or long connection establishing
        c = 0
        flow_S = record.calculate("flows")[0]['S']
        for tput in flow_S['tput']:
            if tput == 0.000000:
                c += 1
            else: break
        if flow_S['end'][c] > 1:
            warn("Long connection establishment (%ss): %s" %(flow_S['end'][c], record.filename))



        dbcur.execute("""
                      INSERT INTO tests VALUES ("%s", "%s", %s, %u, %u, %u, %s, %s, %u, %u, %u, "%s", "%s", %f, %u, "$%s$", "%s", "%s")
                      """ % (variable, reordering, bnbw, qlimit, rrate, rdelay, rtos, frs, iterationNo, scenarioNo, runNo, src, dst, thruput,
                             start_time, run_label, scenario_label, test))


    def generateYOverXLinePlot(self, y):
        """Generates a line plot of the DB column y over the DB column x
           reordering rate. One line for each scenario.
        """

        x      = self.options.variable
        rotype = self.options.rotype

        dbcur = self.dbcon.cursor()

        # get all scenario labels
        dbcur.execute('''
            SELECT DISTINCT scenarioNo, scenario_label
            FROM tests ORDER BY scenarioNo'''
        )
        scenarios = dict()
        for row in dbcur:
            (key,val) = row
            scenarios[key] = val

        outdir = self.options.outdir
        p = UmLinePointPlot("%s_%s_over_%s" % (rotype, y, x))
        p.setXLabel(self.plotlabels[x])
        p.setYLabel(self.plotlabels[y])

        max_y_value = 0
        for scenarioNo in scenarios.keys():
            # 1) aggregate the iterations of each run of one scenario under one testbed
            #    configuration by avg() to get the average total y of such flows
            # 2) sum() up these average values of each scenario under one testbed
            #    configuration to get the total average y of one scenario under one
            #    testbed configuration
            query = '''
                SELECT %s, sum(avg_y) AS total_avg_y
                FROM
                (
                    SELECT %s, runNo, avg(%s) AS avg_y
                    FROM tests
                    WHERE scenarioNo=%u AND variable='%s' AND reordering='%s'
                    GROUP BY %s, runNo
                )
                GROUP BY %s
                ORDER BY %s
            ''' % (x, x, y, scenarioNo, x, rotype, x, x, x)
            debug("\n\n" + query + "\n\n")
            dbcur.execute(query)

            plotname = "%s_%s_over_%s_s%u" % (rotype, y, x, scenarioNo)
            valfilename = os.path.join(outdir, plotname+".values")

            info("Generating %s..." % valfilename)
            fhv = file(valfilename, "w")

            # header
            fhv.write("# %s %s\n" % (x, y))

            # data
            success = False
            for row in dbcur:
                (x_value, y_value) = row
                try:
                    if self.options.plot_error:
                        stddev = self.calculateStdDev(y, x_value, scenarioNo)
                        fhv.write("%u %f %f\n" %(x_value, y_value, stddev))
                    else:
                        fhv.write("%u %f\n" %(x_value, y_value))
                except TypeError:
                    continue
                success = True
                if y_value > max_y_value:
                    max_y_value = y_value
            fhv.close()
            if not success:
                return

            # plot
            if self.options.plot_error:
                p.plotYerror(valfilename, scenarios[scenarioNo], linestyle=scenarioNo + 1, using="1:2:3")
                p.plot(valfilename, title="", linestyle=scenarioNo + 1, using="1:2")
            else:
                p.plot(valfilename, scenarios[scenarioNo], linestyle=scenarioNo + 1, using="1:2")

        # make room for the legend
        if max_y_value:
            p.setYRange("[*:%u]" % int(max_y_value + ((25 * max_y_value) / 100 )))

        p.save(self.options.outdir, self.options.debug, self.options.cfgfile)


    def calculateStdDev(self, y, x_value, scenarioNo):
        """Calculates the standarddeviation for the values of the YoverXPlot
        """

        x      = self.options.variable
        rotype = self.options.rotype
        dbcur = self.dbcon.cursor()

        query = '''
            SELECT sum(%s) AS sum_y
            FROM tests
            WHERE %s=%u AND scenarioNo=%u AND variable='%s' AND reordering='%s'
            GROUP BY iterationNo
        ''' % (y, x, x_value, scenarioNo, x, rotype)

        dbcur.execute(query)
        ary = numpy.array(dbcur.fetchall())
        return ary.std()

    def run(self):
        """Main Method"""

        # bring up database
        dbexists = False
        if os.path.exists('data.sqlite'):
            dbexists = True
        self.dbcon = sqlite.connect('data.sqlite')

        if not dbexists:
            dbcur = self.dbcon.cursor()
            dbcur.execute("""
            CREATE TABLE tests (variable    VARCHAR(15),
                                reordering  VARCHAR(15),
                                bnbw        INTEGER,
                                qlimit      INTEGER,
                                rrate       INTEGER,
                                rdelay      INTEGER,
                                rtos        INTEGER,
                                frs         INTEGER,
                                iterationNo INTEGER,
                                scenarioNo  INTEGER,
                                runNo       INTEGER,
                                src         INTEGER,
                                dst         INTEGER,
                                thruput     DOUBLE,
                                start_time  INTEGER,
                                run_label   VARCHAR(70),
                                scenario_label VARCHAR(70),
                                test        VARCHAR(50))
            """)
            # store failed test as a mapping from run_label to number
            self.failed = dict()
            # only load flowgrind test records
            self.loadRecords(tests=["flowgrind"])
            self.dbcon.commit()
        else:
            info("Database already exists, don't load records.")

        if self.options.dry_run:
            return

        # Do Plots
        for y in ("thruput", "frs", "rtos"):
            self.generateYOverXLinePlot(y)


    def main(self):
        """Main method of the ping stats object"""

        self.parse_option()
        self.set_option()
        ReorderingAnalysis.run(self)

# this only runs if the module was *not* imported
if __name__ == '__main__':
    ReorderingAnalysis().main()
