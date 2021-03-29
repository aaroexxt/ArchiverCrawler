import logging
from urllib.parse import urlparse, urljoin
import os

cwd = os.path.dirname(os.path.realpath(__file__))

def extractURLParts(url):
	parsed = urlparse(url.strip())
	if len(parsed.path) == 0 or parsed.path == "/" or parsed.path == None:
		return({
			"subdir": parsed.netloc,
			"page": "", #default to base page
			"path": [],
			"fullPath": [parsed.netloc]
		})
	else:
		path = [i for i in parsed.path.split("/") if i]

		if "." in path[-1]: # Is there a file extension?
			page = path[-1] # page is top dir
			path = path[:-1] # page is everything else
		else:
			page = ""

		return({
				"subdir": parsed.netloc,
				"page": page,
				"path": path,
				"fullPath": [j.split(":")[0] for j in [i for i in ([parsed.netloc]+path) if i]]
			})


def cleanLink(url):
	parsed = urlparse(url.strip())
	if parsed.scheme is None or parsed.scheme == "":
		if parsed.path is not None and parsed.path != "":
			urlClean = "http://"+parsed.path
		else:
			return None
	else:
		urlClean = urljoin(parsed.scheme+"://"+parsed.netloc, parsed.path)
	return urlClean

def createSubdirs(base, subdirs):
	if len(subdirs) != 0:
		for idx in range(0, len(subdirs)):
			subdirs[idx] = subdirs[idx].split(":")[0]

		for idx in range(0, len(subdirs)):
			direc = os.path.join(base, *subdirs[:(idx+1)])
			if os.path.exists(direc) and not os.path.isdir(direc): # Uhoh it's a file
				logging.debug("DELFILE FOR SUBDIR: "+direc)
				os.remove(direc)

			if not os.path.isdir(direc):
				logging.debug("SUBDIR CREATE: "+direc)
				os.mkdir(direc)


# Takes a list of links and returns urls and filepaths for them
def extractMedia(config, baseURL, mediaURLS):
	extractedURLS = []
	extractedPaths = []

	URLparts = extractURLParts(baseURL)
	for mediaURL in mediaURLS:
		parts = extractURLParts(mediaURL)
		if parts["subdir"] == "":
			mediaURL = urljoin(baseURL,mediaURL)
			# Relative path, so refer to inside URLparts directory
			createSubdirs(os.path.join(cwd, config["folderName"]), URLparts["fullPath"]+parts["fullPath"])
			mediaPath = os.path.join(cwd, config["folderName"], *(URLparts["fullPath"]+parts["fullPath"]), parts["page"])
		else:
			# Absolute path
			createSubdirs(os.path.join(cwd, config["folderName"]), parts["fullPath"])
			mediaPath = os.path.join(cwd, config["folderName"], *parts["fullPath"], parts["page"])

		extractedURLS.append(mediaURL)
		extractedPaths.append(mediaPath)

	return({
		"urls": extractedURLS,
		"paths": extractedPaths
	})

def forceAbsoluteLink(baseURL, linkURL):
	baseParts = extractURLParts(baseURL)
	parts = extractURLParts(linkURL)

	baseLoc = "http://"+"/".join(baseParts["fullPath"])
	if baseLoc[-1] != "/":
		baseLoc += "/"

	print(baseLoc)
	if parts["subdir"] == "":
		return urljoin(baseLoc,linkURL)
	else:
		# Absolute path
		return linkURL

def removeEmptyFolders(path):
	count = 0
	if not os.path.isdir(path):
		return 0

	# remove empty subfolders
	files = os.listdir(path)
	if len(files):
		for f in files:
			fullpath = os.path.join(path, f)
			if os.path.isdir(fullpath):
				count += removeEmptyFolders(fullpath)

	# if folder empty, delete it
	files = os.listdir(path)
	if len(files) == 0:
		logging.debug("Removing empty folder: "+path)
		os.rmdir(path)
		count+=1

	return count