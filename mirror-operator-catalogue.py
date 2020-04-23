import os, re, json, tarfile, shutil, yaml, subprocess
import urllib.request
from pathlib import Path


# Global Variables
offline_registry_catalog_repo_url=os.environ['offline_registry_catalog_repo_url']
offline_registry_olm_images_repo_url=os.environ['offline_registry_olm_images_repo_url']
catalog_version = os.environ['catalog_version']
operator_channel = "4.3"
script_root_dir = os.path.dirname(os.path.realpath(__file__))
content_root_dir = script_root_dir + "/content"
manifest_root_dir = content_root_dir + "/manifests"
publish_root_dir = script_root_dir + "/publish"
operator_related_image_list_file = content_root_dir + "/imagelist"
operator_known_bad_image_list_file = script_root_dir + "/known-bad-images"
offline_operator_list_file =  script_root_dir + "/offline-operator-list"
quay_rh_base_url="https://quay.io/cnr/api/v1/packages/"
redhat_operators_image_name = "redhat-operators"
redhat_operators_packages_url = "https://quay.io/cnr/api/v1/packages?namespace=redhat-operators"
redhat_operators_packages_filename = content_root_dir + "/packages.json"
image_content_source_policy_template_file = script_root_dir + "/image-content-source-template"
catalog_source_template_file = script_root_dir + "/catalog-source-template"
image_content_source_policy_output_file = publish_root_dir + "/olm-icsp.yaml"
catalog_source_output_file = publish_root_dir + "/rh-catalog-source.yaml"
mod_package_file_name = content_root_dir + "/mod_packages.json"
nl = "\n"



def main():
  # validate registry url has been set
  if offline_registry_catalog_repo_url == "" or offline_registry_olm_images_repo_url == "":
    print("Registry url should be set please see README.md for instructions")
    exit(1)
  # clean and recreate contents directory
  dirpath = Path(content_root_dir)
  publishpath = Path(publish_root_dir)
  if dirpath.exists() and dirpath.is_dir():
      shutil.rmtree(dirpath)
  if publishpath.exists() and publishpath.is_dir():
      shutil.rmtree(publishpath)
  os.mkdir(content_root_dir)
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
  #MirrorImagesToLocalRegistry()

  print("Creating Image Content Source Policy YAML...")
  CreateImageContentSourcePolicyFile()

  print("Catalogue creation and image mirroring complete")
  print("See Publish folder for the image content source policy and catalog source yaml files to apply to your cluster")




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

  mod_package_file_data="["
  with open(offline_operator_list_file) as f:
    first_item = True
    for op in (l.rstrip('\n') for l in f):
      op = op.strip()
      for c in data:
          if(c["name"].find(op) != -1):
              if first_item:
                mod_package_file_data+= json.dumps(c)
                first_item = False
              else:
                mod_package_file_data+= "," + json.dumps(c)
  mod_package_file_data+="]"
  mod_package_file_data_json = json.loads(mod_package_file_data)
  print(json.dumps(mod_package_file_data_json, indent=4, sort_keys=True))

  # Write new OLM package manifest to file
  with open(mod_package_file_name, "w") as mod_package_file:
      json.dump(mod_package_file_data_json, mod_package_file, indent=4, sort_keys=True)
  return mod_package_file_data_json

# Download Manifests for each white listed operator
def downloadAndProcessManifests(mod_package_file_data_json):
  for c in mod_package_file_data_json:
    quay_operator_reg_name = c["name"]
    quay_operator_version = c["default"]
    quay_operator_name = quay_operator_reg_name.partition("/")[2]
    downloadManifest(quay_operator_reg_name, quay_operator_version, quay_operator_name)

# Download individual operator manifest
def downloadManifest(quay_operator_reg_name, quay_operator_version, quay_operator_name):
  print("quay_operator_reg_name:" + quay_operator_reg_name)
  print("quay_operator_version:" + quay_operator_version)
  print("quay_operator_name:" + quay_operator_name)
  operator_base_url = quay_rh_base_url + quay_operator_reg_name
  operator_digest_url = operator_base_url + "/" + quay_operator_version
  print("Getting operator digest from: " + operator_digest_url)

  operator_digest_file = content_root_dir + "/" + quay_operator_name + ".json"
  urllib.request.urlretrieve(operator_digest_url, operator_digest_file)


  with open(operator_digest_file) as f:
    digest_data = json.load(f)
  operator_blob_url = operator_base_url + "/blobs/sha256/" + digest_data[0]["content"]["digest"]
  print("Downloading " + quay_operator_name + " opeartor archive from " + operator_blob_url + "..." )
  operator_archive_file = content_root_dir + "/" + quay_operator_name + ".tar.gz"
  urllib.request.urlretrieve(operator_blob_url, operator_archive_file)

  print("Extracting " + operator_archive_file)
  tf = tarfile.open(operator_archive_file)
  tf.extractall(manifest_root_dir)
  operatorCsvYaml = getOperatorCsvYaml(quay_operator_name)
  print("Getting list of related images from " + quay_operator_name + " operator")
  extractRelatedImagesToFile(operatorCsvYaml)


def getOperatorCsvYaml(operator_name):
  #csvData = None
  with os.scandir(manifest_root_dir) as directories:
    for directory in directories:
      if operator_name in directory.name and directory.is_dir:
        with os.scandir(directory.path) as manifest_items:
          for manifest_item in manifest_items:
            if "package" in manifest_item.name and manifest_item.is_file:
              with open(manifest_item.path, 'r') as packageYamlFile:
                  try:
                    packageYaml = yaml.safe_load(packageYamlFile)
                    default = packageYaml['defaultChannel']
                    for channel in packageYaml['channels']:
                      if channel['name'] == default:
                        currentChannel = channel['currentCSV']
                        csvFilePath = GetOperatorCsvPath(directory.path, currentChannel)

                        with open(csvFilePath, 'r') as yamlFile:
                          try:
                            csvYaml = yaml.safe_load(yamlFile)
                            return csvYaml
                          except yaml.YAMLError as exc:
                            print(exc)
                          break
                  except yaml.YAMLError as exc:
                    print(exc)
                  break
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
  image_url = offline_registry_catalog_repo_url + "/" + redhat_operators_image_name + ":" + catalog_version
  cmd_args = "podman build " + script_root_dir + " -t " + image_url
  subprocess.run(cmd_args, shell=True, check=True)

  print("Pushing catalog image to offline registry...")
  cmd_args = "podman push " + image_url
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
          cmd_args = "skopeo copy -a docker://" + image + " docker://" + destUrl
          subprocess.run(cmd_args, shell=True, check=True)
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


def CopyImageToDestinationRegistry(sourceImageUrl, destinationImageUrl):
    cmd_args = "skopeo copy -a docker://" + sourceImageUrl + " docker://" + destinationImageUrl
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
  return offline_registry_olm_images_repo_url + image_url[res:]

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
