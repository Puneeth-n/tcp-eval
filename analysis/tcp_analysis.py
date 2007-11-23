#!/usr/bin/env python
# -*- coding: utf-8 -*-

# python imports
import sys
import os
import os.path
import subprocess
import re
import time
import signal
import socket
import optparse
import time
import gc
from logging import info, debug, warn, error
from datetime import timedelta, datetime
from pysqlite2 import dbapi2 as sqlite 

import numpy

# umic-mesh imports
from um_application import Application
from um_config import *
from um_functions import call
from um_analysis.testrecords import TestRecordFactory
from um_analysis.analysis import Analysis
from um_gnuplot import UmHistogram, UmGnuplot

class TcpAnalysis(Analysis):
    "Application for analysis of flowgrind results"

    def __init__(self):

        Analysis.__init__(self)
        self.parser.set_defaults(outprefix= "neighbors", quality = 100,
                                 indir  = "./",
                                 outdir = "./",
                                 digraph=False)
        
        self.parser.add_option('-P', '--prefix', metavar="PREFIX",
                        action = 'store', type = 'string', dest = 'outprefix',
                        help = 'Set prefix of output files [default: %default]')




    def set_option(self):
        "Set options"
        Analysis.set_option(self)

        


    def onLoad(self, record, iterationNo, scenarioNo, test):
        dbcur = self.dbcon.cursor()
    
        recordHeader = record.getHeader()
        src = recordHeader["flowgrind_src"]
        dst = recordHeader["flowgrind_dst"]
        run_label = recordHeader["run_label"]
        scenario_label = recordHeader["scenario_label"]
        
        thruput = record.calculate("thruput")


        
        if not thruput:
            if not self.failed.has_key(run_label):
                self.failed[run_label] = 1
            else:
                self.failed[run_label] = self.failed[run_label]+1            
            return

        dbcur.execute("""
                      INSERT INTO tests VALUES (%u, %u, %s, %s, %f, "%s", "%s", "%s")
                      """ % (iterationNo,scenarioNo,src,dst, thruput, run_label, scenario_label, test))



    def generateAccHistogram(self):
        """ Generates a histogram of the 10 best pairs (avg_thruput).
            Thruput is accumulated for one run_label """

        dbcur = self.dbcon.cursor()

        # accumulate all scenarios and just distinct via run, limit to 10
        limit = 10
        sortby = "avg_thruput"

        # get unique "runs" and sum up thruput
        dbcur.execute('''
        SELECT run_label,
        MIN(thruput) as min_thruput,
        MAX(thruput) as max_thruput,
        SUM(thruput)/SUM(1) as avg_thruput,
        SUM(1)
        FROM tests GROUP BY src, dst ORDER BY %s DESC LIMIT %d
        ''' %(sortby, limit) )


        # outfile
        outdir = self.options.outdir
        plotname = "best_%d_pairs_acc" %limit
        bestfilename = os.path.join(outdir, plotname+".values")
        texfilename = os.path.join(outdir, plotname+".tex")
        
        info("Generating %s..." % bestfilename)

        fh = file(bestfilename, "w")

        # print header
        fh.write("# label MIN(thruput) MAX(thruput) avg_thruput no_of_thruputs no_of_failed\n")

        for row in dbcur:
            (label,min_thruput,max_thruput,avg_thruput,notests) = row
            if self.failed.has_key(label):
                nofailed = self.failed[label]
            else:
                nofailed = 0
            fh.write('"%s" %f %f %f %d' % row)
            fh.write(' %d\n' % nofailed)

        fh.close()

        info("Generating %s..." %texfilename)
        g = UmHistogram()

        g.setYLabel(r"Throughput in $\\Mbps$")
        g.setBars(limit)
        g.setOutput(texfilename)
        g('plot "%s" using 4:xtic(1) title "Thruput" ls 1' % bestfilename)
        

        g = None
        gc.collect()

        info("Generating %s.pdf" % plotname)
        cmd = ["gnuplot2pdf.py", "-f", "-p","pdf"]
        if self.options.cfgfile:
            cmd.extend(["-c", self.options.cfgfile])
        if self.options.debug:
            cmd.append("--debug")
        cmd.append(plotname)
        call(cmd, shell=False)


    def generateHistogram(self):
        """ Generates a histogram of the 10 best pairs (avg_thruput). With scenario labels.
        """

        dbcur = self.dbcon.cursor()

        # accumulate all scenarios and just distinct via run, limit to 10
        limit = 10
        sortby = "avg_thruput"

        # get unique "runs" and sum up thruput
        dbcur.execute('''
        SELECT run_label, scenario_label,
        MIN(thruput) as min_thruput,
        MAX(thruput) as max_thruput,
        SUM(thruput)/SUM(1) as 
        SUM(1)
        FROM tests GROUP BY src, dst, scenario_no ORDER BY %s DESC LIMIT %d
        ''' %(sortby, limit) )


        # outfile
        outdir = self.options.outdir
        plotname = "best_%d_pairs" %limit
        bestfilename = os.path.join(outdir, plotname+".values")
        texfilename = os.path.join(outdir, plotname+".tex")
        
        info("Generating %s..." % bestfilename)

        fh = file(bestfilename, "w")

        # print header
        fh.write("# run_label no_of_thruputs no_of_failed\n")

        for row in dbcur:
            (label,min_thruput,max_thruput,avg_thruput,notests) = row
            if self.failed.has_key(label):
                nofailed = self.failed[label]
            else:
                nofailed = 0
            fh.write('"%s" %f %f %f %d' % row)
            fh.write(' %d\n' % nofailed)

        fh.close()

        info("Generating %s..." %texfilename)
        g = UmHistogram()

        g.setYLabel(r"Throughput in $\\Mbps$")
        g.setBars(limit)
        g.setOutput(texfilename)
        g('plot "%s" using 4:xtic(1) title "Thruput" ls 1' % bestfilename)
        

        g = None
        gc.collect()

        info("Generating %s.pdf" % plotname)
        cmd = ["gnuplot2pdf.py", "-f", "-p","pdf"]
        if self.options.cfgfile:
            cmd.extend(["-c", self.options.cfgfile])
        if self.options.debug:
            cmd.append("--debug")
        cmd.append(plotname)
        call(cmd, shell=False)


    def generateCumulativeFractionOfPairs(self):
        dbcur = self.dbcon.cursor()
        
        # get number of unique pairs
        dbcur.execute('''
        SELECT COUNT(DISTINCT run_label) FROM tests 
        ''')

        pairs = dbcur.fetchone()[0]
        info("Found %u unique pairs" %pairs)
        
        # get unique pairs and calculate avg_thruput, sort by it
        dbcur.execute('''
        SELECT
        SUM(thruput)/SUM(1) as avg_thruput,
        SUM(1)
        FROM tests GROUP BY src, dst ORDER BY avg_thruput ASC
        ''')

        outdir = self.options.outdir
        plotname = "fraction_of_pairs" 
        bestfilename = os.path.join(outdir, plotname+".values")
        texfilename = os.path.join(outdir, plotname+".tex")
        
        info("Generating %s..." % bestfilename)
        fh = file(bestfilename, "w")

        # header
        fh.write("# fraction of pairs\n")
        fh.write("# avg_thruput fraction\n")

        i = 1
        for row in dbcur:
            (avg_thruput,notests) = row
            fraction = float(i)/float(pairs)
            fh.write("%f %f\n" %(avg_thruput, fraction))
            i = i+1


        fh.close()


        info("Generating %s..." %texfilename)
        g = UmGnuplot()

        g.setXLabel(r"Throughput in $\\Mbps$")
        g.setYLabel("Fraction of Pairs")
        
        g.setOutput(texfilename)
        g('plot "%s" using 1:2 title "1-Hop" ls 1 with steps' % bestfilename)

        g = None
        gc.collect()

        info("Generating %s.pdf" % plotname)
        cmd = ["gnuplot2pdf.py", "-f", "-p","pdf"]
        if self.options.cfgfile:
            cmd.extend(["-c", self.options.cfgfile])
        if self.options.debug:
            cmd.append("--debug")
        cmd.append(plotname)
        call(cmd, shell=False)




    def run(self):
        "Main Method"

        # database in memory to access data efficiently
        self.dbcon = sqlite.connect(':memory:')
        dbcur = self.dbcon.cursor()
        dbcur.execute("""
        CREATE TABLE tests (iterationNo INTEGER,
                            scenarioNo  INTEGER,
                            src         INTEGER,
                            dst         INTEGER,                            
                            thruput     DOUBLE,
                            run_label   VARCHAR(70),
                            scenario_label VARCHAR(70),
                            test        VARCHAR(50))
        """)

        # store failed test as a mapping from run_label to number
        self.failed = dict()

        # only load ping test records
        self.loadRecords(tests=["flowgrind"])

        self.dbcon.commit()

        self.generateAccHistogram()
        
        self.generateCumulativeFractionOfPairs()
        
        
                    
    def main(self):
        "Main method of the ping stats object"

        self.parse_option()
        self.set_option()
        TcpAnalysis.run(self)

# this only runs if the module was *not* imported
if __name__ == '__main__':
    TcpAnalysis().main()

