#!/bin/sh
#### DO NOT MODIFY THIS SECTION ###
export BUILDAH_FORMAT=dockerv2
###################################

#### MODIFY THIS SECTION FOR YOUR ENVIRONMENT ###

export offline_registry_catalog_repo_url=aamirian:5000
export offline_registry_olm_images_repo_url=aamirian:5000
export catalog_version=1.0.0
##################################################


python mirror-operator-catalogue.py