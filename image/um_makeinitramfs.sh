#!/bin/bash

# image path 
IMAGEDIR_EDGY="/opt/umic-mesh/images/vmeshrouter"

# destination -$IMAGE will be appended to this
INITRD_DST=/opt/umic-mesh/boot/initrd/initramfs

# temp directory copying files
INITRD_TMP=/tmp/initrd

# path of configuration files etc, to copy in
FILE_DIR=/opt/checkout/boot/initrd

# directorys to create
DIRS="/usr/sbin,/newroot,/proc,/sbin,/dev/net,/var/lib/dhcp"
DIRS="$DIRS,/var/lib/dhcp3,/var/log,/var/run,/etc"
DIRS="$DIRS,/bin,/lib,/etc,/lib/dhcp3-client"

# files which belong to /bin
BINFILES="bash,cat,chmod,echo,expr,grep,hostname,"
BINFILES="$BINFILES,kill,logger,ls,mknod,mount,ping,rm,sed"
BINFILES="$BINFILES,sh,sleep,umount,uname,run-init,chroot"

# files which belong to /sbin
SBINFILES="brctl,dhclient3,dhclient,hwclock,ifconfig,insmod,ip,losetup"
SBINFILES="$SBINFILES,modprobe,ntpdate,portmap,route"
SBINFILES="$SBINFILES,ethtool,syslog-ng,strace"

# some static files, which are copied only for ubuntu
STATIC="/bin/ip,/lib/dhcp3-client/call-dhclient-script"

# where to search for executables and librarys
LIB_SEARCHPATH="/lib,/usr/lib,/usr/lib/i586"
BIN_SEARCHPATH="/bin,/usr/bin,/sbin,/usr/sbin,/usr/lib/klibc/bin"

# librarys which are copied for ubuntu edgy initramfs
LIBS_EDGY="ld-2.4.so,ld-linux.so.2,libblkid.so.1,libblkid.so.1.0,libc-2.4.so,libcap.so.1,libcap.so.1.10,libcrypto.so.0.9.8,libc.so.6,libdl-2.4.so,libdl.so.2,liblzo.so.1,liblzo.so.1.0.0,libncurses.so.5,libncurses.so.5.5,libnsl.so.1,libnss_dns.so.2,libnss_dns-2.4.so,libnss_files.so.2,libnss_files-2.4.so,libproc-3.2.7.so,libpthread-2.4.so,libpthread.so.0,libresolv-2.4.so,libresolv.so.2,librt-2.4.so,librt.so.1,libssl.so.0.9.8,libutil-2.4.so,libutil.so.1,libuuid.so.1,libuuid.so.1.2,libwrap.so.0,libwrap.so.0.7.6,libz.so.1,libz.so.1.2.3,libacl.so.1,libacl.so.1.1.0,libselinux.so.1,libattr.so.1,libattr.so.1.1.0,libsepol.so.1,libnsl.so.1,libnsl-2.4.so,libnss_compat.so.2,libnss_compat-2.4.so,libsysfs.so.2,libsysfs.so.2.0.0,klibc-gk2XW_qpdO7ELQ5NYkvZBbv1VsI.so"


function makedev() {
   # loop devices
   for i in 0 1 2 3 4 5 6 7; do
       mknod $INITRD_TMP/dev/loop$i b 7 $i
   done;
  
   # console, null, random, urandom, tty12
   mknod $INITRD_TMP/dev/console c 5 1
   mknod $INITRD_TMP/dev/null    c 1 3
   mknod $INITRD_TMP/dev/random  c 1 8
   mknod $INITRD_TMP/dev/urandom c 1 9
   mknod $INITRD_TMP/dev/tty12   c 4 12
   
   # net tun
   mknod $INITRD_TMP/dev/net/tun c 10 200
   
}

# filecopy "$files" "$searchpath" "$dstdir"
function filecopy () {
    for file in ${1//,/ }; do
        FOUND=n
        for dir in ${2//,/ }; do
            dir="${IMAGEDIR}$dir"
            if [ -e $dir/$file ]; then
                cp $CPOPTS $dir/$file $3;
                FOUND=y
                break;
            fi;
        done;
        if [ $FOUND = n ]; then
            echo "Warning: failed to locate $file!"
        fi
    done;
}


function usage ()
{
    this=`basename $0`
    cat <<!EOF!
usage: $this [options] image
options:
  -h        Print this help summary and exit.
  -v        Be more verbose.

image should be edgy.
!EOF!
}


# check if root
if [ $UID -ne 0 ]; then
    echo "Must be root!"
    usage;
    exit 1;
fi;

# parse optional arguments
getopts vh FLAG
if [ "$?" -ne 0 ]; then
    FLAG="null"
fi

VERBOSE=n 
case $FLAG in
    "v")
        VERBOSE=y; shift ;;
    "h")
        usage; exit 0;;
esac


# if there is no image argument, print usage and exit
IMAGE=$1;
if [ -z $IMAGE ]; then
    echo "You have to specify an image name."
    usage; exit 1;
fi

case $IMAGE in
    edgy)
        LIBS=$LIBS_EDGY
        IMAGEDIR=$IMAGEDIR_EDGY ;;
    *)
        echo "Unknown image type: $IMAGE"; usage; exit 2; ;;
esac

INITRD_DST="$INITRD_DST-$IMAGE";

echo "Generating $INITRD_DST..."

# options for invocation of "cp"
CPOPTS="--update --no-dereference --preserve=mode,ownership,timestamps,link"
if [ $VERBOSE = y ]; then
    CPOPTS="--verbose $CPOPTS"
fi;

# Options for invocation of "mkdir"
MKOPTS="-p"
if [ $VERBOSE = y ]; then
    MKOPTS="-v $MKOPTS"
fi;

# create tmp directory
mkdir $INITRD_TMP
if [ $? -ne 0 ]; then 
    echo Creating $INITRD_TMP failed, please remove it manually.
    exit 1;
fi

# create directories
for dir in ${DIRS//,/ }; do
  mkdir $MKOPTS $INITRD_TMP/$dir 
done

# copy binfiles
filecopy "$BINFILES" "$BIN_SEARCHPATH" "$INITRD_TMP/bin/"

# copy sbinfiles
filecopy "$SBINFILES" "$BIN_SEARCHPATH" "$INITRD_TMP/sbin/"

# copy libs
filecopy "$LIBS" "$LIB_SEARCHPATH" "$INITRD_TMP/lib/"

# copy static files 
for file in ${STATIC//,/ }; do
    cp $CPOPTS ${IMAGEDIR}$file ${INITRD_TMP}${file}
done;


# make a dhcp client link for ubuntu edgy eft
if [ "$IMAGE" = "edgy" ]; then
    ln -vs /etc/dhcp/dhclient-script $INITRD_TMP/sbin
fi;

# make /dev nodes
makedev;

cp -a $FILE_DIR/etc $INITRD_TMP/
cp -a $FILE_DIR/*rc $INITRD_TMP/
cp -a $FILE_DIR/initrd $INITRD_TMP/

# link /init to /linuxrc
(cd $INITRD_TMP && ln linuxrc init)

# build initramfs
(cd $INITRD_TMP && find . | cpio --quiet -o -H newc | gzip -9 > $INITRD_DST.gz)

# celanup
rm -rf $INITRD_TMP

echo "Done."