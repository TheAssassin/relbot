from collections import namedtuple
from typing import List, Iterator
from urllib.parse import urlencode

import requests
from lxml import html


class UrbanDictionaryError(Exception):
    pass


UrbanDictionaryDefinition = namedtuple("UrbanDictionaryDefinition", ["word", "meaning", "example"])


class UrbanDictionaryClient:
    @staticmethod
    def build_url(term: str):
        querystring = urlencode({
            "term": term,
        })

        url = "https://www.urbandictionary.com/define.php?{}".format(querystring)

        return url

    @classmethod
    def define_all(cls, term: str) -> Iterator[UrbanDictionaryDefinition]:
        url = cls.build_url(term)

        proxies = {
            "http": "socks5://127.0.0.1:9050",
            "https": "socks5://127.0.0.1:9050",
        }

        response = requests.get(url, allow_redirects=True, proxies=proxies)

        if response.status_code != 200:
            raise UrbanDictionaryError("HTTP status %d" % response.status_code)

        tree = html.fromstring(response.content)

        definitions = tree.cssselect("#content .def-panel")

        for definition in definitions:
            kwargs = {}

            for attribute in ["word", "meaning", "example"]:
                attrib_elem = definition.cssselect(".{}".format(attribute))[0]
                kwargs[attribute] = attrib_elem.text_content().replace("\n", " ")

            yield UrbanDictionaryDefinition(**kwargs)

    @classmethod
    def top_definition(cls, term: str):
        return next(cls.define_all(term))


if __name__ == "__main__":
    print(UrbanDictionaryClient.top_definition("lol"))
    print(UrbanDictionaryClient.top_definition("lulz"))
