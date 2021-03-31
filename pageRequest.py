import requests
from parsel import Selector

class SplashRequest():
	def __init__(self, url, adArr, **kw):
		if len(adArr) == 0:
			allowedDomains = "*"
		elif len(adArr) == 1:
			allowedDomains = adArr
		else:
			allowedDomains = ",".join(adArr)

		r = requests.get('http://localhost:8050/render.html', params={
			'url': url,
			'wait': 0.25, 
			'html5_media': 1,
			'html': 1,
			'resource_timeout': 1,
			'allowed_domains': allowedDomains,
			'timeout': 12
		})
		self.url = url
		self.status = r.status_code
		if (r.status_code == 200):
			self.body = r.text
			selector = Selector(text=self.body)
		else:
			self.body = None
			selector = Selector(text="")

		self.css = selector.css
		self.xpath = selector.xpath

class LocalRequest():
	def __init__(self, url, filedata, **kw):
		self.url = url
		self.body = filedata
		self.status = 200

		selector = Selector(text=self.body)
		self.css = selector.css
		self.xpath = selector.xpath
