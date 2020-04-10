#!/bin/bash

# Installation script for Kaldi
#
set -e

KALDI_GIT="-b pykaldi https://github.com/pykaldi/kaldi.git"

KALDI_DIR="$PWD/kaldi"

if [ ! -d "$KALDI_DIR" ]; then
  git clone $KALDI_GIT $KALDI_DIR
else
  echo "$KALDI_DIR already exists!"
fi

cd "$KALDI_DIR/tools"
git pull

# Prevent kaldi from switching default python version
mkdir -p "python"
touch "python/.use_default_python"

./extras/check_dependencies.sh

make -j 4

cd ../src
./configure --use-cuda=no --shared
make clean -j 4
make depend -j 4
make checkversion -j 4
make kaldi.mk -j 4
make mklibdir -j 4
make base matrix util feat tree gmm transform \
      fstext hmm lm decoder lat kws \
      bin fstbin gmmbin featbin latbin kwsbin -j 4


echo "Done installing Kaldi."
