#!/bin/bash

umask 027
BACKUP_DIR=${1:-/backup/subversion}

if [ ! -d $BACKUP_DIR ]; then mkdir -p $BACKUP_DIR; fi
for i in /srv/svn/*; do
    BACKUP_FILE=`basename "$i"`
    svnadmin dump "$i" -q | gzip > $BACKUP_DIR/$BACKUP_FILE.gz
done