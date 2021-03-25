import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy_splash import SplashRequest
from urllib.parse import urlparse, urljoin
import os
import json
import requests
import time

cwd = os.path.dirname(os.path.realpath(__file__))

cfg_path = "configChurchOfReality.json"

config = json.load(open(os.path.join(cwd, cfg_path), "r"))
folderName = config["folderName"]

# TODO: Depth limit https://stackoverflow.com/questions/27805952/scrapy-set-depth-limit-per-allowed-domains
# Possibly limit it in other ways https://stackoverflow.com/questions/30448532/scrapy-wait-for-a-specific-url-to-be-parsed-before-parsing-others

direc = os.path.join(cwd, folderName)
if (not os.path.isdir(direc)):
    os.mkdir(direc)

class CoaSpider(scrapy.Spider):
    name = 'coa'
    start_urls = config["startUrls"]
    allowed_domains = config["allowedDomains"]
    custom_settings = {
        'ROBOTSTXT_OBEY': False
    }
    links = []
    link_extractor = LinkExtractor()

    def start_requests(self):
        for url in self.start_urls:
            yield SplashRequest(url, self.parse, args={'wait': 1, 'html': 1})

    def parse(self, response):
        if response.status != 404:
            # Extract subdirectory, page, path from url
            URLparts = self.extractURLParts(response.url)
            
            # Ensure the subdirs exist, since we're not in a root directory
            self.createSubdirs(os.path.join(cwd, folderName), URLparts["fullPath"])
            filepath = os.path.join(cwd, folderName, *URLparts["fullPath"], URLparts["page"])
            
            if not os.path.exists(filepath): # Ensure we don't overwrite
                self.logger.info("FILE WRITE: "+filepath)
                with open(filepath, 'wb') as f:
                        f.write(response.body)

            mediaUrls = []
            mediaPaths = []

            # Extract all images relating to page
            result = self.extractMedia(response.url, response.css("img::attr(src)").extract())
            mediaUrls += result["urls"]
            mediaPaths += result["paths"]

            # Save all JS files relating to page
            result = self.extractMedia(response.url, response.css("script::attr(src)").extract())
            mediaUrls += result["urls"]
            mediaPaths += result["paths"]

            # Save all CSS files relating to page
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
                    r = requests.get(mediaUrls[i], stream=True)
                    if r.status_code == 200:
                        with open(mediaPaths[i], 'wb') as f:
                            for chunk in r:
                                f.write(chunk)

        for link in self.link_extractor.extract_links(response):
            # Clean out any special characters etc
            link.url = self.cleanLink(link.url)

            if (link.url is not None) and (link.url not in self.links): # We've found a new link we haven't seen
                self.links.append(link.url)

                self.logger.info("NEW LINK: "+link.url)

                yield SplashRequest(link.url, self.parse, args={'wait': 1, 'html': 1}) #crawl it
            #else:
                #self.logger.debug("DEAD LINK: "+link.url)

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
                    self.logger.info("DELFILE FOR SUBDIR: "+direc)
                    os.remove(direc)

                if not os.path.isdir(direc):
                    self.logger.info("SUBDIR CREATE: "+direc)
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
                self.createSubdirs(os.path.join(cwd, folderName), URLparts["fullPath"]+parts["fullPath"])
                mediaPath = os.path.join(cwd, folderName, *(URLparts["fullPath"]+parts["fullPath"]), parts["page"])
            else:
                # Absolute path
                self.createSubdirs(os.path.join(cwd, folderName), parts["fullPath"])
                mediaPath = os.path.join(cwd, folderName, *parts["fullPath"], parts["page"])

            extractedURLS.append(mediaURL)
            extractedPaths.append(mediaPath)

        return({
            "urls": extractedURLS,
            "paths": extractedPaths
        })


