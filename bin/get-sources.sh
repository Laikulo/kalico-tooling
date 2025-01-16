#!/usr/bin/env bash

klippy_version="${1:-v0.12.0}"
klippy_upstream="${2:-https://github.com/KalicoCrew/kalico.git}"
if [[ -d upstream ]]; then
	rm -rf upstream
fi

mkdir upstream
cd upstream
git init
git fetch "${klippy_upstream}" --tags "${klippy_version}"
git checkout FETCH_HEAD
