"""
This modules implements the CrawlSpider which is the recommended spider to use
for scraping typical web sites that requires crawling pages.

See documentation in docs/topics/spiders.rst
"""

import copy
import six

from scrapy.http import Request, HtmlResponse
from scrapy.utils.spider import iterate_spider_output
from scrapy.spiders import Spider


def identity(x):
    return x


class Rule(object):

    def __init__(self, link_extractor, callback=None, cb_kwargs=None, follow=None, process_links=None, process_request=identity):
        self.link_extractor = link_extractor
        self.callback = callback
        self.cb_kwargs = cb_kwargs or {}
        self.process_links = process_links
        self.process_request = process_request
        if follow is None:
            self.follow = False if callback else True
        else:
            self.follow = follow


class CrawlSpider(Spider):
    """
    Class for spiders that crawl over web pages and extract/parse their links
    given some crawling rules.

    These crawling rules are established by setting the 'rules' class attribute,
    which is a tuple of Rule objects.
    When the spider is running, it iterates over these rules with each response
    and do what it has to (extract links if follow=True, and return items/requests if
    there's a parsing method defined in the rule).
    """
    rules = ()

    def __init__(self, *a, **kw):
        """Constructor takes care of compiling rules"""
        super(CrawlSpider, self).__init__(*a, **kw)
        self._compile_rules()

    def parse(self, response):
        """
        This function is called by the framework core for all the
        start_urls. Do not override this function, override parse_start_url
        instead.
        """
        return self._parse_response(response, self.parse_start_url, cb_kwargs={}, follow=True)

    def parse_start_url(self, response):
        """
        Overrideable callback function for processing start_urls. It must
        return a list of BaseItem and/or Requests.
        """
        return []

    def process_results(self, response, results):
        """
        This overridable method is called for each result (item or request)
        returned by the spider, and it's intended to perform any last time
        processing required before returning the results to the framework core,
        for example setting the item GUIDs. It receives a list of results and
        the response which originated that results. It must return a list
        of results (Items or Requests).
        """
        return results

    def _build_request(self, rule, link):
        r = Request(url=link.url, callback=self._response_downloaded)
        r.meta.update(rule=rule, link_text=link.text)
        return r

    def _requests_to_follow(self, response):
        """
        This method iterates over each of the spider's rules, extracts the links
        matching each case, filters them (if needed), and returns a list of unique
        requests per response.
        """
        if not isinstance(response, HtmlResponse):
            return
        seen = set()
        for n, rule in enumerate(self._rules):
            links = [lnk for lnk in rule.link_extractor.extract_links(response)
                     if lnk not in seen]
            if links and rule.process_links:
                links = rule.process_links(links)
            for link in links:
                seen.add(link)
                r = self._build_request(n, link)
                yield rule.process_request(r)

    def _response_downloaded(self, response):
        """
        This is were any response arrives, and were it's decided whether
        to extract links or not from it, and if it will be parsed or not.
        It returns a list of requests/items.
        """
        rule = self._rules[response.meta['rule']]
        return self._parse_response(response, rule.callback, rule.cb_kwargs, rule.follow)

    def _parse_response(self, response, callback, cb_kwargs, follow=True):
        if callback:
            cb_res = callback(response, **cb_kwargs) or ()
            cb_res = self.process_results(response, cb_res)
            for requests_or_item in iterate_spider_output(cb_res):
                yield requests_or_item

        if follow and self._follow_links:
            for request_or_item in self._requests_to_follow(response):
                yield request_or_item

    def _compile_rules(self):
        """Compile the crawling rules"""
        def get_method(method):
            if callable(method):
                return method
            elif isinstance(method, six.string_types):
                return getattr(self, method, None)

        self._rules = [copy.copy(r) for r in self.rules]
        for rule in self._rules:
            rule.callback = get_method(rule.callback)
            rule.process_links = get_method(rule.process_links)
            rule.process_request = get_method(rule.process_request)

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(CrawlSpider, cls).from_crawler(crawler, *args, **kwargs)
        spider._follow_links = crawler.settings.getbool(
            'CRAWLSPIDER_FOLLOW_LINKS', True)
        return spider

    def set_crawler(self, crawler):
        super(CrawlSpider, self).set_crawler(crawler)
        self._follow_links = crawler.settings.getbool('CRAWLSPIDER_FOLLOW_LINKS', True)
