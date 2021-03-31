#!/bin/bash -x

BUNDLE_DIR='bundle'
BUNDLE_NAME='compliance-bundle.tar.gz'
HOST_DIR='/host/'
AUTH_TOKEN=$1
AUTH_FILE='auth.json'


function __startRegistry() {
  podman container stop registry
  podman container rm registry
  mkdir -p operators
  podman run -d --rm \
  -p 5000:5000 \
  --name registry \
  -v ./operators:/var/lib/registry \
  registry:2
}

function __stopRegistry() {
  podman container stop registry
  podman container rm registry
}

function __consolidate() {

  mkdir -p bundle
  mv operators bundle/
  mv publish bundle/

}

function __extractCreds() {
  RH_PS=$(echo $1 | jq -r '.auths."registry.redhat.io".auth' | base64 -d -)
  ID=$(grep -o -P "^.+(?=:)" <<< $RH_PS)
  PASS=$(grep -o -P "(?<=\:)(.+$)" <<< $RH_PS)
  echo "$ID $PASS"
}

function __podmanLogin() {
  podman login registry.redhat.io --username $1 --password $2
}

function __writeAuth() {
  echo $1 > auth.json
}

function __mirror() {
  ./mirror-operator-catalogue.py \
    --catalog-version 1.0.0 \
    --authfile $1 \
    --registry-olm localhost:5000 \
    --registry-catalog localhost:5000 \
    --operator-file ./offline-operator-list \
    --icsp-scope=namespace
}

function bundle() {

# Write Auth file
__writeAuth ${AUTH_TOKEN}

# Extract credentials
read UN PASS < <(__extractCreds ${AUTH_TOKEN})

# Podman login
__podmanLogin $UN $PASS

# Start the registry
__startRegistry

# Run the mirroring script
__mirror $AUTH_FILE

# Stop the registry
__stopRegistry

# Consolidate
__consolidate

# Compress
tar -czvf ${BUNDLE_NAME} ${BUNDLE_DIR}


# Export
mv ${BUNDLE_NAME} ${HOST_DIR}

}

bundle

