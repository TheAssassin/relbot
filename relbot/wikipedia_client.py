from collections import namedtuple
from typing import Iterator
from urllib.parse import urlencode, quote

from bs4 import BeautifulSoup

from relbot.util import managed_proxied_session


WikipediaPage = namedtuple("WikipediaPage", ["title", "snippet"])


class WikipediaAPIError(Exception):
    pass


class WikipediaAPIClient:
    @staticmethod
    def build_search_api_url(term: str):
        # example: https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=C++&format=json

        querystring = urlencode({
            "action": "query",
            "list": "search",
            "srsearch": term,
            "format": "json",
        })

        url = "https://en.wikipedia.org/w/api.php?{}".format(querystring)

        return url

    @staticmethod
    def get_page_url(title: str):
        return "https://en.wikipedia.org/wiki/{}".format(quote(title))

    @classmethod
    def search_for_term(cls, term: str) -> Iterator[WikipediaPage]:
        url = cls.build_search_api_url(term)

        with managed_proxied_session() as session:
            response = session.get(url, allow_redirects=True)

        if response.status_code != 200:
            raise WikipediaAPIError("HTTP status %d" % response.status_code)

        data = response.json()

        error = data.get("error", None)

        if error:
            raise WikipediaAPIError("API error: %s: %s" % (error["code"], error["info"]))

        for result in data["query"]["search"]:
            title = result["title"]

            snippet = BeautifulSoup(result["snippet"], "lxml").get_text()

            yield WikipediaPage(title, snippet)


if __name__ == "__main__":
    print(WikipediaAPIClient.get_page_url("Python"))

    for p in WikipediaAPIClient.search_for_term("Python"):
        print(p)

