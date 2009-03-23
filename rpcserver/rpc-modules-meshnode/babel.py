#!/usr/bin/env python2.5
# -*- coding: utf-8 -*-

import os
from logging import info, debug, warn, error, critical
from tempfile import mkstemp

# twisted imports
from twisted.internet import defer, threads, protocol, utils
from twisted.web import xmlrpc

from um_rpcservice import RPCService
from um_twisted_functions import twisted_execute, twisted_call
          

class Babel(RPCService):
    """Class for managing the babel routing daemon"""


    #
    # Public XMLRPC Interface
    #

    @defer.inlineCallbacks
    def xmlrpc_restart(self):
        rc = yield self.reread_config()
        
        if rc == 0:
            # don't complain if stopping doesnt work
            yield self.stop()
            rc = yield self.start()
        defer.returnValue(rc)

    @defer.inlineCallbacks
    def xmlrpc_start(self):
        rc = yield self.reread_config()
        if rc == 0:            
            rc = yield self.start()
        defer.returnValue(rc)

    def xmlrpc_stop(self):
        return self.stop()

    @defer.inlineCallbacks
    def xmlrpc_isAlive(self):
        """ Check if babel is alive by looking in the process table. """
        cmd = ["/bin/ps", "-C", "babel" ]
        rc = yield twisted_call(cmd, shell=False)

        if (rc==0):
            defer.returnValue(True)
        else:
            defer.returnValue(False)


    #
    # Internal stuff
    #
    def __init__(self, parent = None):
        
        # Call super constructor
        RPCService.__init__(self, parent)

        self._name = "babel"
        self._config = None

        self._configfile = None

        self._daemon = "/usr/local/bin/babel"
    
    
    @defer.inlineCallbacks
    def reread_config(self):
        """ Rereads the configuration

            The babel service table has the following important columns
                 config : the config file contents

            Will return 0 on success.
            
        """
        
        # get service config out of database
        assoc = yield self._parent._dbpool.getCurrentServiceConfig(self._name)
        if not assoc:
            info("Found no configuration")
            defer.returnValue(-1)

        self._config = assoc

        if assoc['config']:        
                # set/create configfile
                if self._configfile and os.path.exists(self._configfile):
                    tempfile = file(self._configfile, 'w')
                else:
                    # create new tempfile
                    (temp_fd, self._configfile) = mkstemp(".conf", self._name)
                    info("Created new configfile: %s", self._configfile)
                    tempfile = os.fdopen(temp_fd, 'w') 
                tempfile.write(assoc['config'])
                tempfile.close()

        defer.returnValue(0)
                                   

    @defer.inlineCallbacks
    def start(self):
        """ This function invokes start-stop daemon to bring up babel """
        
        # set arguments
        args = ['-d', '0']

        try: args.extend(['-m', self._config['mcastaddress']])
        except: pass
        try: args.extend(['-p', self._config['port']])
        except: pass
        try: args.extend(['-h', self._config['hellointerval']])
        except: pass
        try: args.extend(['-H', self._config['whellointerval']])
        except: pass
        try: args.extend(['-i', self._config['ihellointerval']])
        except: pass
        try: args.extend(['-u', self._config['updateinterval']])
        except: pass

        try: args.extend(['-c', self._configfile])
        except: pass

        try: args.append(self._config['interfaces'])
        except: error("At least one interface has to be given!")

        # set command
        cmd = [ "start-stop-daemon", "--start",  
                "--exec", self._daemon,
                "--"]
        cmd.extend(args)
        (stdout, stderr, rc) = yield twisted_execute(cmd, shell=False)
        if len(stdout):
            debug(stdout)
        if (rc != 0):
            error("babel.start(): Command failed with RC=%s", rc)
            for line in stderr.splitlines():
                error(" %s" %line)
            # when an error occurs stdout is important too
            if len(stdout):
                stderr = stderr+stdout

        yield self._parent._dbpool.startedService(self._config,
                                                  rc, message=stderr)
        defer.returnValue(rc)

    @defer.inlineCallbacks
    def stop(self):
        """ This function invokes start-stop-daemon to stop babel """

        cmd = [ "start-stop-daemon", "--stop",  "--quiet",
                "--exec", self._daemon,
                "--signal", "TERM",
                "--retry",  "5"]
        (stdout, stderr, rc) = yield twisted_execute(cmd, shell=False)
        if len(stdout):
            debug(stdout)
        if (rc != 0):
            error("babel.stop(): Command failed with RC=%s", rc)
            for line in stderr.splitlines():
                error(" %s" %line)
        yield self._parent._dbpool.stoppedService(self._config,
                                                  rc, message=stderr)            
        defer.returnValue(rc)






        
        