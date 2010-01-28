#!/usr/bin/env python
# -*- coding: utf-8 -*-

# python imports
import sys
import re
from subprocess import Popen, PIPE
from logging import info, debug, warn, error

# umic-mesh imports
from um_application import Application

class XplotCut(Application):
    def __init__(self):
        Application.__init__(self)

        # initialization of the option parser
        usage = "usage: %prog [options] xpl-file"

        self.parser.set_usage(usage)
        #self.parser.set_defaults( )
        #self.parser.add_option('-O', '--output', metavar="OutDir",
        #                action = 'store', type = 'string', dest = 'outdir',
        #                help = 'Set outputdirectory [default: %default]')

    def set_option(self):
        """Set options"""

        Application.set_option(self)
        if len(self.args) < 1:
            error("no input files, stop.")
            sys.exit(1)
        elif len(self.args) > 1:
            error("give exactly one file!")
            sys.exit(1)
        else:
            self.infile = self.args[0]

    def cut(self, begin, end, infile, outfile):
        """Write the current view to a new file"""

        ifh = open(infile,  'r')
        ofh = open(outfile, 'w')
        state = 0
        buf   = ''
        info("Cutting %s" % infile)
        for line in ifh.xreadlines():
            line = line.rstrip("\n")
            if state == 0:
                ofh.write(line + "\n")
                if line == 'sequence offset' or line == 'sequence number':
                    state += 1
                continue
            if state == 1:
                buf += line + "\n"
                if re.match('^(\D+|\d+)$', line):
                    continue
                m = re.match('\w+ ([\d.]+) \d+(?: ([\d.]+))?', line)
                if not m:
                    warn('Something wrong in state 1: %s' % line)
                    continue
                d = float(m.group(2) if m.group(2) else m.group(1))
                if d < begin:
                    buf = ''
                    continue
                elif begin <= d and d <= end:
                    ofh.write(buf)
                    buf = ''
                    state = state + 1
                    continue
            if state == 2:
                buf += line + "\n"
                if re.match('^(\D+|\d+)$', line):
                    continue
                m = re.match('\w+ ([\d.]+)', line)
                if not m:
                    warn('Something wrong in state 2: %s' % line)
                    continue
                d = float(m.group(1))
                if begin <= d and d <= end:
                    ofh.write(buf)
                    buf = ''
                    continue
                elif d > end:
                    continue
        ofh.close()
        ifh.close()

    def run(self):
        """Xplot file is opened (and normally doesn't print anything to
           stdout). The modified version prints by pressing 'c' the begin
           and end time of the current view. This view is then written to
           a new file.
        """

        xplot = Popen(["xplot", self.infile], bufsize=0, stdout=PIPE, shell=False).stdout
        while True:
            line = xplot.readline()
            if not line:
                break
            begin, end = re.match("<time_begin:time_end> = <([\d.]+):([\d.]+)>", line).group(1, 2)
            begin = float(begin)
            end   = float(end)
            self.cut(begin, end, self.infile, "%s_%s_%s.xpl" % (self.infile, begin, end))

    def main(self):
        self.parse_option()
        self.set_option()
        self.run()

# this only runs if the module was *not* imported
if __name__ == '__main__':
    XplotCut().main()
