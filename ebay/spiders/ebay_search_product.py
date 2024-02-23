import scrapy
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import re
import requests

def create_google_product_categories():
    """This method creates a JSON of the google product categories that is used to populate the dropdown"""
    r = requests.get(
        "https://www.google.com/basepages/producttype/taxonomy-with-ids.en-US.txt"
    )

    result = {}

    for category in r.text.strip().split("\n")[1:]:
        line = category.split("-", 1)

        number = int(line[0].strip())

        # Format Category > Sub-category > Sub sub-category > ...
        full_category = line[1].strip()

        # Break up full_catagory
        separated = full_category.split(">")
        last_keyword = separated[-1:]
        result[number] = last_keyword[0].strip()

    return result


class EbaySearchProductSpider(scrapy.Spider):
    name = "ebay_search_product"

    custom_settings = {
        "FEEDS": {
            "data/%(name)s_%(time)s.xlsx": {
                "format": "xlsx",
            }
        }
    }

    def start_requests(self):
        keyword_list = create_google_product_categories()
        for taxonomy_id, keyword in keyword_list.items():
            print(keyword)
            keyword_chars = keyword.replace("&", "%26").replace(" ", "+")
            ebay_search_url = f"https://www.ebay.co.uk/sch/i.html?_from=R40&_trksid=p2380057.m570.l1313&_nkw={keyword_chars}&_sacat=0"
            yield scrapy.Request(
                url=ebay_search_url,
                callback=self.discover_product_urls,
                meta={"keyword": keyword, "taxonomy_id": taxonomy_id},
            )

    def discover_product_urls(self, response):
        keyword = response.meta["keyword"]
        taxonomy_id = response.meta["taxonomy_id"]
        ## Discover Product URLs
        search_products = response.css("#srp-river-results > ul > li")
        if len(search_products) >= 10:
            search_products = search_products[:10]
        for product in search_products:
            product_url = product.css(
                "div > div.s-item__info.clearfix >a::attr(href)"
            ).get()
            yield scrapy.Request(
                url=product_url,
                callback=self.parse_product_data,
                meta={"keyword": keyword, "taxonomy_id": taxonomy_id},
            )

        ## Get All Pages
        # if page == 1:
        #    available_pages = response.xpath(
        #        '//*[contains(@class, "s-pagination-item")][not(has-class("s-pagination-separator"))]/text()'
        #    ).getall()
        #
        #    last_page = available_pages[-1]
        #    for page_num in range(2, int(last_page)):
        #        ebay_search_url = f'https://www.ebay.com/s?k={keyword}&page={page_num}'
        #        yield scrapy.Request(url=ebay_search_url, callback=self.discover_product_urls, meta={'keyword': keyword, 'page': page_num})

    def parse_product_data(self, response):
        # image_data = json.loads(re.findall(r"colorImages':.*'initial':\s*(\[.+?\])},\n", response.text)[0])
        # variant_data = re.findall(r'dimensionValuesDisplayData"\s*:\s* ({.+?}),\n', response.text)
        name = response.css("h1 span::text").get("").strip()
        price = response.css(".x-price-primary>span::text").get("").strip()
        # description is an iframe (independant page). We can keep it as an URL or scrape it later.
        description_url = ""
        if response.css("iframe#desc_ifr::attr(src)"):
            description_url = response.css("iframe#desc_ifr::attr(src)").get("").strip()


        print(response.request.url.split("?")[0])

        yield scrapy.Request(
            url=description_url,
            callback=self.description_parse,
            meta={
                "name": name,
                "price": price,
                "description_url": description_url,
                "url": response.request.url,
                "category": response.meta["keyword"],
                "taxonomy_id": response.meta["taxonomy_id"],
            },
        )

    def description_parse(self, response):
        # Parse the response
        soup = BeautifulSoup(response.body, "html.parser")

        # complete text
        plain_text = soup.get_text(separator=" ")
        plain_text = plain_text.replace("eBay", "").strip()
        plain_text = re.sub(r"\s+", " ", plain_text)
        plain_text = re.sub(r"\n+", r"\n", plain_text)
        plain_text = re.sub(r"\t+", r"\t", plain_text)

        yield {
            "name": response.meta["name"],
            "price": response.meta["price"],
            "url": response.meta["url"].split("?")[0],
            "category": response.meta["category"],
            "description_url": response.meta["description_url"].split("?")[0],
            "description": plain_text,
            "taxonomy_id": response.meta["taxonomy_id"],
        }
