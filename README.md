# OpenShift Offline Operator Catalog Build and Mirror

This script will create a custom operator catalogue based on the desired operators and mirror the images to a local registry.

FAQ:

Why create this?

Because the current catalog build and mirror (https://docs.openshift.com/container-platform/4.3/operators/olm-restricted-networks.html) takes 1-5 hours to create and more than 50% of the catalog is not usable offline anyways. This tool allows you to create a custom catalog with only the operators you need.

Why is the code so ugly?

This is a quick and dirty first version. Any contributions to make this prettier are welcome.

## Requirements

This tool was tested with the following tools

1. Python 3.7.6
2. Podman v1.8
3. Skopeo 0.1.41

Please note this only works with operators that meet the following criterea

1. Have a CSV in the manifest that contains a full list of related images
2. The related images are tagged with a SHA

For a full list of operators that work offline please see link below
<https://access.redhat.com/articles/4740011>

## Running the script

1. Install the tools listed in the requirments section
2. To authenticate use the parameter --authfile <pull-secret>
    a. The auth file is a json file generated when you do a docker or podman login to a registry. You should do a login against registry.redhat.io as well as your offline registry (if authentication is required).
    b. The auth file is located either in your home directory under .docker or under /run/user/your_uid/containers/auth.json
3. Update the offline-operator-list file with the operators you want to include in the catalog creation and mirroring. See <https://access.redhat.com/articles/4740011> for list of supported offline operators.
4. Execute the app. Use --help to see the options:
```Shell
./mirror-operator-catalogue.py --help
```
6. Disable default operator source
```Shell
oc patch OperatorHub cluster --type json -p '[{"op": "add", "path": "/spec/disableAllDefaultSources", "value": true}]'
```
7. Apply the yaml files in the publish folder
    a. The image content source policy will create a new MCO render which will start a rolling reboot of your cluster nodes. You have to wait until that is complete before attemtping to install operators from the catalog

## Script Notes

Unfortuneately just because an image is listed in the related images spec doesn't mean it exists or is even used by the operator. for example registry.redhat.io/openshift4/ose-promtail from the logging operator. I have put that image in the knownBadImages file to avoid attempting to mirror. Other images will be added as I find them.

## Local Docker Registry

If you need a to create a local secured registry follow the instructions from the link below
<https://docs.openshift.com/container-platform/4.3/installing/install_config/installing-restricted-networks-preparations.html#installing-restricted-networks-preparations>
