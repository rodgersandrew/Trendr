import scrapy


class ContentSpider(scrapy.Spider):
    name = 'content'

    def parse(self, response):
        content = u''.join(response.css("p::text").extract())
        url = response.request.url

        item = {'url': url, 'content': content}

        return item
