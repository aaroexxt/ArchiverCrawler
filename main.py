from crawler import ArchiverCrawler
import os
import json

cwd = os.path.dirname(os.path.realpath(__file__))

cfg_path = "configAaronTech.json"
config = json.load(open(os.path.join(cwd, cfg_path), "r"))

crawler = ArchiverCrawler(config)

crawler.run()

print("Done?")