# OpenShift Offline Operator Catalog Build and Mirror

This script will create a custom operator catalogue based on the desired operators and mirror the images to a local registry.

Why create this?

Because the current catalog build and mirror (https://docs.openshift.com/container-platform/4.3/operators/olm-restricted-networks.html) takes 1-5 hours to create and more than 50% of the catalog is not usable offline anyways. This tool allows you to create a custom catalog with only the operators you need.


## Requirements

This tool was tested with the following tools

1. Python 3.7.6
2. Podman v1.8 (If you use anything below 1.8, you might run into issues with multi-arch manifests)
3. Skopeo 0.1.41

Please note this only works with operators that meet the following criterea

1. Have a CSV in the manifest that contains a full list of related images
2. The related images are tagged with a SHA

For a full list of operators that work offline please see link below
<https://access.redhat.com/articles/4740011>

## Running the script

1. Install the tools listed in the requirments section
2. Login to your offline registry using podman (This is the registry where you will be publishing the catalogue and related images)
3. Login to registry.redhat.io using podman
4. Update the offline-operator-list file with the operators you want to include in the catalog creation and mirroring. See <https://access.redhat.com/articles/4740011> for list of supported offline operators.
5. Run the script

```Shell
mirror-operator-catalogue.py \
--catalog-version 1.0.0 \
--authfile /run/user/0/containers/auth.json \
--registry-olm localhost:5000 \
--registry-catalog localhost:5000 \
--operator-file ./offline-operator-list
```

6. Disable default operator source
```Shell
oc patch OperatorHub cluster --type json -p '[{"op": "add", "path": "/spec/disableAllDefaultSources", "value": true}]'
```
7. Apply the yaml files in the publish folder. The image content source policy will create a new MCO render which will start a rolling reboot of your cluster nodes. You have to wait until that is complete before attemtping to install operators from the catalog


##### Script Arguements

###### --catalog-version

Arbitrariy version number to tag your catalogue image


###### --authfile

The location of the auth.json file generated when you use podman or docker to login registries using podman. The auth file is located either in your home directory under .docker or under /run/user/your_uid/containers/auth.json


###### --registry-olm

The URL of the destination registry where the operator images will be mirroed to


###### --registry-catalog

The URL of the destination registry where the operator catalogue image will be published to


###### --operator-file

Location of the file containing a list of operators to include in your custom catalog. The entries should be in plain text with no quotes. Each line should only have one operator name. 

Example:

```Shell
local-storage-operator
cluster-logging
codeready-workspaces
```



## Script Notes

Unfortuneately just because an image is listed in the related images spec doesn't mean it exists or is even used by the operator. for example registry.redhat.io/openshift4/ose-promtail from the logging operator. I have put that image in the knownBadImages file to avoid attempting to mirror. Other images will be added as I find them.

## Local Docker Registry

If you need a to create a local secured registry follow the instructions from the link below
<https://docs.openshift.com/container-platform/4.3/installing/install_config/installing-restricted-networks-preparations.html#installing-restricted-networks-preparations>
