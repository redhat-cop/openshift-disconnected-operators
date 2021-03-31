# OpenShift Offline Operator Catalogue

This script will create a custom operator catalogue based on the desired operators and mirror the images to a local registry.

Why create this?

Because the current [catalogue build and mirror](https://docs.openshift.com/container-platform/4.6/operators/admin/olm-restricted-networks.html) process mirrors all versions of the operator which results in exponential amount of images that are mirrored that are unnecessary. For my use case only 100 images were required but I ended up with 1200 mirrored images.

## Note

This script has been update for OpenShift 4.6+. Please use the script in the ocp4.5 branch for releases 4.5 and earlier.

## Requirements

This tool was tested with the following versions of the runtime and utilities.

1. RHEL 8.2, Fedora 33 (For OPM tool RHEL 8 or Fedora equivalent is a hard requirement due to dependency on glibc version 2.28+)
2. Python 3.7.6 (with pyyaml,jinja2 library)
3. Podman v2.0+ (If you use anything below 1.8, you might run into issues with multi-arch manifests)
4. Skopeo 1.0+ (If you use anything below 1.0 you might have issue with the newer manifests)
5. Oc CLI 4.6.9+
6. sqlite3

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
    --authfile /var/run/containers/0/auth.json \
    --registry-olm local_registry_url:5000 \
    --registry-catalog local_registry_url:5000 \
    --operator-file ./offline-operator-list \
    --icsp-scope=namespace
    ```

7. Disable default operator source

    ```Shell
    oc patch OperatorHub cluster --type json \
        -p '[{"op": "add", "path": "/spec/disableAllDefaultSources", "value": true}]''
    ```

8. Apply the yaml files in the publish folder. The image content source policy will create a new MCO render which will start a rolling reboot of your cluster nodes. You have to wait until that is complete before attempting to install operators from the catalogue

### Script Arguments

#### --catalog-version

Arbitrary version number to tag your catalogue image. Unless you are interested in doing AB testing, keep the release version for all subsequent runs.


##### --authfile

The location of the auth.json file generated when you use podman or docker to login registries using podman. The auth file is located either in your home directory under .docker or /run/user/your_uid/containers/auth.json or /var/run/containers/your_uid/auth.json


##### --registry-olm

The URL of the destination registry where the operator images will be mirrored to


##### --registry-catalog

The URL of the destination registry where the operator catalogue image will be published to


##### --operator-file

Location of the file containing a list of operators to include in your custom catalogue. The entries should be in plain text with no quotes. Each line should only have one operator name. If this arguement is used, --operator-list should not be used

Example operator list file content:

```Shell
local-storage-operator
cluster-logging
codeready-workspaces
```

##### --operator-list

List of operators to include in your custom catalogue. If this arguement is used, --operator-file arguement should not be used.

The entires should be seperated by spaces

Example:

```Shell
--operator-list kubevirt-hyperconverged local-storage-operator
```

##### --icsp-scope

Scope of registry mirrors in imagecontentsourcepolicy file. Allowed values: namespace, registry. Defaults to: namespace

##### --mirror-images

This field is optional
Default: True

If set to True all related images will be mirrored to the registry provided by the --registry-olm arguement. Otherwise images will not be mirrored. Set to false if you are using a registry proxy and don't need to mirror images locally.

## Updating The Catalogue

To update the catalogue,run the script the same way you did the first time. As of OCP 4.6 you no longer have to increment the version of the catalog. The catalog will query for a newer version of the image used every 10 minutes (by default).

## Script Notes

Unfortunately just because an image is listed in the related images spec doesn't mean it exists or is even used by the operator. for example registry.redhat.io/openshift4/ose-promtail from the logging operator. I have put that image in the knownBadImages file to avoid attempting to mirror. Other images will be added as I find them.

## Convenience Container

The convenience container already has all dependencies needed to run the mirror-operator-catalogue.py script. Additionally, the container includes a convenience script that will export a registry v2 compressed tar archive to the host device running the container.

To launch the container:
```
chmod +x container-launch.sh
./container-launch.sh
```

To use the convenience script (from inside the container):
```
./bundle.sh '<< Pull Secret >>'
```
Note1: Make sure to include the single quotes in the above command
Note2: Pull secret can be obtained from https://cloud.redhat.com/openshift/install/aws/installer-provisioned

If you just want the Compliance Operator and associated resources:
```
./container/container-launch.sh ./bundle.sh '<< Pull Secret>>'
```

## Local Docker Registry

If you need a to create a local secured registry follow the instructions from the link below
<https://docs.openshift.com/container-platform/4.3/installing/install_config/installing-restricted-networks-preparations.html#installing-restricted-networks-preparations>
