#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vi:et:sw=4 ts=4

# Copyright (C) 2009 - 2010 Christian Samsel <christian.samsel@rwth-aachen.de>
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
import os
import math
import sys
import glob
import textwrap
from logging import info, debug, warn, error
from simpleparse import generator
from simpleparse.parser import Parser
from mx.TextTools import TextTools

# tcp-eval imports
from common.application import Application
from visualization.gnuplot import UmHistogram, UmGnuplot, UmXPlot

class xpl2pdf(Application):
    """Class to convert xplot/tcptrace files to gnuplot files"""

    def __init__(self):
        """Creates a new xpl2pdf object"""

        self.declaration = textwrap.dedent("""\
                root        :=    timeval,title,xlabel,ylabel,(diamond / text / darrow / uarrow / harrow /
                                  line / dot / box / tick / color / linebreak)*,end*
                alphanum    :=    [a-zA-Z0-9]
                punct       :=    [!@#$%^&()+=|\{}:;<>,.?/"_-]
                whitespace  :=    [ \t]
                string      :=    ( alphanum / punct / whitespace )*
                keyword     :=    ( string / int1 )
                float1      :=    [0-9]+,".",[0-9]+
                float2      :=    [0-9]+,".",[0-9]+
                int1        :=    [0-9]+
                int2        :=    [0-9]+
                end         :=    'go', linebreak*
                timeval     :=    ( 'timeval double' / 'timeval signed' / 'dtime signed' ),
                                    linebreak
                title       :=    'title\n',string, linebreak
                xlabel      :=     'xlabel\n',string, linebreak
                ylabel      :=     'ylabel\n',string, linebreak
                linebreak   :=    [ \t]*,( '\n' / '\n\r' ),[ \t]*
                color       :=    ( 'green' / 'yellow' / 'white' / 'orange' / 'blue' / 'magenta' /
                                    'red' / 'purple' / 'pink' / 'window' / 'ack' / 'sack' / 'data' /
                                    'retransmit' / 'duplicate' / 'reorder'/ 'text' / 'default' /
                                    'sinfin' / 'push' / 'ecn' / 'urgent' / 'probe' / 'a2bseg' /
                                    'b2aseg'/ 'nosampleack' /'ambigousack' / 'icmp' )
                localcolor  :=    ( 'green' / 'yellow' / 'white' / 'orange' / 'blue' / 'magenta' /
                                    'red' / 'purple' / 'pink' / 'window' / 'ack' / 'sack' / 'data' /
                                    'retransmit' / 'duplicate' / 'reorder'/ 'text' / 'default' /
                                    'sinfin' / 'push' / 'ecn' / 'urgent' / 'probe' / 'a2bseg' /
                                    'b2aseg'/ 'nosampleack' /'ambigousack' / 'icmp' )
                harrow      :=    ( 'larrow' / 'rarrow'),whitespace,float1,whitespace,int1,
                                    linebreak
                darrow      :=    ('darrow'),whitespace,float1,whitespace,int1,
                                    linebreak
                uarrow      :=    ('uarrow'),whitespace,float1,whitespace,int1,
                                    linebreak
                line        :=    ( 'line' / 'dline' ),whitespace,float1,whitespace,int1,whitespace,
                                    float2,whitespace,int2,linebreak
                dot         :=    ('dot'),whitespace,float1,whitespace,int1,(whitespace,localcolor)*,
                                    linebreak
                diamond     :=    ('diamond'),whitespace,float1,whitespace,int1,(whitespace,
                                    localcolor)*,linebreak
                box         :=    ('box'),whitespace,float1,whitespace,int1,(whitespace,localcolor)*,
                                    linebreak
                tick        :=    ('dtick' / 'utick' / 'ltick' / 'rtick' / 'vtick' / 'htick'),
                                    whitespace,float1,whitespace,int1,linebreak
                text        :=    ('atext' / 'btext' / 'ltext' / 'rtext'),whitespace,float1,
                                    whitespace,int1,(whitespace,localcolor)*,linebreak,keyword,linebreak
        """)

        # initialization of the option parser
        description = "Creates PDFs for every xpl file specified"
        Application.__init__(self, description=description)
        self.parser.add_argument("xpl_files", metavar="xpl", nargs="+",
                help="a xplot xpl file")
        self.parser.add_argument("-p", "--parser-output", action="store_true",
                default=False, help="print parser output for debugging")
        self.parser.add_argument("--title", metavar="TXT", action="store",
                help="gnuplot title (default: use xplot title)")
        self.parser.add_argument("--xlabel", metavar="TXT", action="store",
                help="gnuplot x label (default: use xplot xlabel)")
        self.parser.add_argument("--ylabel", metavar="TXT", action="store",
                help="gnuplot y label (default: use xplot ylabel)")
        self.parser.add_argument("--ymax", metavar="NUM", type =int,
                action="store", help="gnuplot y range (default: let gnuplot "\
                        "decide)")
        self.parser.add_argument("--microview", action="store_true",
                help="enable microview (use arrowheads etc.)")
        self.parser.add_argument("--plotsize", metavar=("X", "Y"), type=float,
                nargs=2, action="store", help="plot size in cm (default: "\
                        "14.8 11.8), alternative: 14.8 9")
        self.parser.add_argument("--arrowsize", metavar="NUM", type=float,
                action="store", help="arrow size (default: 0.004)")
        self.parser.add_argument("--fontsize", metavar="NUM", type=int,
                action="store", help="target fontsize (default: 6)")
        self.parser.add_argument("--rexmitpos", action="store",
                choices=("left", "mid", "right"), help="position of the red "\
                        "retransmission R (default: mid)")
        self.parser.add_argument("--save", action="store_true", help="save "\
                        "gnuplot and tex files")
        self.parser.add_argument("-o", "--output", metavar="DIR", default="./",
                action="store", dest="outdir", help="Set output directory "\
                        "(default: %(default)s)")
        self.parser.add_argument("-c", "--cfg", metavar="FILE", action="store",
                dest="cfgfile", help="use the file as config file for LaTeX. "\
                        "No default packages will be loaded")
        self.parser.add_argument("-f", "--force", action="store_true",
                help="overwrite existing output")

    def apply_options(self):
        """Set the options"""

        Application.apply_options(self)

        # sanity check
        for entry in self.args.xpl_files:
            if not os.path.isfile(entry):
                error("%s not found." %entry)
                exit(1)

    def work(self, filename):
        """work, work"""
        outdir = self.args.outdir
        basename = os.path.splitext(os.path.basename(filename))[0]
        xplfile = open (filename).read()

        simpleparser = generator.buildParser(self.declaration).parserbyname('root')

        gploutput = UmXPlot(basename, outdir, debug=self.args.debug, saveit=self.args.save, force=self.args.force)
        if self.args.arrowsize:
            gploutput.arrowsize = self.args.arrowsize
        labelsoutput = open ( "%s/%s.labels" %(outdir,basename) , 'w')

        # start the work
        datasources = list()
        data = list()
        info("starting parsing of %s" %(filename) )
        taglist = TextTools.tag(xplfile, simpleparser)
        currentcolor = title = xlabel = ylabel = ""
        # used to generate default XRange
        xmin = sys.maxint
        xmax = 0.0

        for tag, beg, end, subtags in taglist[1]:
        # read options and labels from parse tree
        # convert keyword labels
            localcolor = 0
            if tag == 'text':
                # default color for labels
                localcolor = "black"
                for subtag, subbeg, subend, subparts in subtags:
                    if subtag == 'float1':
                        xpoint = xplfile[subbeg:subend]
                    elif subtag == 'int1':
                        ypoint = xplfile[subbeg:subend]
                    elif subtag == 'keyword':
                        label = xplfile[subbeg:subend]
                    elif subtag == 'localcolor':
                        localcolor = xplfile[subbeg:subend]

                if xplfile[beg:beg+1] == 'l': # 'l'text
                    position = "right"
                elif xplfile[beg:beg+1] == 'r':
                    position = "left"
                else:
                    position = "center"
                # label options
                # defaults
                printthis = True
                labelxoffset = 0.5
                labelyoffset = 0.0
                labelrotation = 0
                if not self.args.fontsize:
                    labelsize = 5
                else:
                    labelsize = self.args.fontsize-1
                # special cases
                if label == "R":
                    localcolor = "red"
                    #labelsize = 3 # smaller R for macroview
                    if self.args.microview:
                        if self.args.rexmitpos == "right":
                            labelxoffset = -0.15
                            labelyoffset = 0.7
                        if self.args.rexmitpos == "left":
                            labelxoffset = -0.15
                            labelyoffset = -0.7
                elif label == "3" or label == "2" or label == "1":
                    printthis = False
                elif label == "3DUP":
                    printthis = False
                    labelxoffset = -1
                    localcolor = "#32CD32"
                    labelrotation = 90
                elif label == "SYN" or label == "RST_IN":
                    printthis = False # edit if you want
                    localcolor = "black"
                    if self.args.microview:
                        labelxoffset = -0.15
                        labelyoffset = 0.7
                # dont print S (sack) labels
                elif label == "S":
                    printthis = False
                # escape _
                label = label.replace("_","\\\_")
                # write label out
                if printthis:
                    labelsoutput.write('set label "\\\\fontsize{%s}{%s}\\\\selectfont %s" at %s, %s '\
                            '%s offset %f, %f tc rgbcolor "%s" rotate by %s\n'
                            %(labelsize, int(round(labelsize/1.2)),label,xpoint,ypoint,position,labelyoffset,labelxoffset,localcolor,labelrotation) )
            # read colors
            elif tag == 'color':
                currentcolor = xplfile[beg:end]

            # read l/r arrow
            elif tag == 'darrow':
                for subtag, subbeg, subend, subparts in subtags:
                    if subtag == 'float1':
                        xpoint = xplfile[subbeg:subend]
                    elif subtag == 'int1':
                        ypoint = xplfile[subbeg:subend]
                    elif subtag == 'localcolor':
                        localcolor = xplfile[subbeg:subend]
                if not localcolor:
                    localcolor = currentcolor
                if ('darrow',localcolor) not in datasources:
                    datasources.append( ('darrow',localcolor) )
                data.append( ( ('darrow', localcolor), "%s %s\n" %(xpoint, ypoint) ) )

            elif tag == 'harrow':
                for subtag, subbeg, subend, subparts in subtags:
                    if subtag == 'float1':
                        xpoint = xplfile[subbeg:subend]
                    elif subtag == 'int1':
                        ypoint = xplfile[subbeg:subend]
                    elif subtag == 'localcolor':
                        localcolor = xplfile[subbeg:subend]
                if not localcolor:
                    localcolor = currentcolor
                if ('harrow',localcolor) not in datasources:
                    datasources.append( ('harrow',localcolor) )
                data.append( ( ('harrow', localcolor), "%s %s\n" %(xpoint, ypoint) ) )

            # read dot
            elif tag == 'dot':
                for subtag, subbeg, subend, subparts in subtags:
                    if subtag == 'float1':
                        xpoint = xplfile[subbeg:subend]
                    elif subtag == 'int1':
                        ypoint = xplfile[subbeg:subend]
                    elif subtag == 'localcolor':
                        localcolor = xplfile[subbeg:subend]
                if not localcolor:
                    localcolor = currentcolor
                if ('dot',localcolor) not in datasources:
                    datasources.append( ('dot',localcolor) )
                data.append( ( ('dot', localcolor), "%s %s\n" %(xpoint, ypoint) ) )

            # diamonds
            elif tag == 'diamond':
                for subtag, subbeg, subend, subparts in subtags:
                    if subtag == 'float1':
                        xpoint = xplfile[subbeg:subend]
                    elif subtag == 'int1':
                        ypoint = xplfile[subbeg:subend]
                    elif subtag == 'localcolor':
                        localcolor = xplfile[subbeg:subend]
                if not localcolor:
                    localcolor = currentcolor
                if ('diamond',localcolor) not in datasources:
                    datasources.append( ('diamond',localcolor) )
                data.append( ( ('diamond', localcolor), "%s %s\n" %(xpoint, ypoint) ) )

            elif tag == 'box':
                for subtag, subbeg, subend, subparts in subtags:
                    if subtag == 'float1':
                        xpoint = xplfile[subbeg:subend]
                    elif subtag == 'int1':
                        ypoint = xplfile[subbeg:subend]
                    elif subtag == 'localcolor':
                        localcolor = xplfile[subbeg:subend]
                if ('box',currentcolor) not in datasources:
                    datasources.append( ('box',currentcolor) )
                data.append( ( ('box',currentcolor), "%s %s\n" %(xpoint, ypoint) ) )

            elif tag == 'tick':
                for subtag, subbeg, subend, subparts in subtags:
                    if subtag == 'float1':
                        xpoint = xplfile[subbeg:subend]
                    elif subtag == 'int1':
                        ypoint = xplfile[subbeg:subend]
                    elif subtag == 'localcolor':
                        localcolor = xplfile[subbeg:subend]
                if not localcolor:
                    localcolor = currentcolor
                if ('tick',localcolor) not in datasources:
                    datasources.append( ('tick',localcolor) )
                data.append( ( ('tick',localcolor), "%s %s\n" %(xpoint, ypoint) ) )

            elif tag == 'line':
                for subtag, subbeg, subend, subparts in subtags:
                    if subtag == 'float1':
                        x1point = float(xplfile[subbeg:subend])
                        if x1point < xmin:
                            xmin = x1point
                    elif subtag == 'int1':
                        y1point = xplfile[subbeg:subend]
                    elif subtag == 'float2':
                        x2point = float(xplfile[subbeg:subend])
                        if x2point > xmax:
                            xmax = x2point
                    elif subtag == 'int2':
                        y2point = xplfile[subbeg:subend]
                if ('line',currentcolor) not in datasources:
                    datasources.append( ('line',currentcolor) )
                data.append( ( ('line',currentcolor), "%s %s %s %s\n" %(x1point, y1point, x2point, y2point) ) )

        # finish close
        labelsoutput.close()
        info("data parsing complete")

        # write options to gpl file
        # labels
        gploutput.setXLabel(self.xlabel)
        gploutput.setYLabel(self.ylabel)

        # range
        debug("XRange [%s:%s]" %(xmin,xmax) )
        gploutput.setXRange("[%s:%s]" %(xmin,xmax) )

        if self.args.ymax:
            debug("YRange [*:%s]" %self.args.ymax )
            gploutput.setYRange("[*:%s]" %self.args.ymax )

        # size
        if self.args.plotsize:
            gploutput.setPlotSize("%scm,%scm" \
                    %(self.args.plotsize[0], self.args.plotsize[1]))

        if self.args.fontsize:
            gploutput.setFontSize(self.args.fontsize)

        if self.args.microview:
            gploutput.arrowheads()

        #iterate over data sources (color x plottype) and write file
        for index,datasource in enumerate(datasources):
            datafilename = "%s/%s.dataset.%s.%s" %(outdir,
                    basename, datasource[1], datasource[0])
            dataoutput = open ( datafilename , 'w')
            wrotedata = False

            # iterate over all data and write approciate  lines to target file
            for dataline in data:
                if dataline[0] == datasource:
                    dataoutput.write("%s" %dataline[1] )
                    if (wrotedata == False):
                        wrotedata = True
            dataoutput.close()

            # only plot datasource if wrote data, else remove target file
            if (wrotedata == True):
                gploutput.plot(outdir, basename, datasource[1], datasource[0],
                        self.args.microview)
            else:
                os.remove(datafilename)

        gploutput.gplot('load "%s/%s.labels"\n' %(outdir,basename) )

        gploutput.arrowheads()
        gploutput.save()

    def prepare(self):
        """ global configuration for all input files """

        if not os.path.exists(self.args.outdir):
            info("%s does not exist, creating. " % self.args.outdir)
            os.mkdir(self.args.outdir)

        # axis labels
        if self.args.xlabel:
            self.xlabel = self.args.xlabel
        else:
            self.xlabel = "Time $[\\\\si{\\\\second}]$"

        if self.args.ylabel:
            self.ylabel = self.args.ylabel
        else:
            self.ylabel = "Sequence Offset $[\\\\si{\\\\byte}]$"

    def cleanup(self, filename):
        os.chdir(self.args.outdir)
        basename = os.path.splitext(os.path.basename( filename ))[0]
        info("Cleaning Up %s/%s" %(self.args.outdir,basename) )
        os.remove("%s.labels" %basename )
        for filename in glob.glob("%s.dataset.*" %basename):
            os.remove(filename)

    def debugparser(self, filename):
        file = open(filename).read()
        debugparser = Parser (self.declaration)
        import pprint
        info("started debug parsing")
        pprint.pprint(debugparser.parse(file))
        info("completed debug parsing")
        exit(0)

    def run(self):
        self.prepare()

        for arg in self.args.xpl_files:
            if self.args.parser_output:
                self.debugparser(arg)
            else:
                self.work(arg)

        if not self.args.debug and not self.args.save:
            for arg in self.args.xpl_files:
                self.cleanup(arg)
            info("use --save to prevent this")

        info("work complete")

    def main(self):
        self.parse_options()
        self.apply_options()
        self.run()


if __name__ == "__main__":
    xpl2pdf().main()

