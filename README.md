# ArchiverCrawler
 Crawls website dynamically by following links on pages and saves all media along the way, to hopefully allow completely local viewing of website or dataset collection

## Use Requirements

 Requires tqdm, logging, requests, urllib, json, parsel in Python 3
 
 Install them all by running:
 
 `pip install tqdm logging requests urllib json parsel`

## How to Use

 First, setup your scrape settings in config.json (use `configSample.json` to give you an idea)
 
 Then, start the Splash rendering server to render the webpages in a headless way.

 Start it with `docker run -it -p 8050:8050 --rm scrapinghub/splash`

 Then, open a new terminal window and start crawling with `python main.py` and you should be set!
 It'll display progress in realtime as the website is explored. Keep in mind though, as it discovers more valid pages the progress bar may drop (as it only reflects progress based on the current explored pages).

## Splash Server

The splash server renders webpages locally in a headless way to facilitate full loading of media and links that wouldn't be immediately be apparent from looking at the local HTML.

You'll need to install Docker, then run: `docker pull scrapinghub/splash` and you should be set!


