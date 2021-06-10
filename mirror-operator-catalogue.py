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
import upgradepath
import sqlite3


def is_number(string):
  try:
      float(string)
      return True
  except ValueError:
      return False

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
    "--ocp-version",
    default="4.6",
    help="OpenShift Y Stream. Only use X.Y version do not use Z. Default 4.6")
parser.add_argument(
    "--operator-channel",
    default="4.6",
    help="Operator Channel. Default 4.6")
parser.add_argument(
    "--operator-image-name",
    default="redhat-operators",
    help="Operator Image short Name. Default redhat-operators")
parser.add_argument(
    "--operator-catalog-image-url",
    default="registry.redhat.io/redhat/redhat-operator-index",
    help="Operator Index Image URL without version. Default registry.redhat.io/redhat/redhat-operator-index")
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument(
    "--operator-list",
    nargs="*",
    metavar="OPERATOR",
    help="List of operators to mirror, space delimeted")
group.add_argument(
    "--operator-file",
    metavar="FILE",
    help="Specify a file containing the operators to mirror")
group.add_argument(
    "--operator-yaml-file",
    metavar="FILE",
    help="Specify a YAML file containing operator list to mirror")
parser.add_argument(
    "--icsp-scope",
    default="namespace",
    help="Scope of registry mirrors in imagecontentsourcepolicy file. Allowed values: namespace, registry. Defaults to: namespace")
parser.add_argument(
    "--output",
    default="publish",
    help="Directory to create YAML files, must be relative to script path")
parser.add_argument(
    "--mirror-images",
    default="True",
    help="Boolean: Mirror related images. Default is True")
parser.add_argument(
    "--run-dir",
    default="",
    help="Run directory for script, must be an absolute path, only handy if running script in a container")
parser.add_argument(
    "--opm-path",
    default="",
    help="Full path of the opm binary if you want to use your own instead of the tool downloading it for you")
parser.add_argument(
    "--oc-cli-path",
    default="oc",
    help="Full path of oc cli")
parser.add_argument(
    "--custom-operator-catalog-image-url",
    default="",
    help="custom operator catalog image url in your registry")
parser.add_argument(
    "--custom-operator-catalog-name",
    default="custom-redhat-operators",
    help="custom operator catalog name")

args = parser.parse_args()

# Global Variables
if args.run_dir != "":
  script_root_dir = args.run_dir
else:
  script_root_dir = os.path.dirname(os.path.realpath(__file__))

publish_root_dir = os.path.join(script_root_dir, args.output)
run_root_dir = os.path.join(script_root_dir, "run")
mirror_images = args.mirror_images
operator_image_list = []
operator_data_list = {}
operator_known_bad_image_list_file = os.path.join(
    script_root_dir, "known-bad-images")
quay_rh_base_url = "https://quay.io/cnr/api/v1/packages/"
redhat_operators_image_name = args.operator_image_name
redhat_operators_packages_url = "https://quay.io/cnr/api/v1/packages?namespace=" + args.operator_image_name
image_content_source_policy_template_file = os.path.join(
    script_root_dir, "image-content-source-template")
catalog_source_template_file = os.path.join(
    script_root_dir, "catalog-source-template")
image_content_source_policy_output_file = os.path.join(
    publish_root_dir, 'olm-icsp.yaml')
catalog_source_output_file = os.path.join(
    publish_root_dir, 'rh-catalog-source.yaml')
mapping_file = os.path.join(
    publish_root_dir, 'mapping.txt')
image_manifest_file = os.path.join(
    publish_root_dir, 'image_manifest.txt')
mirror_summary_file = os.path.join(
    publish_root_dir, 'mirror_log.txt')
ocp_version = args.ocp_version
operator_channel = args.operator_channel
operator_index_version = ":v" + operator_channel if is_number(operator_channel) else ":" + operator_channel
redhat_operators_catalog_image_url = args.operator_catalog_image_url + operator_index_version
custom_redhat_operators_catalog_image_url = args.registry_catalog + "/custom-" + args.operator_catalog_image_url.split('/')[2] + ":" + args.catalog_version
oc_cli_path = args.oc_cli_path

if args.custom_operator_catalog_image_url:
  custom_redhat_operators_catalog_image_url = args.registry_catalog + "/" + args.custom_operator_catalog_image_url + operator_index_version


def main():
  run_temp = os.path.join(run_root_dir, "temp")
  publishpath = Path(publish_root_dir)
  run_path = Path(run_root_dir)
  temp_path = Path(run_temp)
  image_manifest_path = Path(image_manifest_file)
  mirror_summary_path = Path(mirror_summary_file)

  # Create publish, run and temp paths
  if publishpath.exists():
    shutil.rmtree(publishpath)
  os.mkdir(publishpath)

  if run_path.exists():
    shutil.rmtree(run_path)
  os.mkdir(run_path)
  
  if temp_path.exists():
    shutil.rmtree(temp_path)
  os.mkdir(temp_path)


  print("Starting Catalog Build and Mirror...")
  print("Getting opm CLI...")
  if args.opm_path != "":
    opm_cli_path = args.opm_path
  else:
    opm_cli_path = GetOpmCli(run_temp)

  print("Getting the list of operators for custom catalogue..")
  operators = GetWhiteListedOperators()

  # # NEED TO BE LOGGED IN TO REGISTRY.REDHAT.IO WITHOUT AUTHFILE ARGUMENT
  print("Pruning OLM catalogue...")
  PruneCatalog(opm_cli_path, operators, run_temp)
  
  print("Extracting custom catalogue database...")
  db_path = ExtractIndexDb()
  
  print("Create upgrade matrix for selected operators...")
  for operator in operators:
    operator.upgrade_path = upgradepath.GetShortestUpgradePath(operator.name, operator.start_version, db_path)  

  print("Getting list of images to be mirrored...")
  # ExtractOperatorBundles(operators, opm_cli_path, run_temp)
  # GetBundleImageListToMirror(db_path)
  GetImageListToMirror(operators, db_path)

  print("Writing summary data..")
  CreateSummaryFile(operators, mirror_summary_path)

  # GetImageListToMirror(operators, run_temp)

  images = getImages(operators)
  if mirror_images.lower() == "true":
    print("Mirroring related images to offline registry...")
    MirrorImagesToLocalRegistry(images)
  else:
    print("--mirror-images=false   Skipping image mirroring")


  print("Creating Image Content Source Policy YAML...")
  CreateImageContentSourcePolicyFile(images)

  print("Creating Mapping File...")
  CreateMappingFile(images)

  print("Creating Image manifest file...")
  CreateManifestFile(images)
  print("Creating Catalog Source YAML...")
  CreateCatalogSourceYaml(custom_redhat_operators_catalog_image_url)

  print("Catalogue creation and image mirroring complete")
  print("See Publish folder for the image content source policy and catalog source yaml files to apply to your cluster")

  cmd_args = "sudo rm -rf {}".format(run_root_dir)
  subprocess.run(cmd_args, shell=True, check=True)


def GetOcCli(run_temp):
  base_url = "https://mirror.openshift.com/pub/openshift-v4/clients/ocp/"
  archive_name = "openshift-client-linux.tar.gz"
  ocp_bin_channel = "fast"
  ocp_bin_release_url= base_url + ocp_bin_channel + "-" + ocp_version + "/" + archive_name
  print(ocp_bin_release_url)
  archive_file_path = os.path.join(run_temp, archive_name)

  print("Downloading oc Cli...")
  urllib.request.urlretrieve(ocp_bin_release_url, archive_file_path)

  print("Extracting oc Cli...")
  tf = tarfile.open(archive_file_path)
  tf.extractall(run_root_dir)

  return os.path.join(run_root_dir, "oc")


def GetOpmCli(run_temp):
  
  base_url = "https://mirror.openshift.com/pub/openshift-v4/clients/ocp/"
  archive_name = "opm-linux.tar.gz"
  channel = "fast"
  opm_bin_release_url = base_url + channel + "-" + ocp_version + "/" + archive_name
  print(opm_bin_release_url)
  archive_file_path = os.path.join(run_temp, archive_name)

  print("Downloading opm Cli...")
  urllib.request.urlretrieve(opm_bin_release_url, archive_file_path)

  print("Extracting oc Cli...")
  tf = tarfile.open(archive_file_path)
  tf.extractall(run_root_dir)

  return os.path.join(run_root_dir, "opm")


def GetWhiteListedOperators():
  try:
    operators = []
    operator_list = []

    if args.operator_file:
      with open(args.operator_file) as f:
        operators = f.read().splitlines()
        for operator in operators:
          operator_list.append(OperatorSpec(operator, ""))
    
    elif args.operator_yaml_file:
      with open(args.operator_yaml_file) as f:
        data = yaml.safe_load(f)
        for operator in data["operators"]:
          operator_list.append(OperatorSpec(GetFieldValue(operator, "name"), GetFieldValue(operator, "start_version")))

    elif args.operator_list:
      operators = args.operator_list
      for operator in operators:
        operator_list.append(OperatorSpec(operator, ""))

    return operator_list

  except () as exc:
    print("An exception occurred while reading operator list file")
    print(exc)
    sys.exit(1)



  CreateSummaryFile(operators, mirror_summary_path)
  CreateSummaryFile(operators, mirror_summary_path)

def CreateSummaryFile(operators, mirror_summary_path):
  with open(mirror_summary_path, "w") as f:
    for operator in operators:
      f.write(operator.name + '\n')
      f.write("Upgrade Path: ")
      upgrade_path = ""
      for version in operator.upgrade_path:
        upgrade_path += version + " -> "
      upgrade_path = upgrade_path[:-4]
      f.write(upgrade_path)
      f.write("\n")
      ("============================================================\n \n")
      for bundle in operator.operator_bundles:
        f.write("[Version: " + bundle.version + "]\n")
        f.write("Image List \n")
        f.write("---------------------------------------- \n")
        for image in bundle.related_images:
          f.write(image + "\n")
        f.write("---------------------------------------- \n \n")
      f.write("============================================================\n \n \n")

# Returns an empty string if field does not exist
def GetFieldValue(data, field):
  if field in data:
    return data[field]
  else:
    return ""

# Create a custom catalogue with selected operators
def PruneCatalog(opm_cli_path, operators, run_temp):
  
  operator_list = GetListOfCommaDelimitedOperatorList(operators)
  cmd = opm_cli_path + " index prune -f " + redhat_operators_catalog_image_url
  cmd += " -p " + operator_list # local-storage-operator,cluster-logging,kubevirt-hyperconverged "
  cmd += " -t " + custom_redhat_operators_catalog_image_url
  print("Running: " + cmd)
  os.chdir(run_temp)
  subprocess.run(cmd, shell=True, check=True)
  os.chdir(script_root_dir)

  print("Pushing custom catalogue " + custom_redhat_operators_catalog_image_url + "to registry...")
  cmd = "podman push " + custom_redhat_operators_catalog_image_url + " --tls-verify=false --authfile " + args.authfile
  subprocess.run(cmd, shell=True, check=True)
  print("Finished push")

def GetImageListToMirror(operators, db_path):
  con = sqlite3.connect(db_path)
  cur = con.cursor()
  for operator in operators:
    for version in operator.upgrade_path:

      # Get Operator bundle name
      cmd = "select default_channel from package where name like '%" + operator.name + "%';"

      result = cur.execute(cmd).fetchall()
      if len(result) == 1:
        channel = result[0][0]
    
      cmd = "select head_operatorbundle_name from channel where package_name like '" + operator.name + "' and name like '%" + channel + "%'"
      result = cur.execute(cmd).fetchall()

      if len(result) == 1:
        bundle_name = result[0][0]
        index = bundle_name.find(".")
        bundle_name = bundle_name[:index]

      # Get version bundle name
      cmd = "select name from operatorbundle where (name like '%" + bundle_name + "%' and version like '" + version + "');"

      result = cur.execute(cmd).fetchall()
      if len(result) >= 1:
        bundle_name = result[0][0]
      else:
        print("No bundle for for version " + version)
        continue

      bundle = OperatorBundle(bundle_name, version)
      
      # Get related images for the operator bundle
      cmd = "select image from related_image where operatorbundle_name like '%" + bundle_name + "%';"

      result = cur.execute(cmd).fetchall()
      if len(result) > 0:
        for image in result:
          bundle.related_images.append(image[0])
      
      # Get bundle images for operator bundle
      cmd = "select bundlepath from operatorbundle where (name like '%" +  operator.name + "%' or bundlepath like '%" +  operator.name + "%') and version='" + version + "';"

      result = cur.execute(cmd).fetchall()
      if len(result) > 0:
        for image in result:
          bundle.related_images.append(image[0])

      operator.operator_bundles.append(bundle)


## OLD WAY
# def ExtractOperatorBundles(operators, opm_cli_path, run_temp):

#   operator_list = ','.join(operators)
#   # for operator in operators:
#   os.chdir(run_temp)
#   cmd = opm_cli_path + " index export --index=" + custom_redhat_operators_catalog_image_url + " --package=" + operator_list + " -c='podman' --skip-tls -f " + run_temp
#   subprocess.run(cmd, shell=True, check=True)
#   os.chdir(script_root_dir)


## OLD WAY
# def GetImageListToMirror(operators, run_temp):

#   for operator in operators:
#     operator_dir = os.path.join(run_temp, operator)
#     csv_yaml_list = GetOperatorCsvYaml(operator_dir, operator)
#     for csv_yaml in csv_yaml_list:
#       ExtractRelatedImages(csv_yaml)


# def GetOperatorCsvYaml(operator_dir, operator):
#   try:
#     # Normally we would only have to deal with one channel, but for now the stable channel might differ from
#     # default channel and we want both versions to be accessible.
#     csv_yaml_list = []
#     # Find manifest file
#     operatorPackagePath = glob.glob(
#         os.path.join(
#             operator_dir,
#             '*package*'))
#     operatorManifestPath = os.path.dirname(operatorPackagePath[0])
#     operatorPackageFilename = operatorPackagePath[0]

#     with open(operatorPackageFilename, 'r') as packageYamlFile:
#       packageYaml = yaml.safe_load(packageYamlFile)
#       version = next((chan['name'] for chan in packageYaml['channels'] if chan['name'] == args.operator_channel), packageYaml['defaultChannel'])
#       default_channel = ""
#       for channel in packageYaml['channels']:
#         if channel['name'] == version:
#           default_channel = channel['currentCSV']
#           csvFilePath = GetOperatorCsvPath(
#               operatorManifestPath, default_channel)
#           with open(csvFilePath, 'r') as yamlFile:
#             csv_yaml = yaml.safe_load(yamlFile)
#             operator_data_list[operator] = csv_yaml['spec']['version']
#             csv_yaml_list.append(csv_yaml)
        
#     return csv_yaml_list
#   except (yaml.YAMLError, IOError) as exc:
#     print(exc)
#   return None


# # Search within manifest folder for correct CSV
# def GetOperatorCsvPath(search_path, search_string):
#   yamlFiles = Path(search_path).glob("*/**/*.yaml")
#   for fileName in yamlFiles:
#     with open(fileName) as f:
#       if search_string in f.read():
#         return fileName


# Write related images from an operator CSV YAML to a file for later processing
# def ExtractRelatedImages(operatorCsvYaml):
#   for entry in operatorCsvYaml['spec']:
#     if('relatedImages'in entry):
#       for entry in operatorCsvYaml['spec']['relatedImages']:
#         if('image' in entry):
#           setImages(entry['image'])
#         elif('value' in entry):
#           setImages(entry['value'])

  # # Some operators don't have every image they need in the related images field
  # # We have to query the deployments spec to get the missing image(s)
  # for entry in operatorCsvYaml['spec']['install']['spec']['deployments']:
  #   for container in entry['spec']['template']['spec']['containers']:
  #     if('image' in container):
  #       setImages(container['image'])


def ExtractIndexDb():
  cmd = oc_cli_path + " image extract " + custom_redhat_operators_catalog_image_url
  cmd += " -a " + args.authfile + " --path /database/index.db:" + run_root_dir + " --confirm --insecure"
  subprocess.run(cmd, shell=True, check=True)

  return os.path.join(run_root_dir, "index.db")

# def GetBundleImageListToMirror(db_path):
  
#   for operator in operator_data_list:
#     cmd = "sqlite3 -line " + db_path + " \"select bundlepath from operatorbundle where (name like '%" +  operator + "%' or bundlepath like '%" +  operator + "%') and version='" + operator_data_list[operator] + "';\""  
#     print(cmd)
#     proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
#     output = proc.communicate()

#     for line in output[0].splitlines():
#       imageUrl = str(line).strip()
#       if imageUrl and len(imageUrl) > 5:
#         imageUrl = imageUrl.split("=")[1].strip()[:-1]
#         setImages(imageUrl)


# Add image to a list of images to download
# def setImages(image):
#   if image not in operator_image_list:
#     operator_image_list.append(image)

# Get a non duplicate list of images to download
def getImages(operators):
  image_list = []
  for operator in operators:
    for bundle in operator.operator_bundles:
      for image in bundle.related_images:
        if image not in image_list:
          image_list.append(image)
  return image_list


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
      max_retries = 5
      retries = 0
      success = False
      while retries < max_retries and success == False:
        if (retries > 0 ):
          print("RETRY ATTEMPT: " +  str(retries))
        try:
          print("Image: " + image)
          CopyImageToDestinationRegistry(image, destUrl, args.authfile)
          success = True
        except subprocess.CalledProcessError as e:
          print("ERROR Copying image: " + image)
          print("TO")
          print(destUrl)
          if (e.output is not None):
            print("exception:" + e.output)
          print("ERROR copying image!")
          retries+=1
    else:
      print("Known bad image: {}\n{}".format(image, "ignoring..."))

    cur_image_count = cur_image_count + 1
    PrintBreakLine()
  print("Finished mirroring related images.")


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


# Get a List of repos to mirror
def GetRepoListToMirror(images):
  reg = r"^(.*\/){2}"
  if args.icsp_scope == "registry":
    reg = r"^(.*?\/){1}"
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

def CreateMappingFile(images):
  repoList = GetSourceToMirrorMapping(images)
  with open(mapping_file, "w") as f:
    for key in repoList:
      f.write(key + "=" + repoList[key])
      f.write('\n')

def CreateManifestFile(images):
  with open(image_manifest_file, "w") as f:
    for image in images:
      f.write(image)
      f.write("\n")


def isBadImage(image):
  with open(operator_known_bad_image_list_file, 'r') as f:
    for bad_image in (l.rstrip('\n') for l in f):
      if bad_image == image:
        return True
  return False

def ChangeBaseRegistryUrl(image_url):
  res = image_url.find("/")
  if res != -1:
    return args.registry_olm + image_url[res:]
  return args.registry_olm


def CopyImageToDestinationRegistry(
        sourceImageUrl, destinationImageUrl, authfile=None):
  if args.authfile:
    cmd_args = "skopeo copy --dest-tls-verify=false --authfile {} -a docker://{} docker://{}".format(
        authfile, sourceImageUrl, destinationImageUrl)
  else:
    cmd_args = "skopeo copy --dest-tls-verify=false -a docker://{} docker://{}".format(
        sourceImageUrl, destinationImageUrl)

  subprocess.run(cmd_args, shell=True, check=True)

# Get a Mapping of source to mirror images
def GetSourceToMirrorMapping(images):
  reg = r"^(.*@){1}"
  mapping = {}
  for image in images:
    source = re.match(reg, image)
    if source is None:
      sourceRepo = image
    else:
      sourceRepo = source.group()[:-1]

    mapping[image] = ChangeBaseRegistryUrl(sourceRepo)

  return mapping


def CreateCatalogSourceYaml(image_url):
  with open(catalog_source_template_file, 'r') as f:
    templateFile = Template(f.read())
  content = templateFile.render(CatalogSource=image_url,CatalogName=args.custom_operator_catalog_name)
  with open(catalog_source_output_file, "w") as f:
    f.write(content)


def GetListOfCommaDelimitedOperatorList(operators):
    operator_list = ""
    for item in operators:
      operator_list += item.name + ","

    operator_list = operator_list[:-1]
    return operator_list

def PrintBreakLine():
  print("----------------------------------------------")

class OperatorSpec:
  def __init__(self, name, start_version):
      self.name = name
      self.start_version = start_version
      self.upgrade_path = ""
      self.operator_bundles = []

class OperatorBundle:
  def __init__(self, name, version):
      self.name = name
      self.version = version
      self.related_images = []



if __name__ == "__main__":
  main()
