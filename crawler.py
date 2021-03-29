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
		self.discoveredLinks = len(self.start_urls)

		print("ArchiverCrawler instantiated\nstartUrls:")
		for url in self.start_urls:
			print("\t'"+url+"'")
		print("allowedDomains:")
		for domain in self.allowed_domains:
			print("\t'"+domain+"'")

		# Ensure we have base directory
		direc = os.path.join(cwd, self.config["folderName"])
		if (not os.path.isdir(direc)):
			os.mkdir(direc)

	def run(self):
		print("\n~~~ArchiverCrawler starting~~~\n")

		# Start progress bar
		self.pbar = tqdm(total=self.discoveredLinks, ascii=True)
		self.pbar.update(0)

		for url in self.start_urls:
			self.parse_page(SplashRequest(url))
		self.cleanup()
	
	def cleanup(self):
		self.pbar.close()
		logging.debug("Now cleaning folder structure...")
		direc = os.path.join(cwd, self.config["folderName"])
		num = parseUtils.removeEmptyFolders(direc)
		logging.info("Cleaned directory structure and removed %d empty folders", num)


	# All the actual things
	def parse_page(self, response):
		self.crawledCount+=1
		self.pbar.n = self.crawledCount
		self.pbar.set_description(response.url)
		self.pbar.refresh()

		if response.status != 404:
			# Extract subdirectory, page, path from url
			URLparts = parseUtils.extractURLParts(response.url)
			
			# Ensure the subdirs exist, since we're not in a root directory
			parseUtils.createSubdirs(os.path.join(cwd, self.config["folderName"]), URLparts["fullPath"])
			filepath = os.path.join(cwd, self.config["folderName"], *URLparts["fullPath"], URLparts["page"])
			if "." not in URLparts["page"]:
				filepath+=".unknown"

			if is_path_exists_or_creatable(filepath):
				if response.body is None:
					logging.warn("Response.body=None on "+response.url)
					return False
				else:
					if not os.path.isfile(filepath): # Ensure we don't overwrite
						logging.debug("FILE WRITE: "+filepath)
						with open(filepath, 'w', encoding="utf8") as f:
								f.write(response.body)
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
				for allowedDomain in self.allowed_domains:
					if allowedDomain in res:
						resources.append(res)
						break

			tempResources = resources # reuse for next filtering step
			resources = []

			# Filter by media file
			for resource in tempResources:
				isMediaFile = False
				for ext in mediaExtensions:
					if "."+ext in resource:
						isMediaFile = True

				if isMediaFile:
					resources.append(resource)
				elif (resource not in self.links): # It's a link, so add it to links collection and links to crawl
					self.links.append(resource)
					nextLinks.append(resource)
			del tempResources # Free mem

			# Extract the media links
			result = parseUtils.extractMedia(self.config, response.url, resources) # Remaining resources are all media files
			del resources # Free mem
			mediaUrls += result["urls"]
			mediaPaths += result["paths"]

			print(nextLinks, mediaUrls, mediaPaths)

			# Filter media already downloaded
			for idx in range(0, len(mediaPaths)):
				path = mediaPaths[idx]
				url = mediaUrls[idx]

				if is_path_exists_or_creatable(path) and not os.path.isfile(path):
					if "." not in parseUtils.extractURLParts(url)["page"]:
						mediaPaths[idx]+=".unknown"
					logging.debug("MEDIA: downloading "+url)

					# Do the download
					self.download_media(url, path)
				else:
					logging.debug("MEDIA: Local copy of "+url+" being used")

		if len(nextLinks) > 0:
			logging.debug("\nDiscovered "+str(len(nextLinks))+" new link(s)")
			self.discoveredLinks+=len(nextLinks)
			self.pbar.total = self.discoveredLinks
			self.pbar.refresh()

			for link in nextLinks:
				# First we check if a local copy exists on the disk
				filepath = self.get_url_filepath(link)
				if is_path_exists_or_creatable(filepath) and os.path.isfile(filepath):
					with open(filepath, 'r') as file:
						filedata = file.read()
					logging.debug("RESPONSE: Local file at "+filepath+" being used")
					res = self.parse_page(LocalRequest(link, filedata))
					if not res: #Error discovered
						logging.warn("NoneType in response discovered; was probably media (LocalCache)")
						self.downloadMedia(link, filepath)
				else:
					# No local resource exists, so crawl it
					logging.debug("RESPONSE: Remote dir "+link+" being used")
					res = self.parse_page(SplashRequest(link))
					if not res:
						logging.warn("NoneType in response discovered; was probably media (SplashRequest)")
						self.downloadMedia(link, self.get_url_filepath(link))

		else:
			logging.debug("NO LINKS FOUND IN: "+response.url)

		return 1

	def download_media(self, url, filepath):
		url = url.strip().strip('"')
		filepath = filepath.strip().strip('"')

		if not os.path.exists(filepath):
			r = requests.get(url, stream=True)
			if r.status_code == 200:
				with open(filepath, 'wb') as f:
					for chunk in r:
						f.write(chunk)
			else:
				return False
		else:
			return False

		return True

	def get_url_filepath(self, link):
		parts = parseUtils.extractURLParts(link)
		filepath = os.path.join(cwd, self.config["folderName"], *parts["fullPath"], parts["page"])
		if "." not in parts["page"]:
			filepath+=".unknown"

		return filepath