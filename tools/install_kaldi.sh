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

# removes libraries that wont be used after installation for memory
make -j $(nproc) openfst OPENFST_CONFIGURE="--enable-shared --enable-bin --disable-dependency-tracking"
find . -type d -name "openfst*" -exec rm -rf {}/src/script/.libs \;

cd ../src
./configure --shared --use-cuda=no
make clean -j $(nproc) && make depend -j $(nproc) && make -j $(nproc) base matrix util feat tree gmm transform fstext hmm lm decoder lat kws

find . -name "*.a" -delete
find . -name "*.o" -delete

echo "Done installing Kaldi."
