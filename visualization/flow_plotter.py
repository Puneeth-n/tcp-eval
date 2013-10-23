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
import os.path
import math
from logging import info, debug, warn, error

# tcp-eval imports
from common.application import Application
from analysis.testrecords_flowgrind import FlowgrindRecordFactory
from visualization.gnuplot import UmHistogram, UmGnuplot, UmLinePlot, UmStepPlot, UmBoxPlot

class FlowPlotter(Application):
    def __init__(self):
        # initialization of the option parser
        description = "Usage: %prog [options] flowgrind-log[,flowgrind-log,..] [flowgrind-log[,flowgrind-log,..]] ...\n"\
                      "Creates graphs given by -G for every flowgrind-log specified.\n"\
                      "For a set of comma-seperated log files an average is built (throughput only!)"

        Application.__init__(self, description=description)

        # object variables
        self.factory = FlowgrindRecordFactory()

        self.parser.add_argument('-S', '--startat', metavar="time", default = 0,
                        action = 'store', type = float, dest = 'startat',
                        help = 'Start at this point in time [default: %(default)s]')
        self.parser.add_argument('-E', '--endat', metavar="time", default = 0,
                        action = 'store', type = float, dest = 'endat',
                        help = 'Start at this point in time [default: %(default)s]')
        self.parser.add_argument('-A', '--aname', metavar="filename",
                        action = 'store', type = str, dest = 'aname', default = "out",
                        help = 'Set output filename for usage with -a [default: %(default)s]')
        self.parser.add_argument('-a', '--all',
                        action = 'store_true', dest = 'all', default = False,
                        help = 'Print all flowlogs in one graph')
        self.parser.add_argument('-O', '--output', metavar="OutDir",
                        action = 'store', type = str, dest = 'outdir', default="./",
                        help = 'Set outputdirectory [default: %(default)s]')
        self.parser.add_argument("-c", "--cfg", metavar = "FILE",
                        action = "store", dest = "cfgfile",
                        help = "use the file as config file for LaTeX. "\
                               "No default packages will be loaded.")
        self.parser.add_argument("-n", "--flow-numbers", metavar = "Flownumbers",
                        action = 'store', type = str, dest = 'flownumber', default = "0",
                        help = 'print flow number [default: %(default)s]')
        self.parser.add_argument("-r", "--resample", metavar = "Rate", default = 0,
                        action = 'store', type = float, dest = 'resample',
                        help = 'resample to this sample rate [default:'\
                               ' dont resample]')
        self.parser.add_argument("-s", "--dont-plot-source",
                        action = 'store_false', dest = 'plotsrc', default = True,
                        help = 'don\'t plot source cwnd and throughput')
        self.parser.add_argument("-d", "--plot-dest", default = False,
                        action = 'store_true', dest = 'plotdst',
                        help = 'plot destination cwnd and throughput')
        self.parser.add_argument("-G", "--graphics", metavar = "list", default = 'tput,cwnd,rtt,segments',
                        action = 'store', dest = 'graphics',
                        help = 'Graphics that will be plotted '\
                                '[default: %(default)s; optional: dupthresh]')
        self.parser.add_argument("-f", "--force",
                        action = "store_true", dest = "force",
                        help = "overwrite existing output")
        self.parser.add_argument("--save", action = "store_true", dest = "save",
                        help = "save gnuplot and tex files [default: clean up]")

        self.parser.add_argument("flowgrindlog")

    def apply_options(self):
        """Set options"""

        Application.apply_options(self)

        if not os.path.exists(self.args.outdir):
            info("%s does not exist, creating. " % self.args.outdir)
            os.mkdir(self.args.outdir)

        if self.args.graphics:
            self.graphics_array = self.args.graphics.split(',')
        else:
            self.graphics_array = ['tput','cwnd','rtt','segments']

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

                    #actual resampling happens here
                    next = 0    # where to store the next resample (at the end this is the number of points)
                    all = 0     # where are we in the list?
                    while all < nosamples:
                        sum = 0         # sum of all parts
                        r = rate        # how much to sum up

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

                        out = sum/(rate-r)  # out is the value for the interval
                                            # r is not 0, if we are at the end of the list
                        data[next] = out
                        next += 1

                    #truncate table to new size
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
            nosamples = self.resample(record, directions, nosamples, flow)  # returns the new value for nosamples if anything was changed

            flow_array.append([plotname, flow, record, nosamples])

        #build average, save it to flow_array[0]
        if len(flow_array) > 1:
            for i in range(len(flow_array[0][1]['S']['tput'])):
                avg_S = 0
                avg_D = 0
                for l in range(len(flow_array)):
                    avg_S += flow_array[l][1]['S']['tput'][i]
                    avg_D += flow_array[l][1]['D']['tput'][i]
                flow_array[0][1]['S']['tput'][i] = avg_S/len(flow_array)
                flow_array[0][1]['D']['tput'][i] = avg_D/len(flow_array)

        plotname = flow_array[0][0] #just take one
        flow = flow_array[0][1]        #average for all files
        record = flow_array[0][2]      #hopefully the used parameter is always the same :)
        nosamples = min([flow_array[i][3] for i in range(len(flow_array))])

        #delete all data BEFORE some given time
        if self.args.startat > 0:
            for i in range(nosamples):
                if flow['D']['begin'][i] > self.args.startat: #get point where the time is over the threshold
                    for d in directions:    #delete all entries before this point
                        for key in flow[d].keys():
                            try:
                                len(flow[d][key])
                            except: continue
                            flow[d][key] = flow[d][key][i:nosamples]
                    break
            nosamples = nosamples-i

        #delete all data AFTER some given time
        if self.args.endat > 0:
            for i in range(nosamples):
                if flow['D']['begin'][i] > self.args.endat: #get point where the time is over the threshold
                    for d in directions:    #delete all entries before this point
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
        fh.write("# start_time end_time forward_tput reverse_tput forward_cwnd reverse_cwnd ssth krtt krto lost reor retr tret dupthresh\n")
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
            if 'dupthresh' in self.graphics_array:
                formatfields += tuple([flow['S']['dupthresh'][i]])
                formatstring += " %f"
            formatstring += "\n"
            fh.write( formatstring % formatfields )
        fh.close()

        return [plotname, label]


    def plot(self, *plotnameList):
        outdir = self.args.outdir

        outname = plotnameList[0][0]
        if len(plotnameList) > 1:
            outname = self.args.aname

        if 'tput' in self.graphics_array:
            # tput
            p = UmLinePlot(outname+'_tput', self.args.outdir, debug=self.args.debug, saveit=self.args.save, force=self.args.force)
            p.setYLabel(r"Throughput [$\\si{\\Mbps}$]")
            p.setXLabel(r"Time [$\\si{\\second}$]")
            if self.args.endat and self.args.startat:
                p.setXRange("[ %f : %f ]"
                        %(self.args.startat,self.args.endat) )
            count = 0
            for plotname, label in plotnameList:
                count += 1
                valfilename = os.path.join(outdir, plotname+".values")
                if self.args.plotsrc and self.args.plotdst:
                    p.plot(valfilename, "forward path %s" %label, using="2:3", linestyle=2*count)
                    p.plot(valfilename, "reverse path %s" %label, using="2:4", linestyle=2*count+1)
                elif self.args.plotsrc and not self.args.plotdst:
                    p.plot(valfilename, "%s" %label, using="2:3", linestyle=count+1)
                elif self.args.plotdst and not self.args.plotsrc:
                    p.plot(valfilename, "%s" %label, using="2:4", linestyle=count+1)
            # output plot
            p.save()

        if 'cwnd' in self.graphics_array:
            # cwnd
            p = UmLinePlot(outname+'_cwnd_ssth', self.args.outdir, debug=self.args.debug, saveit=self.args.save, force=self.args.force)
            p.setYLabel(r"$\\#$")
            p.setXLabel(r"Time [$\\si{\\second}$]")
            if self.args.endat and self.args.startat:
                p.setXRange("[ %f : %f ]"
                        %(self.args.startat,self.args.endat) )

            count = 0
            for plotname, label in plotnameList:
                valfilename = os.path.join(outdir, plotname+".values")
                if self.args.plotsrc: p.plot(valfilename, "Sender CWND %s" %label, using="2:5", linestyle=3*count+1)
                if self.args.plotdst: p.plot(valfilename, "Receiver CWND %s" %label, using="2:6", linestyle=3*count+2)
                p.plot(valfilename, "SSTHRESH %s" %label, using="2:7", linestyle=3*count+3)
                count += 1
            # output plot
            p.save()

        if 'rtt' in self.graphics_array:
            # rto, rtt
            p = UmLinePlot(outname+'_rto_rtt', self.args.outdir, debug=self.args.debug, saveit=self.args.save, force=self.args.force)
            p.setYLabel(r"$\\si{\\milli\\second}$")
            p.setXLabel(r"Time [$\\si{\\second}$]")
            if self.args.endat and self.args.startat:
                p.setXRange("[ %f : %f ]"
                        %(self.args.startat,self.args.endat) )

            count = 0
            for plotname, label in plotnameList:
                count += 1
                valfilename = os.path.join(outdir, plotname+".values")
                p.plot(valfilename, "RTO %s" %label, using="2:9", linestyle=2*count)
                p.plot(valfilename, "RTT %s" %label, using="2:8", linestyle=2*count+1)
            # output plot
            p.save()

        if 'segments' in self.graphics_array:
            # lost, reorder, retransmit
            p = UmLinePlot(outname+'_lost_reor_retr', self.args.outdir, debug=self.args.debug, saveit=self.args.save, force=self.args.force)
            p.setYLabel(r"$\\#$")
            p.setXLabel(r"Time [$\\si{\\second$]")
            if self.args.endat and self.args.startat:
                p.setXRange("[ %f : %f ]"
                        %(self.args.startat,self.args.endat) )

            count = 0
            for plotname, label in plotnameList:
                valfilename = os.path.join(outdir, plotname+".values")
                p.plot(valfilename, "lost segments %s" %label, using="2:10", linestyle=4*count+1)
                p.plot(valfilename, "dupthresh %s" %label, using="2:11", linestyle=4*count+2)
                p.plot(valfilename, "fast retransmits %s" %label, using="2:12", linestyle=4*count+3)
                p.plot(valfilename, "timeout retransmits %s" %label, using="2:13", linestyle=4*count+4)
                count += 1
            # output plot
            p.save()

        if 'dupthresh' in self.graphics_array:
            # dupthresh, tp->reordering
            p = UmStepPlot(outname+'_reordering_dupthresh', self.args.outdir, debug=self.args.debug, saveit=self.args.save, force=self.args.force)
            p.setYLabel(r"Dupthresh $[\\#]$")
            p.setXLabel(r"Time $[\\si{\\second}]$")
            #max_y_value = max(flow['S']['reor'] + flow['S']['dupthresh'])
            #p.setYRange("[*:%u]" % int(max_y_value + ((20 * max_y_value) / 100 )))
            if self.args.endat and self.args.startat:
                p.setXRange("[ %f : %f ]"
                        %(self.args.startat,self.args.endat) )

            count = 0
            for plotname, label in plotnameList:
                count += 1
                valfilename = os.path.join(outdir, plotname+".values")
                p.plot(valfilename, "Linux", using="2:11", linestyle=2*count)
                p.plot(valfilename, "%s" %label, using="2:14", linestyle=2*count+1)
            # output plot
            p.save()

    def run(self):
        """Run..."""

        plotnameList = []
        if not self.args.all:
            #for infile in self.args.flowgrindlog:
            infile = self.args.flowgrindlog
            for n in self.args.flownumber.split(","):
                plotname = self.write_values(infile, int(n))
                self.plot(plotname)
                if not self.args.save:
                    os.remove(os.path.join(self.args.outdir, plotname[0]+".values"))
        else:
            for infile in self.args.flowgrindlog:
                for n in self.args.flownumber.split(","):
                    plotnameList.append(self.write_values(infile, int(n)))

            self.plot(*plotnameList)

            if not self.args.save:
                for plotname, label in plotnameList:
                    os.remove(plotname+".values")

    def main(self):
        self.parse_options()
        self.apply_options()
        self.run()


# this only runs if the module was *not* imported
if __name__ == '__main__':
    FlowPlotter().main()

