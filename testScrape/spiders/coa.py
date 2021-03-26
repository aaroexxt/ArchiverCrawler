import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy_splash import SplashRequest
from urllib.parse import urlparse, urljoin
import os
import json
import requests
import time
from .pathUtils import is_path_exists_or_creatable
from tqdm import tqdm

cwd = os.path.dirname(os.path.realpath(__file__))

cfg_path = "configPerkel.json"
config = json.load(open(os.path.join(cwd, cfg_path), "r"))

# TODO: Depth limit https://stackoverflow.com/questions/27805952/scrapy-set-depth-limit-per-allowed-domains
# Possibly limit it in other ways https://stackoverflow.com/questions/30448532/scrapy-wait-for-a-specific-url-to-be-parsed-before-parsing-others


class CoaSpider(scrapy.Spider):
	name = 'coa'
	start_urls = config["startUrls"]
	allowed_domains = config["allowedDomains"]
	custom_settings = {
		'ROBOTSTXT_OBEY': False
	}
	links = []
	crawledCount = 0
	discoveredLinks = len(start_urls)

	link_extractor = LinkExtractor()

	def __init__(self, **kw):
		super(CoaSpider, self).__init__()

		self.pbar = tqdm(total=self.discoveredLinks, ascii=True)
		self.pbar.update(0)

	def start_requests(self):
		for url in self.start_urls:
			yield SplashRequest(url, self.parse, args={'wait': 1, 'html': 1})

	def parse(self, response):
		self.crawledCount+=1
		self.pbar.n = self.crawledCount
		self.pbar.set_description(response.url)
		self.pbar.refresh()

		if response.status != 404:
			# Extract subdirectory, page, path from url
			URLparts = self.extractURLParts(response.url)
			
			# Ensure the subdirs exist, since we're not in a root directory
			self.createSubdirs(os.path.join(cwd, config["folderName"]), URLparts["fullPath"])
			filepath = os.path.join(cwd, config["folderName"], *URLparts["fullPath"], URLparts["page"])
			
			if is_path_exists_or_creatable(filepath):
				if not os.path.exists(filepath): # Ensure we don't overwrite
					self.logger.debug("FILE WRITE: "+filepath)
					with open(filepath, 'wb') as f:
							f.write(response.body)
			else:
				self.logger.warn("FILE INVALID PATH: "+filepath)

			mediaUrls = []
			mediaPaths = []

			# Extract all images relating to page
			result = self.extractMedia(response.url, response.css("img::attr(src)").extract())
			mediaUrls += result["urls"]
			mediaPaths += result["paths"]

			# Extract all JS files relating to page
			result = self.extractMedia(response.url, response.css("script::attr(src)").extract())
			mediaUrls += result["urls"]
			mediaPaths += result["paths"]

			# Extract all CSS files relating to page
			result = self.extractMedia(response.url, response.css("link::attr(href)").extract())
			mediaUrls += result["urls"]
			mediaPaths += result["paths"]

			# Actually download them
			for i in range(0, len(mediaUrls)):
				allowedDownload = False # Is the media that we are requesting from the original website?
				for allowedDomain in self.allowed_domains:
					if allowedDomain in mediaUrls[i]:
						allowedDownload = True
						break

				if not os.path.exists(mediaPaths[i]) and allowedDownload:
					r = requests.get(mediaUrls[i].strip().strip('"'), stream=True)
					if r.status_code == 200:
						with open(mediaPaths[i].strip().strip('"'), 'wb') as f:
							for chunk in r:
								f.write(chunk)

		nextLinks = []
		for link in self.link_extractor.extract_links(response):
			# Clean out any special characters etc
			link.url = self.cleanLink(link.url)

			if (link.url is not None) and (link.url not in self.links): # We've found a new link we haven't seen
				nextLinks.append(link.url)
				self.links.append(link.url)
				self.logger.debug("NEW LINK: "+link.url)

		if len(nextLinks) > 0:
			self.logger.debug("\nDiscovered "+str(len(nextLinks))+" new link(s)")
			self.discoveredLinks+=len(nextLinks)
			self.pbar.total = self.discoveredLinks
			self.pbar.refresh()

			for link in nextLinks:
				yield SplashRequest(link, self.parse, args={'wait': 1, 'html': 1}) #crawl it

	@classmethod
	def from_crawler(cls, crawler, *args, **kwargs):
		spider = super(CoaSpider, cls).from_crawler(crawler, *args, **kwargs)
		crawler.signals.connect(spider.spider_opened, signal=scrapy.signals.spider_opened)
		crawler.signals.connect(spider.spider_closed, signal=scrapy.signals.spider_closed)
		return spider

	def spider_closed(self, spider, reason):
		self.pbar.close()
		self.logger.info("Spider '%s' closed for reason: %s", spider.name, reason)
		self.logger.debug("Now cleaning folder structure...")
		direc = os.path.join(cwd, config["folderName"])
		num = self.removeEmptyFolders(direc)
		self.logger.info("Cleaned directory structure and removed %d empty folders", num)


	def spider_opened(self,spider):
		direc = os.path.join(cwd, config["folderName"])
		if (not os.path.isdir(direc)):
			os.mkdir(direc)

	def extractURLParts(self, url):
		parsed = urlparse(url.strip())
		if len(parsed.path) == 0 or parsed.path == "/" or parsed.path == None:
			return({
				"subdir": parsed.netloc,
				"page": "index.html", #default to base page
				"path": [],
				"fullPath": [parsed.netloc]
			})
		else:
			path = [i for i in parsed.path.split("/") if i]
			page = path[-1] # page is top dir
			path = path[:-1] # page is everything else
			return({
				"subdir": parsed.netloc,
				"page": page,
				"path": path,
				"fullPath": [i for i in ([parsed.netloc]+path) if i]
			})

	def cleanLink(self, url):
		parsed = urlparse(url.strip())
		if parsed.scheme is None or parsed.scheme == "":
			urlClean = "http://"+parsed.path
		else:
			urlClean = urljoin(parsed.scheme+"://"+parsed.netloc, parsed.path)
		return urlClean

	def createSubdirs(self, base, subdirs):
		if len(subdirs) != 0:
			for idx in range(0, len(subdirs)):
				direc = os.path.join(base, *subdirs[:(idx+1)])
				if os.path.exists(direc) and not os.path.isdir(direc): # Uhoh it's a file
					self.logger.debug("DELFILE FOR SUBDIR: "+direc)
					os.remove(direc)

				if not os.path.isdir(direc):
					self.logger.debug("SUBDIR CREATE: "+direc)
					os.mkdir(direc)

	def extractMedia(self, baseURL, mediaURLS):
		extractedURLS = []
		extractedPaths = []

		URLparts = self.extractURLParts(baseURL)
		for mediaURL in mediaURLS:
			parts = self.extractURLParts(mediaURL)
			if parts["subdir"] == "":
				mediaURL = urljoin(baseURL,mediaURL)
				# Relative path, so refer to inside URLparts directory
				self.createSubdirs(os.path.join(cwd, config["folderName"]), URLparts["fullPath"]+parts["fullPath"])
				mediaPath = os.path.join(cwd, config["folderName"], *(URLparts["fullPath"]+parts["fullPath"]), parts["page"])
			else:
				# Absolute path
				self.createSubdirs(os.path.join(cwd, config["folderName"]), parts["fullPath"])
				mediaPath = os.path.join(cwd, config["folderName"], *parts["fullPath"], parts["page"])

			extractedURLS.append(mediaURL)
			extractedPaths.append(mediaPath)

		return({
			"urls": extractedURLS,
			"paths": extractedPaths
		})

	def removeEmptyFolders(self, path):
		count = 0
		if not os.path.isdir(path):
			return 0

		# remove empty subfolders
		files = os.listdir(path)
		if len(files):
			for f in files:
				fullpath = os.path.join(path, f)
				if os.path.isdir(fullpath):
					count += self.removeEmptyFolders(fullpath)

		# if folder empty, delete it
		files = os.listdir(path)
		if len(files) == 0:
			self.logger.debug("Removing empty folder:", path)
			os.rmdir(path)
			count+=1

		return count


