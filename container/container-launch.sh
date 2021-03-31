#!/bin/bash

podman run \
  -it --security-opt label=disable \
  -v ./:/host   -v /dev/fuse:/dev/fuse:rw \
  -v operators:/var/lib/containers:rw \
  --rm --ulimit host --privileged \
  quay.io/redhatgov/operator-mirror:offline-dev $@

