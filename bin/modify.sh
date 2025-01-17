#!/usr/bin/env bash
set -ex
klippy_dir=${1:-klippy}
./bin/make-package.py "$klippy_dir"
pushd "$klippy_dir"
cp chelper/__init__.py chelper/stock_pkginit.py
if [[ ! "$2" == nopatch ]]; then
for i in ../patches/*.patch; do
	echo "Applying Patch \"$(basename $i)\""
	if ! patch -p1 < "$i"; then
		echo >&2 "Fatal: patch $i failed, fix and try again"
		exit 2
	fi
done
fi
popd
