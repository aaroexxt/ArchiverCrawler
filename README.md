# ArchiverCrawler
 Crawls website dynamically by following links on pages and saves all media along the way, to hopefully allow completely local viewing of website

## Use Requirements

 Requires tqdm, logging, requests, urllib, json with Python 3

## How to Use

 First, setup your scrape settings in config.json (use exampleConfig.json to give you an idea)

 Then, start crawling with `python main.py` and you should be set! It'll display progress in realtime as the website is explored. Keep in mind though, as it discovers more valid pages the progress bar may drop (as it only reflects progress based on the current explored pages).
