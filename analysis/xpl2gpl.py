#! /usr/bin/env python
# -*- coding: utf-8 -*-

# python imports
import os
import math
import optparse
import sys
import subprocess
from logging import info, debug, warn, error
from simpleparse import generator
from simpleparse.parser import Parser
from mx.TextTools import TextTools

# umic-mesh imports
from um_gnuplot import UmHistogram, UmGnuplot, UmXPlot
from um_application import Application

"""xpl2gpl.py -- tcptrace / xplot 2 gnuplot converter"""

class xpl2gpl(Application):
    """Class to convert xplot/tcptrace files to gnuplot files"""

    declaration = r'''
root        :=    timeval,title,xlabel,ylabel,(diamond / text / varrow / harrow /
                  line / dline / dot / box / tick / color / linebreak)*,end*
alphanum    :=    [a-zA-Z0-9]
punct       :=    [!@#$%^&()+=|\{}:;<>,.?/"_-]
whitespace  :=    [ \t]
string      :=    ( alphanum / punct / whitespace )*, linebreak
keyword     :=    ([ A-Z]+ / int1)
float1      :=    [0-9]+,".",[0-9]+
float2      :=    [0-9]+,".",[0-9]+
int1        :=    [0-9]+
int2        :=    [0-9]+
end         :=    'go', linebreak*
timeval     :=    ( 'timeval double' / 'timeval signed' / 'dtime signed' ),
                    linebreak
title       :=    'title\n',string
xlabel      :=     'xlabel\n',string
ylabel      :=     'ylabel\n',string
linebreak   :=    [ \t]*,( '\n' / '\n\r' ),[ \t]*
color       :=    ( 'green' / 'yellow' / 'white' / 'orange' / 'blue' / 'magenta' /
                    'red' / 'purple' / 'pink' / 'window' / 'ack' / 'sack' / 'data' /
                    'retransmit' / 'duplicate' / 'reorder'/ 'text' / 'default' / 
                    'sinfin' / 'push' / 'ecn' / 'urgent' / 'probe' / 'a2bseg' /'b2aseg' )
harrow      :=    ( 'larrow' / 'rarrow'),whitespace,float1,whitespace,int1,
                    linebreak
varrow      :=    ( 'darrow' / 'uarrow'),whitespace,float1,whitespace,int1,
                    linebreak
line        :=    ( 'line' ),whitespace,float1,whitespace,int1,whitespace,
                    float2,whitespace,int2,linebreak
dline       :=    ( 'dline' ),whitespace,float1,whitespace,int1,whitespace,
                    float2,whitespace,int2,linebreak
dot         :=    ('dot'),whitespace,float1,whitespace,int1,(whitespace,color)*,
                    linebreak
diamond     :=    ('diamond'),whitespace,float1,whitespace,int1,(whitespace,
                    color)*,linebreak
box         :=    ('box'),whitespace,float1,whitespace,int1,(whitespace,color)*,
                    linebreak
tick        :=    ('dtick' / 'utick' / 'ltick' / 'rtick' / 'vtick' / 'htick'),
                    whitespace,float1,whitespace,int1,linebreak
text        :=    ('atext' / 'btext' / 'ltext' / 'rtext' ),whitespace,float1,whitespace,
                    int1,linebreak,keyword,linebreak
        '''

    def __init__(self):
        # initialization of the option parser
        Application.__init__(self)
        self.parser.set_usage("usage: %prog [options] <file1> <file2> ..")
        self.parser.set_defaults(parseroutput = False, outdir = "./")
        self.parser.add_option("-p", "--parseroutput",
                    action = "store_true", dest = "parseroutput",
                    help = "debug parsing [default: %default]")
        self.parser.add_option("--title", metavar = "text",
                    action = "store", dest = "title",
                    help = "gnuplot title [default: use xplot title]")
        self.parser.add_option("--xlabel", metavar = "text",
                    action = "store", dest = "xlabel",
                    help = "gnuplot x label [default: use xplot xlabel]")
        self.parser.add_option("--ylabel", metavar = "text",
                    action = "store", dest = "ylabel",
                    help = "gnuplot y label [default: use yplot xlabel]")
        self.parser.add_option('-O', '--output', metavar="OutDir",
                    action = 'store', type = 'string', dest = 'outdir',
                    help = 'Set outputdirectory [default: %default]')
        self.parser.add_option("-c", "--cfg", metavar = "FILE",
                    action = "store", dest = "cfgfile",
                    help = "use the file as config file for LaTeX. "\
                    "No default packages will be loaded.")

    def main(self):
        self.prepare()
        for arg in self.args:
            if self.options.parseroutput:
                self.debugparser(arg)
            else:
                self.work(arg)

    def prepare(self):
        self.parse_option()
        Application.set_option(self)

        for entry in self.args:
            if not os.path.isfile(entry):
                error("%s not found." %entry)
                exit(1)

    def work(self, filename):

        basename = os.path.splitext(os.path.basename( filename ))[0]
        xplfile = open ( filename ).read()

        simpleparser = generator.buildParser(self.declaration).parserbyname('root')

        gploutput = UmXPlot(basename)
        dataoutput = open ( "%s.datasets" %(basename) , 'w')
        labelsoutput = open ( "%s.labels" %(basename) , 'w')

        # start the work
        datasources = list()
        data = list()
        info("starting parsing")
        taglist = TextTools.tag(xplfile, simpleparser)
        currentcolor = title = xlabel = ylabel = ""
        for tag, beg, end, subtags in taglist[1]:
        # read options and labels from parse tree
        # convert keyword labels
            if tag == 'text':
                for subtag, subbeg, subend, subparts in subtags:
                    if subtag == 'float1':
                        xpoint = xplfile[subbeg:subend]
                    elif subtag == 'int1':
                        ypoint = xplfile[subbeg:subend]
                    elif subtag == 'keyword':
                        label = xplfile[subbeg:subend]
                if xplfile[beg:beg+1] == 'l': # 'l'text
                    position = "right"
                elif xplfile[beg:beg+1] == 'r':
                    position = "left"
                else:
                    position = "center"
                # write label out
                labelsoutput.write('set label "%s" at (%s-946684800.000000), %s %s\n' %(label,xpoint,ypoint,position) )

            # read colors
            elif tag == 'color':
                currentcolor = xplfile[beg:end]

            # read l/r arrow
            elif tag == 'varrow':
                if ('varrow',currentcolor) not in datasources:
                    datasources.append( ('varrow',currentcolor) )
                for subtag, subbeg, subend, subparts in subtags:
                    if subtag == 'float1':
                        xpoint = xplfile[subbeg:subend]
                    elif subtag == 'int1':
                        ypoint = xplfile[subbeg:subend]
                    elif subtag == 'color':
                        currentcolor = xplfile[subbeg:subend]
                data.append( ( ('varrow', currentcolor), "%s %s\n" %(xpoint, ypoint) ) )

            elif tag == 'harrow':
                if ('harrow',currentcolor) not in datasources:
                    datasources.append( ('harrow',currentcolor) )
                for subtag, subbeg, subend, subparts in subtags:
                    if subtag == 'float1':
                        xpoint = xplfile[subbeg:subend]
                    elif subtag == 'int1':
                        ypoint = xplfile[subbeg:subend]
                    elif subtag == 'color':
                        currentcolor = xplfile[subbeg:subend]
                data.append( ( ('harrow', currentcolor), "%s %s\n" %(xpoint, ypoint) ) )

            # read dot
            elif tag == 'dot':
                if ('dot',currentcolor) not in datasources:
                    datasources.append( ('dot',currentcolor) )
                for subtag, subbeg, subend, subparts in subtags:
                    if subtag == 'float1':
                        xpoint = xplfile[subbeg:subend]
                    elif subtag == 'int1':
                        ypoint = xplfile[subbeg:subend]
                    elif subtag == 'color':
                        currentcolor = xplfile[subbeg:subend]
                data.append( ( ('dot', currentcolor), "%s %s\n" %(xpoint, ypoint) ) )

            # diamonds
            elif tag == 'diamond':
                if ('diamond',currentcolor) not in datasources:
                    datasources.append( ('diamond',currentcolor) )
                for subtag, subbeg, subend, subparts in subtags:
                    if subtag == 'float1':
                        xpoint = xplfile[subbeg:subend]
                    elif subtag == 'int1':
                        ypoint = xplfile[subbeg:subend]
                    elif subtag == 'color':
                        currentcolor = xplfile[subbeg:subend]
                data.append( ( ('diamond', currentcolor), "%s %s\n" %(xpoint, ypoint) ) )


            elif tag == 'box':
                if ('box',currentcolor) not in datasources:
                    datasources.append( ('box',currentcolor) )
                for subtag, subbeg, subend, subparts in subtags:
                    if subtag == 'float1':
                        xpoint = xplfile[subbeg:subend]
                    elif subtag == 'int1':
                        ypoint = xplfile[subbeg:subend]
                    elif subtag == 'color':
                        currentcolor = xplfile[subbeg:subend]
                data.append( ( ('box',currentcolor), "%s %s\n" %(xpoint, ypoint) ) )


            elif tag == 'tick':
                if ('tick',currentcolor) not in datasources:
                    datasources.append( ('tick',currentcolor) )
                for subtag, subbeg, subend, subparts in subtags:
                    if subtag == 'float1':
                        xpoint = xplfile[subbeg:subend]
                    elif subtag == 'int1':
                        ypoint = xplfile[subbeg:subend]
                    elif subtag == 'color':
                        currentcolor = xplfile[subbeg:subend]
                data.append( ( ('tick',currentcolor), "%s %s\n" %(xpoint, ypoint) ) )

            elif tag == 'line':
                if ('line',currentcolor) not in datasources:
                    datasources.append( ('line',currentcolor) )
                for subtag, subbeg, subend, subparts in subtags:
                    if subtag == 'float1':
                        x1point = xplfile[subbeg:subend]
                    elif subtag == 'int1':
                        y1point = xplfile[subbeg:subend]
                    elif subtag == 'float2':
                        x2point = xplfile[subbeg:subend]
                    elif subtag == 'int2':
                        y2point = xplfile[subbeg:subend]
                data.append( ( ('line',currentcolor), "%s %s\n%s %s\n\n" %(x1point, y1point, x2point, y2point) ) )

            elif tag == 'dline':
                if ('dline',currentcolor) not in datasources:
                    datasources.append( ('dline',currentcolor) )
                for subtag, subbeg, subend, subparts in subtags:
                    if subtag == 'float1':
                        x1point = xplfile[subbeg:subend]
                    elif subtag == 'int1':
                        y1point = xplfile[subbeg:subend]
                    elif subtag == 'float2':
                        x2point = xplfile[subbeg:subend]
                    elif subtag == 'int2':
                        y2point = xplfile[subbeg:subend]
                data.append( ( ('dline',currentcolor), "%s %s\n%s %s\n\n" %(x1point, y1point, x2point, y2point) ) )

            # read title
            elif tag == 'title':
                if self.options.title == '':
                    title = xplfile[beg+len("title\n "):end-len("\n")]

            # read axis labels
            elif tag == 'xlabel':
                if self.options.xlabel == '':
                    xlabel = xplfile[beg+len("xlabel\n"):end-len("\n")]

            elif tag == 'ylabel':
                if self.options.xlabel == '':
                    ylabel = xplfile[beg+len("ylabel\n"):end-len("\n")]

        #write optons to gpl file
        #gploutput.plot('set title "%s"\n' %title )
        gploutput.setXLabel(xlabel)
        gploutput.setYLabel(ylabel)
        gploutput.gplot('load "%s.labels"\n' %basename)

        #iterate over data sources
        for index,datasource in enumerate(datasources):
	    info("new data source")
            gploutput.plot(basename+".datasets", index, datasource[0], datasource[1])

            # write data with same source in order
            for dataline in data:
                if dataline[0] == datasource:
                    dataoutput.write("%s" %dataline[1] )
            dataoutput.write("\n \n")

        dataoutput.close()
        labelsoutput.close()
        gploutput.save(self.options.outdir, self.options.debug, self.options.cfgfile)

    def debugparser(self, filename):
        file = open(filename).read()
        debugparser = Parser (self.declaration)
        import pprint
        info("started debug parsing")
        pprint.pprint(debugparser.parse(file))
        info("completed debug parsing")
        exit(0)

if __name__ == "__main__":
    xpl2gpl().main()
