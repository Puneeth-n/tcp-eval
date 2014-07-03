#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vi:et:sw=4 ts=4

# Copyright (C) 2010 Carsten Wolff <carsten@wolffcarsten.de>
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
import sys
import os
import os.path
import textwrap
import numpy
import scipy.stats
from logging import info, debug, warn, error
from sqlite3 import dbapi2 as sqlite

# tcp-eval imports
from common.functions import call
from analysis.analysis import Analysis
from visualization.gnuplot import UmGnuplot, UmLinePointPlot

class TCPaNCR_Analysis(Analysis):
    """Application for analysis of TCP-aNCR results.  It needs flowlogs
    produced by the -tcp-more-info branch to fully work"""

    def __init__(self):
        Analysis.__init__(self)

        # create top-level parser
        description = textwrap.dedent("""\
                Creates graphs showing thruput, fast retransmits and RTOs over
                the variable given. For this all flowgrind logs out of input
                folder are used which have the type given by the parameter
                -t.""")
        Analysis.__init__(self, description=description)
        self.parser.add_argument("variable", action="store", choices=["bnbw",
                "delay", "qlimit", "rrate", "rdelay", "ackreor", "ackloss"],
                help="The variable of the measurement")
        self.parser.add_argument("-t", "--type", action="store", dest="rotype",
                choices=["reordering", "congestion", "both"], help="The type "\
                        "of the measurement")
        self.parser.add_argument("-e", "--plot-error", action="store_true",
                help = "Plot error bars")
        self.parser.add_argument("-d", "--dry-run", action="store_true",
                dest="dry_run", help = "Test the flowlogs only")
        self.parser.add_argument("-f", "--fairness", action = "store_true",
                help = "Plot fairness instead")

        # Labels for plots - we use nice LaTeX code
        self.plotlabels = dict()
        self.plotlabels["bnbw"]    = r"Bottleneck Bandwidth [$\\si{\\Mbps}$]";
        self.plotlabels["qlimit"]  = r"Bottleneck Queue Length [packets]";
        self.plotlabels["rrate"]   = r"Reordering Rate [$\\si{\\percent}$]";
        self.plotlabels["rdelay"]  = r"Reordering Delay [$\\si{\\milli\\second}$]";
        self.plotlabels["rtos"]    = r"RTO Retransmissions [$\\#$]";
        self.plotlabels["frs"]     = r"Fast Retransmissions [$\\#$]";
        self.plotlabels["thruput"] = r"Throughput [$\\si{\\Mbps}$]";
        self.plotlabels["fairness"]= r"Fairness"
        self.plotlabels["delay"]   = r"Round-Trip Time [$\\si{\\milli\\second}$]"
        self.plotlabels["ackreor"] = r"ACK Reordering Rate [$\\si{\\percent}$]"
        self.plotlabels["ackloss"] = r"ACK Loss Rate [$\\si{\\percent}$]"
        self.plotlabels["rtt_avg"] = r"Application Layer RTT [$\\si{\\second}$]"
        self.plotlabels["dsacks"]  = r"Spurious Retransmissions [$\\#$]"

    def apply_options(self):
        "Set options"

        Analysis.apply_options(self)


    def onLoad(self, record, iterationNo, scenarioNo, runNo, test):
        dbcur = self.dbcon.cursor()

        try:
            recordHeader   = record.getHeader()
            src            = recordHeader["src"]
            dst            = recordHeader["dst"]
            run_label      = recordHeader["run_label"]
            scenario_label = recordHeader["scenario_label"]
            variable       = recordHeader["testbed_param_variable"]
            reordering     = recordHeader["testbed_param_reordering"]
            qlimit         = int(recordHeader["testbed_param_qlimit"])
            rrate          = int(recordHeader["testbed_param_rrate"])
            rdelay         = int(recordHeader["testbed_param_rdelay"])
        except:
            return

        try:
            bnbw       = int(recordHeader["testbed_param_bottleneckbw"])
        except KeyError:
            bnbw       = "NULL"

        try:
            delay      = 2 * float(recordHeader["testbed_param_delay"])
        except KeyError:
            delay      = "NULL"

        try:
            ackreor    = int(recordHeader["testbed_param_ackreor"])
        except KeyError:
            ackreor    = "NULL"

        try:
            ackloss    = int(recordHeader["testbed_param_ackloss"])
        except KeyError:
            ackloss    = "NULL"

        # test_start_time was introduced later in the header, so its not in old test logs
        try:
            start_time = int(float(recordHeader["test_start_time"]))
        except KeyError:
            start_time = 0
        rtos           = record.calculate("total_rto_retransmits")
        frs            = record.calculate("total_fast_retransmits")
        thruput        = record.calculate("thruput")
        try:
            rtt_avg        = record.calculate("rtt_avg")
        except KeyError:
            # accept measurements without RTT field
            rtt_avg        = 0

        # rtt_avg is measured in ms but we want second scale
        if rtt_avg:
            rtt_avg = rtt_avg / 1000
        else:
            rtt_avg = 0

        dsacks = record.calculate("total_dsacks")

        if dsacks == None:
            dsacks = 0

        if not thruput:
            if not self.failed.has_key(run_label):
                self.failed[run_label] = 1
            else:
                self.failed[run_label] = self.failed[run_label]+1
            return
        if thruput == 0:
            warn("Throughput is 0 in %s!" %record.filename)

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
        try:
            flow_S = record.calculate("flows")[0]['S']
            for tput in flow_S['tput']:
                if tput == 0.000000:
                    c += 1
                else: break
            if flow_S['end'][c] > 1:
                warn("Long connection establishment (%ss): %s" %(flow_S['end'][c], record.filename))
        except:
            warn("calculate(flows) failed")

        print  (variable, reordering, bnbw, qlimit, delay, rrate, rdelay,
                     ackreor, ackloss, rtos, frs, iterationNo, scenarioNo, runNo,
                     src, dst, thruput, rtt_avg, dsacks, start_time, run_label,
                     scenario_label, test)

        debug("""
              INSERT INTO tests VALUES ("%s", "%s", %s, %u, %u, %u, %u, %u, %u, %s, %s, %u, %u,
                    %u, "%s", "%s", %f, %f, %u,
                    %u, "$%s$", "%s", "%s")
              """ % (variable, reordering, bnbw, qlimit, delay, rrate, rdelay,
                     ackreor, ackloss, rtos, frs, iterationNo, scenarioNo, runNo,
                     src, dst, thruput, rtt_avg, dsacks, start_time, run_label,
                     scenario_label, test))

        dbcur.execute("""
                      INSERT INTO tests VALUES ("%s", "%s", %s, %u, %u, %u, %u, %u, %u, %s, %s, %u, %u,
                            %u, "%s", "%s", %f, %f, %u,
                            %u, "$%s$", "%s", "%s")
                      """ % (variable, reordering, bnbw, qlimit, delay, rrate,
                             rdelay, ackreor, ackloss, rtos, frs, iterationNo,
                             scenarioNo, runNo, src, dst, thruput, rtt_avg,
                             dsacks, start_time, run_label, scenario_label, test))

    def generateFairnessOverXLinePlot(self):
        """Generates a line plot of the DB column y over the DB column x
           reordering rate. One line for each scenario.
        """
        y      = 'fairness'
        x      = self.args.variable
        rotype = self.args.rotype

        dbcur = self.dbcon.cursor()

        # get all scenario labels
        dbcur.execute('''
            SELECT DISTINCT scenarioNo
            FROM tests ORDER BY scenarioNo'''
        )
        scenarios = []
        for row in dbcur:
            scen = row[0]
            scenarios.append(scen)

        outdir = self.args.outdir
        p = UmLinePointPlot("%s_%s_over_%s" % (rotype, y, x), outdir, debug = self.args.debug, force = True)
        p.setXLabel(self.plotlabels[x])
        p.setYLabel(self.plotlabels[y])

        for scenarioNo in scenarios:
            query = '''
                SELECT bnbw,avg(thruput),scenario_label
                FROM tests
                WHERE scenarioNo=%s
                GROUP BY scenario_label, bnbw
                ORDER BY bnbw;
            ''' %scenarioNo
            debug("\n\n" + query + "\n\n")
            fairness = dbcur.execute(query).fetchall()

            # fairness plot
            k = 0
            j = 1
            plotname = "%s_%s_over_%s_s%u" % (rotype, y, x, scenarioNo)
            valfilename = os.path.join(outdir, plotname+".values")

            info("Generating %s..." % valfilename)
            fhv = file(valfilename, "w")

            # header
            fhv.write("# %s %s\n" % (x, y))

            # Jain's fairness index
            for i in range(0, len(fairness), 2):
                try:
                    zaehler = (fairness[i][1] + fairness[i+1][1])**2
                    nenner = 2 * (fairness[i][1]**2 + fairness[i+1][1]**2)
                    jain_index = float(zaehler)/float(nenner)
                except: jain_index = 0

                fhv.write("%s %s\n" %(fairness[i][0], jain_index))

            fhv.close()

            p.plot(valfilename, "%s - %s" %(fairness[0][2], fairness[1][2]), linestyle=scenarioNo, using="1:2")

        # make room for the legend
        p.setYRange("[0.5:1.1]")
        p.save()

    def generateYOverXLinePlot(self, y):
        """Generates a line plot of the DB column y over the DB column x
           reordering rate. One line for each scenario.
        """

        x      = self.args.variable
        rotype = self.args.rotype

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

        outdir = self.args.outdir
        #p = UmLinePointPlot("%s_%s_over_%s" % (rotype, y, x), outdir, debug = self.args.debug, force = True)
        p = UmLinePointPlot("%s_%s_over_%s" % (rotype, y, x), outdir, saveit = self.args.save, debug = self.args.debug, force = True)
        #puneeth
        p.setXLabel(self.plotlabels[x])
        p.setYLabel(self.plotlabels[y])
        #p.setLogScale()

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
            dbcur = self.dbcon.cursor()
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
                # skip bogus rtt measurements
                if (y == "rtt_avg" and y_value == 0):
                    continue
                try:
                    if self.args.plot_error:
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
            if self.args.plot_error:
                p.plotYerror(valfilename, scenarios[scenarioNo], linestyle=scenarioNo + 1, using="1:2:3")
                p.plot(valfilename, title="", linestyle=scenarioNo + 1, using="1:2")
            else:
                p.plot(valfilename, scenarios[scenarioNo], linestyle=scenarioNo + 1, using="1:2")

        # make room for the legend
        if max_y_value:
            p.setYRange("[0:%u]" % max(1, int(max_y_value * 1.30)))
        p.save()

    def calculateStdDev(self, y, x_value, scenarioNo):
        """Calculates the standarddeviation for the values of the YoverXPlot
        """

        x      = self.args.variable
        rotype = self.args.rotype
        dbcur  = self.dbcon.cursor()

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
                                delay       INTEGER,
                                rrate       INTEGER,
                                rdelay      INTEGER,
                                ackreor     INTEGER,
                                ackloss     INTEGER,
                                rtos        INTEGER,
                                frs         INTEGER,
                                iterationNo INTEGER,
                                scenarioNo  INTEGER,
                                runNo       INTEGER,
                                src         INTEGER,
                                dst         INTEGER,
                                thruput     DOUBLE,
                                rtt_avg     DOUBLE,
                                dsacks      INTEGER,
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

        if self.args.dry_run:
            return

        # Do Plots
        if self.args.fairness:
            self.generateFairnessOverXLinePlot()
        else:
            for y in ("thruput", "frs", "rtos", "rtt_avg", "dsacks"):
                self.generateYOverXLinePlot(y)


    def main(self):
        """Main method of the ping stats object"""

        self.parse_options()
        self.apply_options()
        self.run()

# this only runs if the module was *not* imported
if __name__ == '__main__':
    TCPaNCR_Analysis().main()
