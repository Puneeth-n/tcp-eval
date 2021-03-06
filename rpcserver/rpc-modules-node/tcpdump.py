#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vi:et:sw=4 ts=4

# Copyright (C) 2007 - 2011 Arnd Hannemann <arnd@arndnet.de>
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
import errno
import re
from logging import info, debug, warn, error, critical
from tempfile import mkstemp

# twisted imports
from twisted.internet import defer, protocol, reactor, threads
from twisted.internet import error as twisted_error
from twisted.web import xmlrpc

# tcp-eval imports
from network.rpcservice import RPCService
from network.functions import twisted_sleep
from common.functions import execute, CommandFailed

class Tcpdump(xmlrpc.XMLRPC):
    """Class for managing the packet capturing"""

    # Error codes (used by xmlrpc_stop)
    #   NOT_RUNNING     Trying to stop tcpdump, but tcpdump is not running
    #   STOPPING_FAILED Failed to stop running tcpdump instance
    #   STOPPED         Tcpdump stopped successfully
    STOPPED = 0
    NOT_RUNNING = 1
    STOPPING_FAILED = 2

    def __init__(self, parent = None):
        # Call super constructor
        xmlrpc.XMLRPC.__init__(self)

        if os.path.exists("/usr/local/sbin/tcpdump"):
            self._daemon = "/usr/local/sbin/tcpdump"
        else:
            self._daemon = "/usr/sbin/tcpdump"

        self._name = "tcpdump"
        self._proc = None

    @defer.inlineCallbacks
    def xmlrpc_start(self, iface, expr, promisc=False, options=None):
        """Start tcpdump instance for interface iface with filter expr.

           If successful, returns the file name of the pcap dump, else an empty
           string.
        """

        # Fail if there is already a tcpdump instance (started by us) running.
        if self._proc is not None and self._proc.active():
            error("Tcpdump already started!")
            defer.returnValue(None)

        # FIXME: -Z?
        cmd = [self._daemon, "-i", iface, "-w", "-"]
        if options is not None and options['tcpdump_snaplen']:
            cmd.extend(['-s', str(options['tcpdump_snaplen'])])
        if not promisc:
            cmd.append("-p")

        cmd.append(expr)
        dir = "/mnt/scratch/%s/tcpdump" % Node().getHostname()

        try:
            os.mkdir(dir)
            os.chmod(dir, 0777)
        except OSError, inst:
            if inst.errno != errno.EEXIST:
                error(inst)
                defer.returnValue(None)

        try:
            temp_fd, temp_file = mkstemp(suffix=".pcap", dir=dir)
            os.chmod(temp_file, 0666)
        except OSError, inst:
            error(inst)
            defer.returnValue(None)

        self._proc = _TcpdumpProtocol()
        debug("spawnProcess: %s" %cmd)
        reactor.spawnProcess(self._proc, self._daemon, args = cmd, path='/',
                childFDs = {1: temp_fd, 2: "r"})
        os.close(temp_fd)

        success, status, stderr = yield self._proc.deferred()

        if not success:
            error("Tcpdump failed (exit status: %s):" % status)
            error(stderr)
            os.unlink(temp_file)
            defer.returnValue(None)
        else:
            info("Tcpdump started.")
            defer.returnValue(temp_file)

    @defer.inlineCallbacks
    def xmlrpc_stop(self):
        """Stop an tcpdump instance started by xmlrpc_start.

           Returns one of Tcpdump.{NOT_RUNNING,STOPPED,STOPPING_FAILED}
        """

        if self._proc is None:
            defer.returnValue(Tcpdump.NOT_RUNNING)
        rc =  yield self._proc.kill()
        self._proc = None
        if rc:
            info("Tcpdump stopped.")
            defer.returnValue(Tcpdump.STOPPED)
        else:
            warning("Stopping of tcpdump failed RC=%s" %rc)
            defer.returnValue(Tcpdump.STOPPING_FAILED)


class _TcpdumpProtocol(protocol.ProcessProtocol):
    """ProcessProtocol instance for using tcpdump which tries to detect, if
       tcpdump was successfully started.

       This is signalled by the deferred returned by _Tcpdump.deferred().

       Returns a 3-tuple (success, status, stderr), where success is a Boolean,
       status either None or an exit status and stderr the output of tcpdump on fd 2.
    """

    def __init__(self):
        self._stderr = []
        self._ended = False
        self._fired = False
        self._timeout = None
        self._deferred = defer.Deferred()

    def deferred(self):
        return self._deferred

    def connectionMade(self):
        self.transport.closeStdin()

    def active(self):
        return not self._ended

    def errReceived(self, data):
        """Accumulates stderr output, till a whole line was collected. Iff this
           line is "listening on ...", tcpdump start is considered successful,
           else failed.
        """

        if self._fired:
            return
        self._stderr.append(data)
        if data.find('\n') == -1:
            return
        # This expects tcpdump to output an line like
        #   tcpdump: listening on eth1, link-type EN10MB (Ethernet), capture size 96 bytes
        # as first output on stderr ...
        stderr = "".join(self._stderr)
        self._fired = True
        if re.search("listening on.*link-type", stderr):
            self._deferred.callback((True, None, stderr))
        else:
            self._deferred.callback((False, None, stderr))

    @defer.inlineCallbacks
    def kill(self):
        """Stop tcpdump instance.

           Returns a Deferred, which evaluetes to True, if tcpdump could be TERMed
           or KILLed; else to False.
        """

        try:
            self.transport.signalProcess('TERM')
            self._timeout = twisted_sleep(2)
            if (yield self._timeout):
                defer.returnValue(True)

            self.transport.loseConnection()
            self.transport.signalProcess('KILL')
        except twisted_error.ProcessExitedAlready:
            defer.returnValue(True)

        self._timeout = twisted_sleep(2)
        if (yield self._timeout):
            defer.returnValue(True)
        else:
            defer.returnValue(False)

    def processEnded(self, status):
        self._ended = True
        if self._timeout is not None and self._timeout.callLater.active():
            self._timeout.callLater.cancel()
            self._timeout.callback(True)
        if not self._fired:
            self._deferred.callback((False, status, "".join(self._stderr)))
