import os
import time
from tqdm import tqdm
import logging
import requests

from pageRequest import SplashRequest, LocalRequest
from pathUtils import is_path_exists_or_creatable
from extensions import mediaExtensions
import parseUtils

cwd = os.path.dirname(os.path.realpath(__file__))

# TODO: Depth limit https://stackoverflow.com/questions/27805952/scrapy-set-depth-limit-per-allowed-domains
# Possibly limit it in other ways https://stackoverflow.com/questions/30448532/scrapy-wait-for-a-specific-url-to-be-parsed-before-parsing-others
# TODO: Fix local file storage
# Stop using response.css, go back to passthrough and use use https://github.com/scrapy/parsel instead to extract with text=response.body
# Also possibly fix links in external files to always point to local directory instead of remote?

class ArchiverCrawler():
	links = []
	crawledCount = 0

	def __init__(self, config, **kw):
		super(ArchiverCrawler, self).__init__()
		# Setup logging
		logging.basicConfig()
		logging.getLogger().setLevel(logging.INFO)

		# Setup config
		self.config = config
		self.start_urls = config["startUrls"]
		self.allowed_domains = config["allowedDomains"]
		self.blocked_subdomains = config["blockedSubdomains"]
		self.discoveredLinks = len(self.start_urls)

		print("ArchiverCrawler instantiated\nstartUrls:")
		for url in self.start_urls:
			print("\t'"+url+"'")
		print("allowedDomains:")
		for domain in self.allowed_domains:
			print("\t'"+domain+"'")
		print("blockedSubdomains:")
		for bsd in self.blocked_subdomains:
			print("\t'"+bsd+"'")

		# Ensure we have base directory
		direc = os.path.join(cwd, self.config["folderName"])
		if (not os.path.isdir(direc)):
			os.mkdir(direc)

	def run(self):
		print("\n~~~ArchiverCrawler starting~~~\n")

		# Start progress bar
		self.pbar = tqdm(total=self.discoveredLinks, ascii=True)
		self.pbar.update(0)

		# Remove previous temp files
		num = parseUtils.removeTempFiles(os.path.join(cwd, self.config["folderName"]))
		if num>0:
			logging.info("Cleaned directory structure and removed %d temporary files from previous run", num)

		for url in self.start_urls:
			self.parse_page(SplashRequest(url, self.allowed_domains, self.config["splashStrictDomains"]))
		self.cleanup()
	
	def cleanup(self):
		self.pbar.close()
		logging.debug("Now cleaning folder structure...")
		direc = os.path.join(cwd, self.config["folderName"])
		num = parseUtils.removeEmptyFolders(direc)
		logging.info("Cleaned directory structure and removed %d empty folders", num)
		num = parseUtils.removeTempFiles(direc)
		logging.info("Cleaned directory structure and removed %d temporary files", num)


	# All the actual things
	def parse_page(self, response):
		self.crawledCount+=1
		self.pbar.n = self.crawledCount
		self.pbar.set_description(response.url)
		self.pbar.refresh()

		try:
			if response.status != 404:
				# Make sure we have something to parse
				if response.body is None:
					logging.warn("Response.body=None on "+response.url)
					return False
				
				# Extract subdirectory, page, path from url
				URLparts = parseUtils.extractURLParts(response.url)
				
				# Ensure the subdirs exist, since we're not in a root directory
				parseUtils.createSubdirs(os.path.join(cwd, self.config["folderName"]), URLparts["fullPath"])
				filepath = self.get_url_filepath(response.url)
				tempfilepath = filepath+".temp"

				if is_path_exists_or_creatable(filepath):
					if not os.path.exists(filepath): # Ensure we don't overwrite
						logging.debug("FILE WRITE: "+filepath)
						with open(tempfilepath, 'w', encoding="utf8", errors="ignore") as f:
								f.write(response.body)
						os.rename(tempfilepath, filepath) # Move finished file to final path
				else:
					logging.warn("FILE INVALID PATH: "+filepath)


				# Define links array
				resources = []
				tempResources = []

				mediaUrls = []
				mediaPaths = []

				nextLinks = []
				
				# Extract all media and links
				tempResources += response.css('*::attr(src)').getall()
				tempResources += response.css('*::attr(href)').getall()
				tempResources += response.css('*::attr(background)').getall()

				# Make things absolute and clean it
				for idx in range(0, len(tempResources)):
					tempResources[idx] = parseUtils.cleanLink(parseUtils.forceAbsoluteLink(response.url, tempResources[idx]))
				tempResources = [i for i in tempResources if i] # Filter "None" invalid links

				# Filter non germane links
				for res in tempResources:
					if self.url_allowed(res):
						resources.append(res)
					else:
						logging.debug("GotLink nOK: "+res)

				tempResources = resources # reuse for next filtering step
				resources = []

				# Filter by media file
				with requests.Session() as s:
					for resource in tempResources:
						isMediaFile = False
						for ext in mediaExtensions:
							if "."+ext in resource:
								isMediaFile = True

						if isMediaFile:
							resources.append(resource)
						else:
							if resource not in self.links:
								self.links.append(resource)
								try:
									# It's a link, so first get all redirects
									filepath = self.get_url_filepath(resource)
									if is_path_exists_or_creatable(filepath) and os.path.isfile(filepath): # We have a local copy already? Well then we don't need to do remote fetch and follow
										nextLinks.append(resource)
									else:
										with s.head(resource, allow_redirects=True, timeout=12) as followedLink: # Don't get the content, just redirect headers
											if followedLink.url not in self.links and self.url_allowed(followedLink.url):
												if followedLink.url != resource:
													self.links.append(followedLink.url)
												# It's a link, so add it to links collection and links to crawl
												nextLinks.append(followedLink.url)
											else:
												logging.debug("FollowLink nOK: "+resource+" | "+followedLink.url+", seen="+str(followedLink.url in self.links)+", allowed="+str(self.url_allowed(followedLink.url)))
								except Exception as e:
									logging.warn("Uhoh, something bad happened while following link '"+resource+"': "+str(e))
							
				del tempResources # Free mem

				# Extract the media links
				result = parseUtils.extractMedia(self.config, response.url, resources) # Remaining resources are all media files
				del resources # Free mem
				mediaUrls += result["urls"]
				mediaPaths += result["paths"]

				logging.debug("NextLinks:")
				logging.debug(nextLinks)
				logging.debug("MediaURLs:")
				logging.debug(mediaUrls)
				logging.debug("MediaPaths:")
				logging.debug(mediaPaths)

				# Filter media already downloaded
				with requests.Session() as s:
					for idx in range(0, len(mediaPaths)):
						path = mediaPaths[idx]
						url = mediaUrls[idx]

						try:
							if is_path_exists_or_creatable(path) and not os.path.isfile(path):
								logging.debug("MEDIA: downloading "+url)

								# Do the download
								self.download_media_session(url, path, s)
							else:
								logging.debug("MEDIA: Local copy of "+url+" being used")
						except Exception as e:
							logging.warn("Uhoh, something bad happened when trying to download '"+url+"': "+e)

				if len(nextLinks) > 0:
					logging.debug("\nDiscovered "+str(len(nextLinks))+" new link(s)")
					self.discoveredLinks+=len(nextLinks)
					self.pbar.total = self.discoveredLinks
					self.pbar.refresh()

					for link in nextLinks:
						# First we check if a local copy exists on the disk
						filepath = self.get_url_filepath(link)
						if is_path_exists_or_creatable(filepath) and os.path.isfile(filepath):
							with open(filepath, 'r', encoding="utf8", errors="ignore") as file:
								filedata = file.read()
							logging.debug("RESPONSE: Local file at "+filepath+" being used")
							res = self.parse_page(LocalRequest(link, filedata))
							if not res: #Error discovered
								logging.warn("NoneType in response discovered; was probably media (LocalCache)")
								self.download_media(link, filepath)
						else:
							# No local resource exists, so crawl it
							logging.debug("RESPONSE: Remote dir "+link+" being used")
							res = self.parse_page(SplashRequest(link, self.allowed_domains, self.config["splashStrictDomains"]))
							if not res:
								logging.warn("NoneType in response discovered; was probably media (SplashRequest)")
								self.download_media(link, self.get_url_filepath(link))

				else:
					logging.debug("NO LINKS FOUND IN: "+response.url)
		except Exception as e:
			logging.warn("Uhoh, something bad happened processing '"+response.url+"'. Error:\n"+str(e))

		return True

	def download_media(self, url, filepath, subdirs=True):
		url = url.strip().strip('"')
		filepath = filepath.strip().strip('"')
		tempfilepath = filepath+".temp"

		if subdirs:
			parseUtils.createSubdirs(os.path.join(cwd, self.config["folderName"]), parseUtils.extractURLParts(url)["fullPath"])

		if not os.path.exists(filepath):
			r = requests.get(url, stream=True)
			if r.status_code == 200:
				with open(tempfilepath, 'wb') as f:
					for chunk in r:
						f.write(chunk)
				os.rename(tempfilepath, filepath) # Move finished file to final path
				r.close()
			else:
				r.close()
				return False

		return True

	def download_media_session(self, url, filepath, session, subdirs=True):
		url = url.strip().strip('"')
		filepath = filepath.strip().strip('"')
		tempfilepath = filepath+".temp"

		if subdirs:
			parseUtils.createSubdirs(os.path.join(cwd, self.config["folderName"]), parseUtils.extractURLParts(url)["fullPath"])

		if not os.path.exists(filepath):
			r = session.get(url, stream=True)
			if r.status_code == 200:
				with open(tempfilepath, 'wb') as f:
					for chunk in r:
						f.write(chunk)
				os.rename(tempfilepath, filepath) # Move finished file to final path
				r.close()
			else:
				r.close()
				return False

		return True

	def get_url_filepath(self, link):
		parts = parseUtils.extractURLParts(link)
		filepath = os.path.join(cwd, self.config["folderName"], *parts["fullPath"], parts["page"])

		return filepath

	def url_allowed(self, link):
		for allowedDomain in self.allowed_domains:
			if allowedDomain in link:
				blocked = False
				for blockedSubdomain in self.blocked_subdomains:
					if blockedSubdomain in link:
						blocked = True
						break

				if not blocked and "@" not in link: # Filter emails
					return True

		return False
