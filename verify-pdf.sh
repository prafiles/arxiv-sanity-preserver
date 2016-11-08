#!/usr/bin/env bash

cd pdf

for f in *.pdf; do
  if pdfinfo "$f" > /dev/null; then
    : Nothing
  else
    echo "$f" is broken. Removing it.
    rm "$f"
  fi
done