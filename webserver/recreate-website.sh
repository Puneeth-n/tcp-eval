#/bin/sh

SVN_USER=
SVN_PASSWD=

if ! type -P bibtex2html > /dev/null ; then
	echo "ERROR: bibtex2html not found."
	exit 1
fi

if [ ! -d .svn ]; then
	echo "ERROR: This is not a working copy. Call this script in the website's working copy."
	exit 1
fi

URL=$(svn info . |grep "^URL:")

if [ "$URL" = "${URL%%umic-mesh/website/trunk}" ]; then
	echo "ERROR: Wrong repository?"
	exit 1
fi

if [ -n "$(svn --ignore-externals st . | grep -v ^X)"  ]; then
	if [ "$1" != "--force" ]; then
		echo "ERROR: Repository is not clean. Check with 'svn st'. Use --force to override check."
		exit 1
	fi
fi

# Check out website
rm -Rf .svn/ *
umask 0002
svn --username=$SVN_USER --password=$SVN_PASSWD co svn://www.umic-mesh.net/umic-mesh/website/trunk .

# Generate literature
TMPDIR=/tmp/$0.$$
svn --username=$SVN_USER --password=$SVN_PASSWD co svn://www.umic-mesh.net/diplomarbeiten/thesis/branches $TMPDIR
WARNING=
for user in $TMPDIR/*; do
	bibtex2html -b -R $user/literature/paper/ -f -P internal -O internal_theses/$(basename $user)/literature $user/literature/Literature.bib || WARNING="$WARNING $user"
done

if [ -n "$WARNING" ]; then
	echo "WARNING: Literature export failed for user(s):$WARNING"
fi
rm -Rf $TMPDIR

# Overlay literature for public research topics
ln -s ../../internal_theses/schaffrath/literature research/tcp
ln -s ../../internal_theses/ritzerfeld/literature research/autoconf

# Make WebDAVs writeable
find internal_theses/ research/ -exec chown www-data {} \;

exit 0


