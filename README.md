# ArchiverCrawler
 Crawls website dynamically using Scrapy and saves all media along the way, to hopefully allow completely local viewing of website

## Use Requirements

Requres Scrapy and Scrapy-Splash to be installed

## How to Use

Start the Splash server: `docker run -p 8050:8050 scrapinghub/splash`
Then, start the crawler: `scrapy crawl coa`