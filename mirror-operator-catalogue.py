#!/usr/bin/env python3
import os
import sys
import glob
import re
import json
import tarfile
import shutil
import yaml
import subprocess
import tempfile
import argparse
import urllib.request
from jinja2 import Template
from pathlib import Path

parser = argparse.ArgumentParser(
    description='Mirror individual operators to an offline registry')
parser.add_argument(
    "--authfile",
    default=None,
    help="Pull secret with credentials")
parser.add_argument(
    "--registry-olm",
    metavar="REGISTRY",
    required=True,
    help="Registry to copy the operator images")
parser.add_argument(
    "--registry-catalog",
    metavar="REGISTRY",
    required=True,
    help="Registry to copy the catalog image")
parser.add_argument(
    "--catalog-version",
    default="1.0.0",
    help="Tag for the catalog image")
parser.add_argument(
    "--operator-channel",
    default="4.3",
    help="Operator Channel. Default 4.3")
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument(
    "--operator-list",
    nargs="*",
    metavar="OPERATOR",
    help="List of operators to mirror")
group.add_argument(
    "--operator-file",
    metavar="FILE",
    help="Specify a file containing the operators to mirror")
parser.add_argument(
    "--output",
    default="publish",
    help="Directory to create YAML files")
args = parser.parse_args()

# Global Variables
script_root_dir = os.path.dirname(os.path.realpath(__file__))
content_root_dir = tempfile.mkdtemp()
manifest_root_dir = tempfile.mkdtemp()
publish_root_dir = args.output
operator_image_list = []
operator_known_bad_image_list_file = os.path.join(
    script_root_dir, "known-bad-images")
quay_rh_base_url = "https://quay.io/cnr/api/v1/packages/"
redhat_operators_image_name = "redhat-operators"
redhat_operators_packages_url = "https://quay.io/cnr/api/v1/packages?namespace=redhat-operators"
image_content_source_policy_template_file = os.path.join(
    script_root_dir, "image-content-source-template")
catalog_source_template_file = os.path.join(
    script_root_dir, "catalog-source-template")
image_content_source_policy_output_file = os.path.join(
    publish_root_dir, 'olm-icsp.yaml')
catalog_source_output_file = os.path.join(
    publish_root_dir, 'rh-catalog-source.yaml')


def main():
  publishpath = Path(publish_root_dir)

  if publish_root_dir is not "publish" and not (
          publishpath.exists() and publishpath.is_dir()):
    print("The output folder doesn't exist. Please specify a valid directory")
    sys.exit(1)
  elif publish_root_dir is "publish" and not (publishpath.exists() and publishpath.is_dir()):
    os.mkdir(publishpath)

  print("Starting Catalog Build and Mirror...")

  # Download OLM Package File with all operators
  print("Downloading OLM package for Redhat Operators...")
  redhat_operators_packages = downloadOlmPackageFile(
      redhat_operators_packages_url)

  print("Extracting white-listed operators...")
  mod_package_file_data_json = extractWhiteListedOperators(
      redhat_operators_packages)

  print("Downloading Manifests for white-listed operators...")
  downloadAndProcessManifests(mod_package_file_data_json)

  print("Creating custom catalogue image..")
  CreateCatalogImageAndPushToLocalRegistry()

  print("Mirroring related images to offline registry...")
  images = getImages()
  MirrorImagesToLocalRegistry(images)

  print("Creating Image Content Source Policy YAML...")
  CreateImageContentSourcePolicyFile(images)

  print("Catalogue creation and image mirroring complete")
  print("See Publish folder for the image content source policy and catalog source yaml files to apply to your cluster")

  # Cleanup temporary directories
  shutil.rmtree(content_root_dir)
  shutil.rmtree(manifest_root_dir)

# Get a List of repos to mirror
def GetRepoListToMirror(images):
  reg = r"^(.*\/){2}"
  sourceList = []
  mirrorList = {}
  for image in images:
    source = re.match(reg, image)
    if source is None:
      sourceRepo = image[:image.find("@")]
    else:
      sourceRepo = source.group()[:-1]
    sourceList.append(
        sourceRepo) if sourceRepo not in sourceList else sourceList

  for source in sourceList:
    mirrorList[source] = ChangeBaseRegistryUrl(source)

  return mirrorList

# Download Red Hat Channel OLM pcakage file
def downloadOlmPackageFile(redhat_operators_packages_url):
  operators_packages = urllib.request.urlopen(redhat_operators_packages_url)
  return json.load(operators_packages)


def extractWhiteListedOperators(redhat_operators_packages):
  try:
    data = redhat_operators_packages

    operators = []
    if args.operator_file:
      with open(args.operator_file) as f:
        operators = f.read().splitlines()
    elif args.operator_list:
      operators = args.operator_list

    mod_package_file_data = []
    for operator in operators:
      for c in data:
        if(c["name"].find(operator) != -1):
          mod_package_file_data.append(c)

    mod_package_file_data_json = json.dumps(mod_package_file_data)
    return json.loads(mod_package_file_data_json)

  except (yaml.YAMLError, IOError) as exc:
    print(exc)
  return None

# Download Manifests for each white listed operator
def downloadAndProcessManifests(mod_package_file_data_json):
  for c in mod_package_file_data_json:
    quay_operator_reg_name = c["name"]
    quay_operator_version = c["default"]
    quay_operator_name = quay_operator_reg_name.split("/")[-1]
    downloadManifest(
        quay_operator_reg_name,
        quay_operator_version,
        quay_operator_name)

# Download individual operator manifest
def downloadManifest(quay_operator_reg_name,
                     quay_operator_version, quay_operator_name):
  print("quay_operator_reg_name: " + quay_operator_reg_name)
  print("quay_operator_version: " + quay_operator_version)
  print("quay_operator_name: " + quay_operator_name)
  operator_base_url = "{}{}".format(quay_rh_base_url, quay_operator_reg_name)
  operator_digest_url = "{}/{}".format(operator_base_url,
                                       quay_operator_version)

  print("Getting operator digest from: " + operator_digest_url)

  operator_digest = urllib.request.urlopen(operator_digest_url)
  digest_data = json.load(operator_digest)
  operator_blob_url = operator_base_url + \
      "/blobs/sha256/" + digest_data[0]["content"]["digest"]
  print(
      "Downloading " +
      quay_operator_name +
      " opeartor archive from " +
      operator_blob_url +
      "...")
  operator_archive_file = os.path.join(
      content_root_dir,
      '{}.tar.gz'.format(quay_operator_name))
  urllib.request.urlretrieve(operator_blob_url, operator_archive_file)

  print("Extracting " + operator_archive_file)
  tf = tarfile.open(operator_archive_file)
  tf.extractall(manifest_root_dir)
  operatorCsvYaml = getOperatorCsvYaml(quay_operator_name)
  print(
      "Getting list of related images from " +
      quay_operator_name +
      " operator")
  extractRelatedImagesToFile(operatorCsvYaml)


def getOperatorCsvYaml(operator_name):
  try:
    # Find manifest file
    operatorPackagePath = glob.glob(
        os.path.join(
            manifest_root_dir,
            operator_name + '*',
            '*package*'))
    operatorManifestPath = os.path.dirname(operatorPackagePath[0])
    operatorPackageFilename = operatorPackagePath[0]

    with open(operatorPackageFilename, 'r') as packageYamlFile:
      packageYaml = yaml.safe_load(packageYamlFile)
      default = packageYaml['defaultChannel']
      for channel in packageYaml['channels']:
        if channel['name'] == default:
          currentChannel = channel['currentCSV']
          csvFilePath = GetOperatorCsvPath(
              operatorManifestPath, currentChannel)
          with open(csvFilePath, 'r') as yamlFile:
            csvYaml = yaml.safe_load(yamlFile)
            return csvYaml
  except (yaml.YAMLError, IOError) as exc:
    print(exc)
  return None


# Search within manifest folder for correct CSV
def GetOperatorCsvPath(search_path, search_string):
  yamlFiles = Path(search_path).glob("*/**/*.yaml")
  for fileName in yamlFiles:
    with open(fileName) as f:
      if search_string in f.read():
        return fileName


# Get a non duplicate list of images to download
def getImages():
  return operator_image_list

# Add image to a list of images to download
def setImages(image):
  if image not in operator_image_list:
    operator_image_list.append(image)

# Write related images from an operator CSV YAML to a file for later processing
def extractRelatedImagesToFile(operatorCsvYaml):
  for entry in operatorCsvYaml['spec']['relatedImages']:
    if('image' in entry):
      setImages(entry['image'])
    elif('value' in entry):
      setImages(entry['value'])

# Create custom catalog image and push it to offline registry
def CreateCatalogImageAndPushToLocalRegistry():
  image_url = args.registry_catalog + "/" + \
      redhat_operators_image_name + ":" + args.catalog_version

  with open(os.path.join(script_root_dir, 'Dockerfile.template')) as f:
    templateFile = Template(f.read())

  content = templateFile.render(manifestPath=os.path.basename(manifest_root_dir))
  
  dockerFile = os.path.join(content_root_dir, 'Dockerfile')

  with open(dockerFile, "w") as dockerfile:
    dockerfile.write(content)

  cmd_args = "podman build --format docker -f {} -t {}".format(content_root_dir, image_url)
  subprocess.run(cmd_args, shell=True, check=True)

  print("Pushing catalog image to offline registry...")
  if args.authfile:
    cmd_args = "podman push --authfile {} {}".format(args.authfile, image_url)
  else:
    cmd_args = "podman push {} ".format(image_url)

  subprocess.run(cmd_args, shell=True, check=True)
  CreateCatalogSourceYaml(image_url)


def CreateCatalogSourceYaml(image_url):
  with open(catalog_source_template_file, 'r') as f:
    templateFile = Template(f.read())
  content = templateFile.render(CatalogSource=image_url)
  with open(catalog_source_output_file, "w") as f:
    f.write(content)


def MirrorImagesToLocalRegistry(images):
  print("Copying image list to offline registry...")
  image_count = len(images)
  cur_image_count = 1
  for image in images:
    PrintBreakLine()
    print(
        "Mirroring image " +
        str(cur_image_count) +
        " of " +
        str(image_count))
    if isBadImage(image) == False:
      destUrl = ChangeBaseRegistryUrl(image)
      try:
        print("Image: " + image)
        CopyImageToDestinationRegistry(image, destUrl, args.authfile)
      except subprocess.CalledProcessError as e:
        print("ERROR Copying image: " + image)
        print("TO")
        print(destUrl)
        if (e.output is not None):
          print("exception:" + e.output + nl)
        print("ERROR copying image!")
    else:
      print("Known bad image: {}\n{}".format(image, "ignoring..."))

    cur_image_count = cur_image_count + 1
    PrintBreakLine()
  print("Finished mirroring related images.")


def CopyImageToDestinationRegistry(
        sourceImageUrl, destinationImageUrl, authfile=None):
  if args.authfile:
    cmd_args = "skopeo copy --authfile {} -a docker://{} docker://{}".format(
        authfile, sourceImageUrl, destinationImageUrl)
  else:
    cmd_args = "skopeo copy -a docker://{} docker://{}".format(
        sourceImageUrl, destinationImageUrl)

  subprocess.run(cmd_args, shell=True, check=True)

# Create Image Content Source Policy Yaml to apply to OCP cluster
def CreateImageContentSourcePolicyFile(images):
  with open(image_content_source_policy_template_file) as f:
    icpt = yaml.safe_load(f)

  repoList = GetRepoListToMirror(images)

  for key in repoList:
    icpt['spec']['repositoryDigestMirrors'].append(
        {'mirrors': [repoList[key]], 'source': key})

  with open(image_content_source_policy_output_file, "w") as f:
    yaml.dump(icpt, f, default_flow_style=False)


def ChangeBaseRegistryUrl(image_url):
  res = image_url.find("/")
  return args.registry_olm + image_url[res:]


def isBadImage(image):
  with open(operator_known_bad_image_list_file, 'r') as f:
    for bad_image in (l.rstrip('\n') for l in f):
      if bad_image == image:
        return True
  return False


def PrintBreakLine():
  print("----------------------------------------------")


if __name__ == "__main__":
  main()
