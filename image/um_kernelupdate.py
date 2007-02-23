#!/usr/bin/env python
# -*- coding: utf-8 -*-

# python imports
from logging import info, debug, warn, error

# umic-mesh imports
from um_application import Application
from um_util import *


class KernelUpdate(Application):
    "Class to handle kernel source update within images"

    def __init__(self):
        "Constructor of the object"

        Application.__init__(self)


    def set_option(self):
        "Set options"

        Application.set_option(self)


    def kernelupdate(self):
        "Update Kernel source"

        # get nodetype
        nodetype = getnodetype()

        # for kernelupdate only works for meshnodes
        if nodetype == "meshnode":
            kernel = "linux-%s" %(kernelinfos["version"])
            tmp = "/tmp/kernelupdate"
            dst = "%s/%s" %(tmp, kernel)
            cmd = "mkdir -p %s" %(dst)
            execute(cmd, shell = True)
        else:
            raise NotImplementedError()

        # check out upstream files
        info("Check out kernel upstream")
        cmd = ("svn",  "checkout", "%s/boot/linux/branches/upstream" \
              %(svninfos["svnrepos"]), dst)
        info(cmd)
        call(cmd, shell = False)

        # download kernel image and extract
        cmd = "wget %s/v2.6/%s.tar.gz -O - | tar xz -C %s" \
              %(kernelinfos["mirror"], kernel, tmp)
        info(cmd)
        call(cmd, shell = True)

        # get revision
        cmd = "svn info %s | grep Revision | awk '{print $2;}'" %(dst)
        info(cmd)
        (stdout, stderr) = execute(cmd, shell = True)
        local_revision = stdout.splitlines()[0]
        info(local_revision)

        # commit new versions of files to upstream repository
        cmd = ("svn", "commit", dst, "-m","updated kernel to %s" %(kernel))
        info(cmd)
        call(cmd, shell = False)

        # switch repository to trunk
        cmd = ("svn", "switch", "%s/boot/linux/trunk" %(svninfos["svnrepos"]), dst)
        info(cmd)
        call(cmd, shell = False)

        # merge upstream with trunk
        cmd = ("svn", "merge", "-r", "%s:HEAD" %(local_revision),
               "%s/boot/linux/branches/upstream" %(svninfos["svnrepos"]), dst)
        info(cmd)
        call(cmd, shell = False)

        # remove modified files and svn infos
        cmd = "rm -rf `find %s -name .svn`" %(dst)
        info(cmd)
        call(cmd, shell = True)
        for i in kernelinfos["modifiedfiles"]:
            cmd = "rm -v %s/%s" %(dst,i)
            call(cmd, shell = True)

        # copy other files to images
        for img in imageinfos.iterkeys():
            imgdst = "%s/%s/meshnode/opt/meshnode/linux" %(imageprefix, img)
            cmd = "mkdir -vp %s" %(imgdst)
            call(cmd, shell = True)
            cmd = "cp -r %s/* %s" %(dst, imgdst)
            info(cmd)
            call(cmd, shell = True)

        # clean up
        info("Cleaning up %s..." %(tmp))
        cmd = "rm -rf %s" %(tmp)
        execute(cmd, shell = True)
        info("Done.")


    def main(self):
        "Main method of the kernelupdate object"

        self.parse_option()
        self.set_option()
        self.kernelupdate()



if __name__ == "__main__":
    KernelUpdate().main()
