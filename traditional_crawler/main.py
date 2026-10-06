from crawler.crawler import crawl


start_url = "https://books.toscrape.com/"

pages = crawl(
    start_url,
    max_pages=10,
    max_depth=1,
    delay=1.0
)

print("\nCrawled pages:")

for page in pages:
    print(page)