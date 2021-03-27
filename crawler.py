import os
import time
from tqdm import tqdm
import logging
import requests

from pageRequest import SplashRequest, LocalRequest
from pathUtils import is_path_exists_or_creatable
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
				if not os.path.isfile(filepath): # Ensure we don't overwrite
					logging.debug("FILE WRITE: "+filepath)
					with open(filepath, 'w', encoding="utf8") as f:
							f.write(response.body)
			else:
				logging.warn("FILE INVALID PATH: "+filepath)

			mediaUrls = []
			mediaPaths = []

			# Extract all images relating to page
			result = parseUtils.extractMedia(self.config, response.url, response.css("img::attr(src)").extract())
			mediaUrls += result["urls"]
			mediaPaths += result["paths"]

			# Extract all JS files relating to page
			result = parseUtils.extractMedia(self.config, response.url, response.css("script::attr(src)").extract())
			mediaUrls += result["urls"]
			mediaPaths += result["paths"]

			# Extract all CSS files relating to page
			result = parseUtils.extractMedia(self.config, response.url, response.css("link::attr(href)").extract())
			mediaUrls += result["urls"]
			mediaPaths += result["paths"]

			# Filter items already downloaded
			finalMediaPaths = []
			finalMediaUrls = []
			for idx in range(0, len(mediaPaths)):
				path = mediaPaths[idx]
				url = mediaUrls[idx]

				if is_path_exists_or_creatable(path) and not os.path.isfile(path):
					if "." not in parseUtils.extractURLParts(url)["page"]:
						path+=".unknown"
					finalMediaPaths.append(path)
					finalMediaUrls.append(url)
					logging.debug("MEDIA: downloading "+url)
				else:
					logging.debug("MEDIA: Local copy of "+url+" being used")

			# Actually download them
			if len(finalMediaPaths) > 0:
				for i in range(0, len(finalMediaUrls)):
					allowedDownload = False # Is the media that we are requesting from the original website?
					for allowedDomain in self.allowed_domains:
						if allowedDomain in finalMediaUrls[i]:
							allowedDownload = True
							break

					mediaPath = finalMediaPaths[i].strip().strip('"')
					if not os.path.exists(mediaPath) and allowedDownload:
						r = requests.get(finalMediaUrls[i].strip().strip('"'), stream=True)
						if r.status_code == 200:
							with open(mediaPath, 'wb') as f:
								for chunk in r:
									f.write(chunk)

		nextLinks = [] # All valid and new links from the page
		for link in response.css("a::attr(href)").extract():
			# Clean out any special characters etc
			link = parseUtils.cleanLink(link) # Will return None if invalid

			allowedFollow = False # Is the media that we are requesting from the original website?
			if link is not None:
				for allowedDomain in self.allowed_domains:
					if allowedDomain in link:
						allowedFollow = True
						break

			if (link is not None) and (link not in self.links) and allowedFollow: # We've found a new link we haven't seen
				nextLinks.append(link)
				self.links.append(link)
				logging.debug("NEW LINK: "+link)

		if len(nextLinks) > 0:
			logging.debug("\nDiscovered "+str(len(nextLinks))+" new link(s)")
			self.discoveredLinks+=len(nextLinks)
			self.pbar.total = self.discoveredLinks
			self.pbar.refresh()

			for link in nextLinks:
				# First we check if a local copy exists on the disk
				localParts = parseUtils.extractURLParts(link)
				filepath = os.path.join(cwd, self.config["folderName"], *localParts["fullPath"], localParts["page"])
				if "." not in localParts["page"]:
					filepath+=".unknown"
				if is_path_exists_or_creatable(filepath) and os.path.isfile(filepath):
					with open(filepath, 'r') as file:
						filedata = file.read()
					logging.debug("RESPONSE: Local file at "+filepath+" being used")
					self.parse_page(LocalRequest(link, filedata))
				else:
					# No local resource exists, so crawl it
					logging.debug("RESPONSE: Remote dir "+link+" being used")
					self.parse_page(SplashRequest(link))
		else:
			logging.debug("NO LINKS FOUND IN: "+response.url)