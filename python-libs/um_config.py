#!/usr/bin/env python
# -*- coding: utf-8 -*-

# global informations
svnrepos    = 'svn://mesh.umic.rwth-aachen.de/umic-mesh'
imageprefix = '/opt/umic-mesh/images'
bootprefix  = '/opt/umic-mesh/boot'
svnprefix   = '/opt/checkout'

# informations about the kernel
kernelinfos = dict(
    mirror = 'http://sunsite.informatik.rwth-aachen.de/ftp/pub/Linux/kernel/',
    version = '2.6.16.29',
    srcpath = '/usr/src',
)

# informations about olsr
olsrinfos = dict(
    remote_repos    = ':pserver:anonymous@olsrd.cvs.sourceforge.net:/cvsroot/olsrd',
    remote_module   = 'olsrd-current',
    local_upstream  = '/routing/olsr/trunk',
    local_trunk     = '/routing/olsr/branches/um-version-olsr5'
)

# informations about madwifi
madwifiinfos = dict(
    remote_repos    = 'http://svn.madwifi.org',
    remote_module   = '/trunk',
    local_upstream  = '/drivers/madwifi-ng/trunk',
    local_trunk     = '/drivers/madwifi-ng/branches/um-version'
)

# informations about the umic-mesh nodes
nodeinfos = dict(
    vmeshhost = dict(
        hostnameprefix = 'vmeshhost',
        imagetype      = 'vmeshhost',
        imageversion   = 'um_edgy',
        startup        = [],
    ),
    vmeshrouter = dict(
        hostnameprefix = 'vmrouter',
        imagetype      = 'vmeshnode',
        imageversion   = 'um_edgy',
        xenconfig      = 'config0',
        meshdevices    = {},
        startup        = [],
    ),
    meshrouter = dict(
        hostnameprefix = 'mrouter',
        imagetype      = 'meshnode',
        imageversion   = 'um_edgy',
        meshdevices    = { 'ath0' : 'wlancfg0', 'ath1' : 'wlancfg2' },
        startup        = [ 'execpy(["/usr/local/sbin/um_madwifi", "--debug", "loadmod"])',
                           'Madwifi("ath0").start()',
                           'Madwifi("ath1").start()' ]
#                           'execpy(["/usr/local/sbin/um_madwifi", "--debug", "--dev=ath0", "start"])',
#                           'execpy(["/usr/local/sbin/um_madwifi", "--debug", "--dev=ath1", "start"])',
#                           'call(["/etc/init.d/snmpd", "start"], shell=False)' ] 
    )
)

# informations about the different images
imageinfos = dict(
    vmeshhost = dict(
        svnmappings = { '/config/vmeshhost/trunk' : 'config',
                        '/linux/xen/trunk' : 'linux/default',
                        '/tools/nuttcp/branches/um-version' : 'tools/nuttcp',
                        '/tools/thrulay/branches/advanced' : 'tools/thrulay',
                        '/tools/twisted/branches/um-version' : 'tools/twisted',
                        '/boot/bios/trunk' : 'boot/bios',
                        '/boot/etherboot/trunk' : 'boot/etherboot',
                        '/scripts/python-libs' : 'scripts/python-libs',
                        '/scripts/image' : 'scripts/image',
                        '/scripts/vmesh' : 'scripts/vmesh',
                        '/scripts/util' : 'scripts/util',
                        '/scripts/measurement' : 'scripts/measurement' },
        scriptmappings = { 'scripts/image' : '/usr/local/sbin',
                           'scripts/vmesh' : '/usr/local/sbin',
                           'scripts/image' : '/usr/local/sbin',
                           'scripts/measurement' : '/usr/local/bin'  }
    ),
    vmeshnode = dict(
        svnmappings = { '/config/vmeshnode/trunk' : 'config',
                        '/linux/xen/trunk' : 'linux/default',
                        '/linux/xen/branches/linux-2.6.16.29-xen-elcn' : 'linux/elcn',
                        '/routing/olsr/branches/um-version-olsr4' : 'routing/olsr4',
                        '/routing/olsr/branches/um-version-olsr5' : 'routing/olsr5',
                        '/tools/nuttcp/branches/um-version' : 'tools/nuttcp',
                        '/tools/thrulay/branches/advanced' : 'tools/thrulay',
                        '/tools/tcpdump/branches/um-version-elcn' : 'tools/tcpdump',
                        '/tools/set-tcp_elcn/' : 'tools/set-tcp_elcn',
                        '/scripts/python-libs' : 'scripts/python-libs',
                        '/scripts/vmesh' : 'scripts/vmesh',
                        '/scripts/util' : 'scripts/util' },
        scriptmappings = { 'scripts/vmesh' : '/usr/local/sbin',
                           'scripts/util' : '/usr/local/bin' }
    ),
    meshnode = dict(
        svnmappings = { '/config/vmeshnode/trunk' : 'config',
                        '/linux/vanilla/trunk' : 'linux/default',
                        '/linux/vanilla/branches/linux-2.6.16.29-ring3' : 'linux/ring3',
                        '/linux/vanilla/branches/linux-2.6.16.29-elcn' : 'linux/elcn',
                        '/routing/olsr/branches/um-version-olsr4' : 'routing/olsr4',
                        '/routing/olsr/branches/um-version-olsr5' : 'routing/olsr5',
                        '/drivers/madwifi-ng/branches/um-version' : 'drivers/madwifi-ng',
                        '/drivers/madwifi-ng/branches/um-version-elcn' : 'drivers/madwifi-ng-elcn',
                        '/projects/meshconf/net-snmp/branches/um-version' : 'projects/meshconf/net-snmp',
                        '/tools/set-tcp_elcn' : 'tools/set-tcp_elcn',
                        '/tools/nuttcp/branches/um-version' : 'tools/nuttcp',
                        '/tools/thrulay/branches/advanced' : 'tools/thrulay',
                        '/tools/tcpdump/branches/elcn' : 'tools/tcpdump',
                        '/tools/libpcap/branches/ring3' : 'tools/libpcap',
                        '/tools/libpfring/branches/um-version' : 'tools/libpfring',
                        '/tools/twisted/branches/um-version' : 'tools/twisted',
                        '/scripts/python-libs' : 'scripts/python-libs',
                        '/scripts/rpcserver' : 'scripts/rpcserver',
                        '/scripts/mesh' : 'scripts/mesh',
                        '/scripts/init' : 'scripts/init',
                        '/scripts/util' : 'scripts/util' },
        scriptmappings = { 'scripts/mesh' : '/usr/local/sbin',
                           'scripts/util' : '/usr/local/bin',
                           'scripts/init' : '/usr/local/sbin' }
    )
)

# device configurations
deviceconfig = dict(
    wlancfg0 = dict(
        hwdevice = 'wifi0',
        essid    = 'umic-mesh-ah',
        channel  = 1,
        antenna  = 2,
        address  = '169.254.9.@NODENR/16',
        wlanmode = 'ahdemo',
        txpower  = 0
    ),
    wlancfg1 = dict(
        hwdevice = 'wifi1',
        essid    = 'umic-mesh-sta',
        channel  = 11,
        antenna  = 2,
        address  = '169.254.10.@NODENR/16',
        wlanmode = 'sta',
        txpower  = 0
    ), 
    wlancfg2 = dict(
        hwdevice = 'wifi1',
        essid    = 'umic-mesh-ah2',
        channel  = 11,
        antenna  = 2,
        address  = '169.254.10.@NODENR/16',
        wlanmode = 'ahdemo',
        txpower  = 0
    )
)

# xen configurations
xenconfig = dict(
    config0 = dict(
        ramdisk = 'initrd/vmeshnode-initrd',
        kernel  = 'linux/default/vmeshnode-vmlinuz',
        memory  = 40
    )
)
