#!/usr/bin/env python
# -*- coding: utf-8 -*-
#vi:et:sw=4 ts=4

# Copyright (C) 2010 Carsten Wolff <carsten@wolffcarsten.de>
# Copyright (C) 2009 - 2010 Christian Samsel <christian.samsel@rwth-aachen.de>
# Copyright (C) 2008 - 2011 Lennart Schulte <lennart.schulte@rwth-aachen.de>
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
import math
import textwrap
import os.path
from logging import info, debug, warn, error

# tcp-eval imports
from common.application import Application
from analysis.testrecords_flowgrind import FlowgrindRecordFactory
from visualization.gnuplot import UmHistogram, UmGnuplot, UmLinePlot, UmStepPlot, UmBoxPlot

class FlowPlotter(Application):
    """Creates graphs for throughput, cwnd, rtt, dupthresh, and segments out of
    flowgrind log files"""

    def __init__(self):
        """Creates a new FlowPotter object"""

        # object variables
        self.factory = FlowgrindRecordFactory()
        # all graphics that currently be supported
        self.graphics_array = ("tput", "cwnd", "rtt", "dupthresh", "retrans")

        # create top-level parser
        description = textwrap.dedent("""\
                      Creates graphs given by -g for every flowgrind-log
                      specified. For a set of flowgrind log files an average is
                      built (throughput only!)""")
        Application.__init__(self, description=description)
        self.parser.add_argument("flowgrind_log", metavar="log", nargs="+",
                help="flowgrind log file")
        self.parser.add_argument("-n", "--node", action="store",
                choices=["src", "dst", "both"], default="src", help="node "\
                        "to be plotted (default: %(default)s)")
        self.parser.add_argument("-s", "--start", metavar="NUM", default=0.0,
                action="store", type=float, help = "Start at this point in "\
                        "time (default: %(default)s)")
        self.parser.add_argument("-e", "--end", metavar="NUM", default=0.0,
                action="store", type=float, help="End at this point in "\
                        "time (default: %(default)s)")
        self.parser.add_argument("-f", "--flow-numbers", metavar="NUM",
                nargs="+", action="store", type=int, dest="flownumber",
                default=0, help="plot flows with number '%(metavar)s' "\
                        "(default: %(default)s)")
        self.parser.add_argument("-r", "--resample", metavar="RATE",
                default=0.0, action="store", type=float, help="resample flow "\
                        "to sample rate '%(metavar)s' (default: %(default)s)")
        self.parser.add_argument("-a", "--all-in-one", metavar="FILE",
                action="store", nargs="?", const="flowlog-all", dest="all",
                help="Plot all flowlogs in one graph into file '%(metavar)s' "\
                        "(default: %(const)s)")
        self.parser.add_argument("-g", "--graphic", action="store", nargs="+",
                metavar="PLOT", choices=self.graphics_array + ("all",),
                default="all", help="variable that will be plotted. Possible "\
                        "choices are: {%(choices)s} (default: %(default)s)")
        self.parser.add_argument("-o", "--output", metavar="DIR", default="./",
                action="store", type=str, dest="outdir", help="Set output "\
                        "directory (default: %(default)s)")
        self.parser.add_argument("-c", "--cfg", metavar="FILE", type=str,
                action="store", dest="cfgfile", help = "use the file as "\
                        "config file for LaTeX. No default packages will be "\
                        "loaded")
        self.parser.add_argument("--force", action="store_true",
                help="overwrite existing output")
        self.parser.add_argument("--save", action="store_true", help="save "\
                "gnuplot and tex files")

    def apply_options(self):
        """Configure object based on the options form the argparser.
        On the given options perform some sanity checks
        """

        Application.apply_options(self)

        if not os.path.exists(self.args.outdir):
            info("%s does not exist, creating. " % self.args.outdir)
            os.mkdir(self.args.outdir)

        # create an array with the graphics we want produce
        if "all" not in self.args.graphic:
            self.graphics_array = self.args.graphic

        # default values are string or int, a command line option given by the
        # user is a list. In oder to access the argument always in the same
        # way, we convert the string/int into a list
        if type(self.args.flownumber) == int:
            self.args.flownumber = [self.args.flownumber]

    def resample(self, record, directions, nosamples, flow):
        # get sample rate for resampling
        sample = float(record.results['reporting_interval'][0])
        resample = float(self.args.resample)
        rate = resample/sample
        debug("sample = %s, resample = %s -> rate = %s" %(sample, resample, rate))

        if resample > 0:
            if rate <= 1 :
                error("sample = %s, resample = %s -> rate = %s -> rate <= 1 !" %(sample, resample, rate))
                sys.exit(1)

            for d in directions:
                for key in (flow[d].keys()):
                    data = flow[d][key]

                    # check if data is number
                    try:
                        float(data[0])
                    except:
                        continue
                    debug("type: %s" %key)

                    # actual resampling happens here
                    next = 0 # where to store the next resample (at the end this is the number of points)
                    all = 0  # where are we in the list?
                    while all < nosamples:
                        sum = 0  # sum of all parts
                        r = rate # how much to sum up

                        if all != int(all):             # not an int
                            frac = 1 - (all - int(all)) # get the fraction which has not yet been included
                            sum += frac * data[int(all)]
                            all += frac
                            r -= frac

                        while r >= 1:
                            if all < nosamples:
                                sum += data[int(all)]
                                all += 1
                                r -= 1
                            else: break

                        if r > 0 and all < nosamples:
                            sum += r * data[int(all)]
                            all += r
                            r = 0

                        out = sum/(rate-r) # out is the value for the interval
                                           # r is not 0, if we are at the end of the list
                        data[next] = out
                        next += 1

                    # truncate table to new size
                    del flow[d][key][next:nosamples]

                # set begin and end time
                for i in range(next):
                    flow[d]['begin'][i] = i*resample
                    flow[d]['end'][i] = (i+1)*resample

            debug("new nosamples: %i" %next)
            return next
        else: return nosamples  # resample == 0


    def load_values(self, infile, flownumber):

        flow_array = []

        for file in infile.split(','):
            # create record from given file
            debug("analyzing %s" %file)
            record = self.factory.createRecord(file, "flowgrind")
            flows = record.calculate("flows")
            if not flows:
                error("parse error")
                sys.exit(1)

            if flownumber > len(flows):
                error("requested flow number %i greater then flows in file: %i"
                        %(flownumber,len(flows) ) )
                return
            flow = flows[int(flownumber)]

            plotname = "%s_%d"%(os.path.splitext(os.path.basename(file))[0],flownumber)

            # to avoid code duplicates
            directions = ['S', 'D']
            nosamples = min(flow['S']['size'], flow['D']['size'])
            debug("nosamples: %i" %nosamples)

            # resampling
            # returns the new value for nosamples if anything was changed
            nosamples = self.resample(record, directions, nosamples, flow)

            flow_array.append([plotname, flow, record, nosamples])

        # build average, save it to flow_array[0]
        if len(flow_array) > 1:
            for i in range(len(flow_array[0][1]['S']['tput'])):
                avg_S = 0
                avg_D = 0
                for l in range(len(flow_array)):
                    avg_S += flow_array[l][1]['S']['tput'][i]
                    avg_D += flow_array[l][1]['D']['tput'][i]
                flow_array[0][1]['S']['tput'][i] = avg_S/len(flow_array)
                flow_array[0][1]['D']['tput'][i] = avg_D/len(flow_array)

        plotname = flow_array[0][0] # just take one
        flow = flow_array[0][1]     # average for all files
        record = flow_array[0][2]   # hopefully the used parameter is always the same :)
        nosamples = min([flow_array[i][3] for i in range(len(flow_array))])

        # delete all data BEFORE some given time
        if self.args.start > 0:
            for i in range(nosamples):
                if flow['D']['begin'][i] > self.args.start: # get point where the time is over the threshold
                    for d in directions: # delete all entries before this point
                        for key in flow[d].keys():
                            try:
                                len(flow[d][key])
                            except: continue
                            flow[d][key] = flow[d][key][i:nosamples]
                    break
            nosamples = nosamples-i

        # delete all data AFTER some given time
        if self.args.end > 0:
            for i in range(nosamples):
                if flow['D']['begin'][i] > self.args.end: # get point where the time is over the threshold
                    for d in directions: # delete all entries before this point
                        for key in flow[d].keys():
                            try:
                                len(flow[d][key])
                            except: continue
                            flow[d][key] = flow[d][key][0:i]
                    break
            nosamples = i

        # get max cwnd for ssth output
        cwnd_max = 0
        for i in range(nosamples):
            for dir in directions:
                if flow[dir]['cwnd'][i] > cwnd_max:
                    cwnd_max = flow[dir]['cwnd'][i]

        return plotname, flow, cwnd_max, record, nosamples

    def write_values(self, infile, flownumber):
        """Write values of one file"""

        def ssth_max(ssth):
            SSTHRESH_MAX = 2147483647
            X = 50
            if ssth == SSTHRESH_MAX:  return 0
            elif ssth > cwnd_max + X: return cwnd_max + X
            else:                     return ssth

        def rto_max(rto):
            if rto == 3000: return 0
            else:           return rto

        plotname, flow, cwnd_max, record, nosamples = self.load_values(infile, flownumber)

        outdir=self.args.outdir
        valfilename = os.path.join(outdir, plotname+".values")
        info("Generating %s..." % valfilename)
        fh = file(valfilename, "w")
        # header
        recordHeader = record.getHeader()
        try:
            label = "%s %s Flow %d" %(recordHeader["scenario_label"],
                                      recordHeader["run_label"],
                                      flownumber)
        except:
            label = ""
        fh.write("# start_time end_time forward_tput reverse_tput "\
                "forward_cwnd reverse_cwnd ssth krtt krto lost reor retr "\
                "tret dupthresh\n")
        for i in range(nosamples):
            formatfields = (flow['S']['begin'][i],
                            flow['S']['end'][i],
                            flow['S']['tput'][i],
                            flow['D']['tput'][i],
                            flow['S']['cwnd'][i],
                            flow['D']['cwnd'][i],
                            ssth_max(flow['S']['ssth'][i]),
                            flow['S']['krtt'][i],
                            rto_max(flow['S']['krto'][i]),
                            flow['S']['lost'][i],
                            flow['S']['reor'][i],
                            flow['S']['retr'][i],
                            flow['S']['tret'][i] )
            formatstring = "%f %f %f %f %f %f %f %f %f %f %f %f %f"

            # to plot linux and tcp-ancr dupthresh together
#            if 'dupthresh' in self.graphics_array:
#                formatfields += tuple([flow['S']['dupthresh'][i]])
#                formatstring += " %f"
            formatstring += "\n"
            fh.write( formatstring % formatfields )
        fh.close()

        return [plotname, label]


    def plot(self, *plotnameList):
        """Produce the plot"""

        # Output directory and file name
        outdir = self.args.outdir
        outname = plotnameList[0][0]

        # if we want a combined all-in-one plot
        if len(plotnameList) > 1:
            outname = self.args.all

        # plot throughput
        if "tput" in self.graphics_array:
            p = UmLinePlot(outname+"_tput", self.args.outdir,
                    debug=self.args.debug, saveit=self.args.save,
                    force=self.args.force)
            p.setYLabel(r"Throughput $[\\si{\\Mbps}]$")
            p.setXLabel(r"Time $[\\si{\\second}]$")
            if self.args.end and self.args.start:
                p.setXRange("[ %f : %f ]" %(self.args.start, self.args.end))

            count = 0
            for plotname, label in plotnameList:
                valfilename = os.path.join(outdir, plotname+".values")
                # plotting both sender and receiver side
                if self.args.node == "both":
                    p.plot(valfilename, "Forward path %s" %label, using="2:3",
                            linestyle=2*count)
                    p.plot(valfilename, "Reverse path %s" %label, using="2:4",
                            linestyle=2*count+1)
                # plotting sender side only
                elif self.args.node == "src":
                    p.plot(valfilename, "%s" %label, using="2:3",
                            linestyle=count+1)
                # plotting receiver side only
                elif self.args.node == "dst":
                    p.plot(valfilename, "%s" %label, using="2:4",
                            linestyle=count+1)
                count += 1

            # plot and create pdf
            p.save()

        # plot cwnd and ssthresh
        if "cwnd" in self.graphics_array:
            p = UmLinePlot(outname+"_cwnd_ssth", self.args.outdir,
                    debug=self.args.debug, saveit=self.args.save,
                    force=self.args.force)
            p.setYLabel(r"Segment $[\\#]$")
            p.setXLabel(r"Time $[\\si{\\second}]$")
            if self.args.end and self.args.start:
                p.setXRange("[ %f : %f ]" %(self.args.start, self.args.end))

            count = 0
            for plotname, label in plotnameList:
                valfilename = os.path.join(outdir, plotname+".values")
                # plotting sender side
                if self.args.node == "src":
                    p.plot(valfilename, "Sender CWND %s" %label, using="2:5",
                            linestyle=2*count+1)
                    p.plot(valfilename, "Sender SSTHRESH %s" %label, using="2:7",
                            linestyle=2*count+3)
                # plotting receiver side
                if self.args.node == "dst":
                    p.plot(valfilename, "Receiver CWND %s" %label, using="2:6",
                            linestyle=1*count+2)
                count += 1

            # plot and create pdf
            p.save()

        # plot rto and rtt
        if "rtt" in self.graphics_array:
            p = UmLinePlot(outname+"_rto_rtt", self.args.outdir,
                    debug=self.args.debug, saveit=self.args.save,
                    force=self.args.force)
            p.setYLabel(r"$\\si{\\milli\\second}$")
            p.setXLabel(r"Time $[\\si{\\second}]$")
            if self.args.end and self.args.start:
                p.setXRange("[ %f : %f ]" %(self.args.start, self.args.end))

            count = 0
            for plotname, label in plotnameList:
                valfilename = os.path.join(outdir, plotname+".values")
                # plotting sender side
                if self.args.node == "src":
                    p.plot(valfilename, "RTO %s" %label, using="2:9",
                            linestyle=2*count)
                    p.plot(valfilename, "RTT %s" %label, using="2:8",
                            linestyle=2*count+1)
                # plotting receiver side
                if self.args.node == "dst":
                    #FIXME
                    raise NotImplementedError
                count += 1

            # plot and create pdf
            p.save()

        # plot lost segments, fast retransmits and rto retransmissions
        if "retrans" in self.graphics_array:
            p = UmLinePlot(outname+"_lost_retr_rto", self.args.outdir,
                    debug=self.args.debug, saveit=self.args.save,
                    force=self.args.force)
            p.setYLabel(r"Segment $[\\#]$")
            p.setXLabel(r"Time $[\\si{\\second}]$")
            if self.args.end and self.args.start:
                p.setXRange("[ %f : %f ]" %(self.args.start, self.args.end))

            count = 0
            for plotname, label in plotnameList:
                valfilename = os.path.join(outdir, plotname+".values")
                # plotting sender side
                if self.args.node == "src":
                    p.plot(valfilename, "Lost segments %s" %label,
                            using="2:10", linestyle=3*count+1)
                    p.plot(valfilename, "Fast retransmits %s" %label,
                            using="2:12", linestyle=3*count+3)
                    p.plot(valfilename, "Timeout retransmits %s" %label,
                            using="2:13", linestyle=3*count+4)
                # plotting receiver side
                if self.args.node == "dst":
                    #FIXME
                    raise NotImplementedError
                count += 1

            # plot and create pdf
            p.save()

        # plot tp->reordering (or TCP-aNCR dupthresh)
        if "dupthresh" in self.graphics_array:
            p = UmStepPlot(outname+'_dupthresh', self.args.outdir,
                    debug=self.args.debug, saveit=self.args.save,
                    force=self.args.force)
            p.setYLabel(r"Dupthresh $[\\#]$")
            p.setXLabel(r"Time $[\\si{\\second}]$")
            if self.args.end and self.args.start:
                p.setXRange("[ %f : %f ]"
                        %(self.args.start,self.args.end) )

            # to plot linux and tcp-ancr dupthresh together
#            max_y_value = max(flow['S']['reor'] + flow['S']['dupthresh'])
#            p.setYRange("[*:%u]" % int(max_y_value + ((20 * max_y_value) / 100 )))

            count = 0
            for plotname, label in plotnameList:
                valfilename = os.path.join(outdir, plotname+".values")
                # plotting sender side
                if self.args.node == "src":
                    p.plot(valfilename, "Dupthresh %s" %label, using="2:11",
                            linestyle=2*count+1)
                    # to plot linux and tcp-ancr dupthresh together
#                    p.plot(valfilename, "%s" %label, using="2:14",
#                            linestyle=2*count+2)
                # plotting receiver side
                if self.args.node == "dst":
                    #FIXME
                    raise NotImplementedError
                count += 1

            # plot and create pdf
            p.save()

    def run(self):
        """Run..."""

        # helper variable
        plotnameList = []

        # iterate over all log and flow numbers
        for infile in self.args.flowgrind_log:
            for n in self.args.flownumber:
                plotname = self.write_values(infile, int(n))
                plotnameList.append(plotname)

                # plot graph for fg log now
                if not self.args.all:
                    self.plot(plotname)

        # plot combined graph for all fg logs
        if self.args.all:
            self.plot(*plotnameList)

        # clean up
        if not self.args.save:
            for plotname, label in plotnameList:
                os.remove(os.path.join(self.args.outdir, "%s.values"
                    %(plotname)))

    def main(self):
        self.parse_options()
        self.apply_options()
        self.run()


# this only runs if the module was *not* imported
if __name__ == '__main__':
    FlowPlotter().main()

