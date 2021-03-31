#!/usr/bin/env bash

set -e


if [[ $# == 0 ]]; then
  if [[ -t 0 ]]; then
    echo
    echo "Starting shell..."
    echo

    exec "bash"
  else
    echo "An interactive shell was not detected."
    echo
    echo "By default, this container starts a bash shell, be sure you are passing '-it' to your run command."

    exit 1
  fi
else
  exec "$@"
fi
