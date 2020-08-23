# OpenShift Offline Operator Catalogue Build and Mirror

This script will create a custom operator catalogue based on the desired operators and mirror the images to a local registry.

Why create this?

Because the current catalogue build and mirror (https://docs.openshift.com/container-platform/4.3/operators/olm-restricted-networks.html) takes 1-5 hours to create and more than 50% of the catalogue is not usable offline anyways. This tool allows you to create a custom catalogue with only the operators you need.


## Requirements

This tool was tested with the following versions of the runtime and utilities.

1. Centos 7.8, Fedora 31
2. Python 3.7.6 (with pyyaml,jinja2 library)
3. Podman v1.8 (If you use anything below 1.8, you might run into issues with multi-arch manifests)
4. Skopeo 1.0 (If you use anything below 1.0 you might have issue with the newer manifests)

Please note this only works with operators that meet the following criteria

1. Have a CSV in the manifest that contains a full list of related images
2. The related images are tagged with a SHA

For a full list of operators that work offline please see link below
<https://access.redhat.com/articles/4740011>

## Running the script

1. Install the tools listed in the requirements section
2. Login to your offline registry using podman (This is the registry where you will be publishing the catalogue and related images)
3. Login to registry.redhat.io using podman
4. Login to quay.io using podman
5. Update the offline-operator-list file with the operators you want to include in the catalog creation and mirroring. See <https://access.redhat.com/articles/4740011> for list of supported offline operators
6. Run the script (sample command, see arguements section for more details)

```Shell
mirror-operator-catalogue.py \
--catalog-version 1.0.0 \
--authfile /run/user/0/containers/auth.json \
--registry-olm local_registry_url:5000 \
--registry-catalog local_registry_url:5000 \
--operator-file ./offline-operator-list \
--icsp-scope=namespace
```

7. Disable default operator source
```Shell
oc patch OperatorHub cluster --type json -p '[{"op": "add", "path": "/spec/disableAllDefaultSources", "value": true}]'
```
8. Apply the yaml files in the publish folder. The image content source policy will create a new MCO render which will start a rolling reboot of your cluster nodes. You have to wait until that is complete before attempting to install operators from the catalogue


##### Script Arguements

###### --catalog-version

Arbitrary version number to tag your catalogue image. Unless you are interested in doing AB testing, keep the release version for all subsequent runs.


###### --authfile

The location of the auth.json file generated when you use podman or docker to login registries using podman. The auth file is located either in your home directory under .docker or /run/user/your_uid/containers/auth.json or /var/run/containers/your_uid/auth.json


###### --registry-olm

The URL of the destination registry where the operator images will be mirrored to


###### --registry-catalog

The URL of the destination registry where the operator catalogue image will be published to


###### --operator-file

Location of the file containing a list of operators to include in your custom catalogue. The entries should be in plain text with no quotes. Each line should only have one operator name. 

Example:

```Shell
local-storage-operator
cluster-logging
codeready-workspaces
```

###### --icsp-scope

Scope of registry mirrors in imagecontentsourcepolicy file. Allowed values: namespace, registry. Defaults to: namespace

###### --mirror-images

This field is optional
Default: True

If set to True all related images will be mirrored to the registry provided by the --registry-olm arguement. Otherwise images will not be mirrored. Set to false if you are using a registry proxy and don't need to mirror images locally.

## Updating The Catalogue

To update the catalogue simply run the script the same way you did the first time. An updated Catalogue image will be created and it will override the existing one in your registry. The only step after that is to delete the redhat-operators pod in the openshift-marketplace namespace. A new pod will get created and it will pull the latest catalogue image. 

## Script Notes

Unfortunately just because an image is listed in the related images spec doesn't mean it exists or is even used by the operator. for example registry.redhat.io/openshift4/ose-promtail from the logging operator. I have put that image in the knownBadImages file to avoid attempting to mirror. Other images will be added as I find them.

## Local Docker Registry

If you need a to create a local secured registry follow the instructions from the link below
<https://docs.openshift.com/container-platform/4.3/installing/install_config/installing-restricted-networks-preparations.html#installing-restricted-networks-preparations>
