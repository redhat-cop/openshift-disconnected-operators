#!/usr/bin/env python3
import sys
import re
import sqlite3
from packaging import version


def GetVersion(name):
    index = name.find(".")
    version = name[index+1:]

    while True:
        if version[0].isalpha():
            version = version[1:]
        else:
            break
    return version


def GetLatestVersion(operator_name, db_path):
  con = sqlite3.connect(db_path)
  cur = con.cursor()
  # Get default channel
  cmd = "select default_channel from package where name like '%" + operator_name + "%';"

  result = cur.execute(cmd).fetchall()
  if len(result) == 1:
    channel = result[0][0]
    
    # get version from default cahnnel
    cmd = "select head_operatorbundle_name from channel where package_name like '" + operator_name + "' and name like '" + channel + "'"
    result = cur.execute(cmd).fetchall()

    if len(result) == 1:
      version = GetVersion(result[0][0])
      return version


def GetVersionMatrix(version, matrix):
  for item in matrix:
    if GetVersion(item) == version:
      return matrix[item][1]


def SanitizeVersion(version):
  index = 0
  for i in range(len(version)):
    if version[i].isnumeric() or version[i] == '.':
      continue
    else:
      index = i
      break
  
  if index == 0:
    return version
  else:
    print(version[:index])
    return version[:index]


def VersionEval(version1, version2, symbol):
  v1 = version.parse(SanitizeVersion(version1))
  v2 = version.parse(SanitizeVersion(version2))
  if symbol == "<":
    return v1 < v2
  elif symbol == "<=":
    return v1 <= v2
  elif symbol == ">":
    return v1 > v2
  elif symbol == ">=":
    return v1 >= v2


def GetUpgradeMatrix(operator, start_version, latest_version, db_path):
  con = sqlite3.connect(db_path)
  cur = con.cursor()

  # Get Operator bundle name
  cmd = "select default_channel from package where name like '%" + operator + "%';"

  result = cur.execute(cmd).fetchall()
  if len(result) == 1:
    channel = result[0][0]

  cmd = "select head_operatorbundle_name from channel where package_name like '" + operator + "' and name like '" + channel + "'"
  result = cur.execute(cmd).fetchall()

  if len(result) == 1:
    bundle_name = result[0][0]
    index = bundle_name.find(".")
    bundle_name = bundle_name[:index]


  cmd = "select name,skiprange,version,replaces from operatorbundle where (name like '%" + \
      bundle_name + "%' or bundlepath like '%" + bundle_name + "%');"
  result = cur.execute(cmd)
  myDict = {}

  bundle = []
  for row in result:
    bundle_entry = []
    for column in row:
      bundle_entry.append(column)
    
    if VersionEval(bundle_entry[2], latest_version, "<="):
      bundle.append(bundle_entry)


  for entry in bundle:
    name = entry[0]
    myDict[name] = [entry[2], []]

  for entry in bundle:
    replaces = entry[3]
    if replaces and replaces in myDict and entry[2] not in myDict[replaces][1]:
      myDict[replaces][1].append(entry[2])

  # Check to see if start version has a bendle in the channel
  bundle_exists = False
  for entry in bundle:
    if entry[2] == start_version:
      bundle_exists = True
      break

  if not bundle_exists:
    myDict["unknown." + start_version] = [start_version, []]



  for entry in bundle:
    skiprange = entry[1]

    if skiprange:
      range = skiprange.split(' ')
      min = range[0]
      min_index = re.search(r"\d", min).start()
      min_oper = min[:min_index]
      min_version = min[min_index:]
      
      max = range[1]
      max_index = re.search(r"\d", max).start()
      max_oper = max[:max_index]
      max_version = max[max_index:]

      for k, v in myDict.items():
        if VersionEval(v[0], min_version, min_oper):
          if VersionEval(v[0], max_version, max_oper):
            if entry[2] not in v[1]:
              v[1].append(entry[2])

  return myDict


def GetHighestVersionFromMatrix(version_matrix):
  next_version = version_matrix[0]
  for app_version in version_matrix:
    if version.parse(next_version) < version.parse(app_version):
      next_version = app_version
  return next_version


def GetUpgradePaths(operator, start_version, latest_version, matrix, upgrade_paths, continue_upgrade_path):
  upgrade_path = continue_upgrade_path
  upgrade_path_complete = False
  current_version = start_version
  while upgrade_path_complete == False:
    current_version_matrix = GetVersionMatrix(current_version, matrix)

    if current_version_matrix:
      for v in range(1, len(current_version_matrix)):
        alternate_path_matrix = upgrade_path.copy()
        alternate_path_matrix.append(current_version_matrix[v])
        GetUpgradePaths(operator, current_version_matrix[v], latest_version, matrix, upgrade_paths, alternate_path_matrix)

      upgrade_path.append(current_version_matrix[0])
      if current_version_matrix[0] == latest_version:
        upgrade_path_complete = True
      else:
        current_version = current_version_matrix[0]
    
    else:
      print("There is no upgrade path for " + operator + " version " + start_version)
      sys.exit(1)

    # Probably won't need this but just in case there is a weird edge case
    if VersionEval(SanitizeVersion(current_version), latest_version, ">="):
        upgrade_path_complete = True

  upgrade_paths.append(upgrade_path)


def GetShortestUpgradePath(operator, start_version, db_path):

  latest_version = GetLatestVersion(operator, db_path)

  if latest_version != None:
    if start_version:
      matrix = GetUpgradeMatrix(operator, start_version, latest_version, db_path)
      upgrade_paths = []
      GetUpgradePaths(operator, start_version, latest_version, matrix, upgrade_paths, [])

      shortest_path = upgrade_paths[0]
      for path in upgrade_paths:
          if len(path) < len(shortest_path):
            shortest_path = path
    else:
      shortest_path = [latest_version]

  else:
    shortest_path = []
  
  return shortest_path