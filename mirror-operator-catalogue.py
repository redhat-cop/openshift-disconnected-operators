#!/usr/bin/env python3
import os, glob, re, json, tarfile, shutil, yaml, subprocess
import urllib.request
from pathlib import Path

import tempfile
import argparse

parser = argparse.ArgumentParser(description='Mirror individual operators to an offline registry')
parser.add_argument("--authfile", default=None, help="Pull secret with credentials")
parser.add_argument("--registry-olm", required=True, help="Registry to copy the operator images")
parser.add_argument("--registry-catalog", required=True, help="Registry to copy the catalog image")
parser.add_argument("--catalog-version", default="1.0.0", help="Tag for the catalog image")
parser.add_argument("--operator-channel", default="4.3", help="Operator Channel. Default 4.3")
parser.add_argument("--operator-list", nargs="*", required=True, help="List of operators to mirror")
args = parser.parse_args()

# Global Variables
script_root_dir = os.path.dirname(os.path.realpath(__file__))
content_root_dir = tempfile.TemporaryDirectory()
manifest_root_dir = tempfile.TemporaryDirectory()
publish_root_dir = os.path.join(script_root_dir, 'publish')
operator_related_image_list_file = os.path.join(content_root_dir.name, "imagelist")
operator_known_bad_image_list_file = os.path.join(script_root_dir, "known-bad-images")
offline_operator_list_file = os.path.join(script_root_dir, "offline-operator-list")
quay_rh_base_url="https://quay.io/cnr/api/v1/packages/"
redhat_operators_image_name = "redhat-operators"
redhat_operators_packages_url = "https://quay.io/cnr/api/v1/packages?namespace=redhat-operators"
redhat_operators_packages_filename = os.path.join(content_root_dir.name, 'packages.json')
image_content_source_policy_template_file = script_root_dir + "/image-content-source-template"
catalog_source_template_file = script_root_dir + "/catalog-source-template"
image_content_source_policy_output_file = os.path.join(publish_root_dir, 'olm-icsp.yaml')
catalog_source_output_file = os.path.join(publish_root_dir, 'rh-catalog-source.yaml')
mod_package_file_name = os.path.join(content_root_dir.name, 'mod_packages.json')
nl = "\n"

def main():
  publishpath = Path(publish_root_dir)
  if publishpath.exists() and publishpath.is_dir():
    shutil.rmtree(publishpath)

  os.mkdir(publishpath)

  print("Starting Catalog Build and Mirror...")
  
  # Download OLM Package File with all operators
  print("Downloading OLM package for Redhat Operators...")
  downloadOlmPackageFile()

  print("Extracting white-listed operators...")
  mod_package_file_data_json = extractWhiteListedOperators()

  print("Downloading Manifests for white-listed operators...")
  downloadAndProcessManifests(mod_package_file_data_json)

  print("Creating custom catalogue image..")
  CreateCatalogImageAndPushToLocalRegistry()

  print("Mirroring related images to offline registry...")
  MirrorImagesToLocalRegistry()

  print("Creating Image Content Source Policy YAML...")
  CreateImageContentSourcePolicyFile()

  print("Catalogue creation and image mirroring complete")
  print("See Publish folder for the image content source policy and catalog source yaml files to apply to your cluster")

  # Cleanup temporary folders
  #shutil.rmtree(content_root_dir.name)
  #shutil.rmtree(manifest_root_dir.name)

# Get a List of repos to mirror
def GetRepoListToMirror(images):
  reg = r"^(.*\/){2}"
  sourceList = []
  mirrorList = {}
  for image in images:
    source = re.match(reg, image)
    if source == None:
      sourceRepo = image[:image.find("@")]
    else:
      sourceRepo = source.group()[:-1]
    sourceList.append(sourceRepo) if sourceRepo not in sourceList else sourceList
  
  for source in sourceList:
    mirrorList[source] = ChangeBaseRegistryUrl(source)

  return mirrorList

# Download Red Hat Channel OLM pcakage file
def downloadOlmPackageFile():
  urllib.request.urlretrieve(redhat_operators_packages_url, redhat_operators_packages_filename)

def extractWhiteListedOperators():
  # Open Red Hat channel OLM package file
  with open(redhat_operators_packages_filename) as f:
    data = json.load(f)

  mod_package_file_data = []
  for operator in args.operator_list:
     for c in data:
       if(c["name"].find(operator) != -1):
         mod_package_file_data.append(c)

  mod_package_file_data_json = json.dumps(mod_package_file_data)
  return json.loads(mod_package_file_data_json)

# Download Manifests for each white listed operator
def downloadAndProcessManifests(mod_package_file_data_json):
  for c in mod_package_file_data_json:
    print("downloadandprocess")
    quay_operator_reg_name = c["name"]
    quay_operator_version = c["default"]
    quay_operator_name = quay_operator_reg_name.split("/")[-1]
    downloadManifest(quay_operator_reg_name, quay_operator_version, quay_operator_name)

# Download individual operator manifest
def downloadManifest(quay_operator_reg_name, quay_operator_version, quay_operator_name):
  print("quay_operator_reg_name: " + quay_operator_reg_name)
  print("quay_operator_version: " + quay_operator_version)
  print("quay_operator_name: " + quay_operator_name)
  operator_base_url = "{}{}".format(quay_rh_base_url, quay_operator_reg_name)
  operator_digest_url = "{}/{}".format(operator_base_url, quay_operator_version)

  print("Getting operator digest from: " + operator_digest_url)

  operator_digest_file = os.path.join(content_root_dir.name, '{}.json'.format(quay_operator_name))
  urllib.request.urlretrieve(operator_digest_url, operator_digest_file)

  with open(operator_digest_file) as f:
    digest_data = json.load(f)

  operator_blob_url = operator_base_url + "/blobs/sha256/" + digest_data[0]["content"]["digest"]
  print("Downloading " + quay_operator_name + " opeartor archive from " + operator_blob_url + "..." )
  operator_archive_file = os.path.join(content_root_dir.name, '{}.tar.gz'.format(quay_operator_name))
  urllib.request.urlretrieve(operator_blob_url, operator_archive_file)

  print("Extracting " + operator_archive_file)
  tf = tarfile.open(operator_archive_file)
  tf.extractall(manifest_root_dir.name)
  operatorCsvYaml = getOperatorCsvYaml(quay_operator_name)
  print("Getting list of related images from " + quay_operator_name + " operator")
  extractRelatedImagesToFile(operatorCsvYaml)

def getOperatorCsvYaml(operator_name):
  try:  
    # Find manifest file
    operatorPackagePath = glob.glob(os.path.join(manifest_root_dir.name, operator_name + '*', '*package*' ))
    operatorManifestPath = os.path.dirname(operatorPackagePath[0])
    operatorPackageFilename = operatorPackagePath[0]

    with open(operatorPackageFilename, 'r') as packageYamlFile:
      packageYaml = yaml.safe_load(packageYamlFile)
      default = packageYaml['defaultChannel']
      for channel in packageYaml['channels']:
        if channel['name'] == default:
          currentChannel = channel['currentCSV']
          csvFilePath = GetOperatorCsvPath(operatorManifestPath, currentChannel)
          with open(csvFilePath, 'r') as yamlFile:
            csvYaml = yaml.safe_load(yamlFile)
            return csvYaml
  except (yaml.YAMLError, IOError) as exc:
    print(exc)
  return None

# Search within manifest folder for operator for correct CSV
def GetOperatorCsvPath(search_path, search_string):
  for root, directories, filenames in os.walk(search_path):
    for filename in filenames:
      if root != search_path:
        with open(os.path.join(root,filename)) as f:
          if search_string in f.read():
            return os.path.join(root,filename)

# Write related images from an operator CSV YAML to a file for later processing
def extractRelatedImagesToFile(operatorCsvYaml):
  with open(operator_related_image_list_file, 'a') as f:
    for entry in operatorCsvYaml['spec']['relatedImages']:
      if('image' in entry):
        f.write(entry['image'])
        f.write("\n")
      elif('value' in entry):
        f.write(entry['value'])
        f.write("\n")


# Create custom catalog image and push it to offline registry
def CreateCatalogImageAndPushToLocalRegistry():
  image_url = args.registry_catalog + "/" + redhat_operators_image_name + ":" + args.catalog_version
  cmd_args = "podman build " + script_root_dir + " -t " + image_url
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
    content = f.read()
  content = re.sub(r"@@(\w+?)@@", image_url, content)
  print(content)
  with open(catalog_source_output_file, "w") as f:
    f.write(content)


# Remove duplicate image entries from image list
def removeDuplicateImageEntries():
  orig_image_list_file = operator_related_image_list_file + "_orig"
  shutil.move(operator_related_image_list_file, orig_image_list_file)
  lines_seen = set() # holds lines already seen
  outfile = open(operator_related_image_list_file, "w")
  for line in open(orig_image_list_file, "r"):
      if line not in lines_seen: # not a duplicate
          outfile.write(line)
          lines_seen.add(line)
  outfile.close()


def MirrorImagesToLocalRegistry():
  removeDuplicateImageEntries()
  print("Copying image list to offline registry...")
  with open(operator_related_image_list_file, 'r') as f:
    images = [line.strip() for line in f]
    image_count = len(images)
    cur_image_count = 1
    for image in images:
      PrintBreakLine()
      print("Mirroring image " + str(cur_image_count) + " of " + str(image_count))
      if isBadImage(image) == False:
        destUrl = ChangeBaseRegistryUrl(image)
        try:
          print("Image: " + image)
          CopyImageToDestinationRegistry(image, destUrl, args.authfile)
        except subprocess.CalledProcessError as e:
          print("ERROR Copying image: " + image)
          print("TO")
          print(destUrl)
          if (e.output != None):
            print("exception:" + e.output + nl)
          print ("ERROR copying image!")
      else:
        print("Known bad image: " + image + nl + "ignoring...")
      
      cur_image_count = cur_image_count + 1
      PrintBreakLine()
  print("Finished mirroring related images.")


def CopyImageToDestinationRegistry(sourceImageUrl, destinationImageUrl, authfile=None):
    if args.authfile:
        cmd_args = "skopeo copy --authfile {} -a docker://{} docker://{}".format(authfile, sourceImageUrl,destinationImageUrl)
    else:
        cmd_args = "skopeo copy -a docker://{} docker://{}".format(sourceImageUrl, destinationImageUrl)

    subprocess.run(cmd_args, shell=True, check=True)

# Create Image Content Source Policy Yaml to apply to OCP cluster
def CreateImageContentSourcePolicyFile():
  with open(image_content_source_policy_template_file) as f:
    icpt = yaml.safe_load(f)
  with open(operator_related_image_list_file, 'r') as f:
    images = [line.strip() for line in f]
    repoList = GetRepoListToMirror(images)
  
  for key in repoList:
    icpt['spec']['repositoryDigestMirrors'].append({'mirrors': [repoList[key]], 'source': key})

  with open(image_content_source_policy_output_file, "w") as f:
    yaml.dump(icpt, f)


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
  print("----------------------------------------------" + nl)


if __name__ == "__main__":
    main()
