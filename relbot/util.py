import contextlib
import logging
import os
import sys

import requests


def format_github_event(event):
    s = "[GitHub] {}".format(event)
    return s


@contextlib.contextmanager
def managed_proxied_session():
    """
    Set up requests session with proxies preconfigured. HTTP(S) requests done via this session object should be proxied
    automatically.
    :return: session with proxies preconfigured
    """

    tor_proxy_host = os.environ.get("TOR_PROXY_HOST", "127.0.0.1")

    # local Tor proxy server
    proxies = {
        "http": f"socks5://{tor_proxy_host}:9050",
        "https": f"socks5://{tor_proxy_host}:9050",
    }

    session = requests.session()

    # this way, we only overwrite entries we want to change, and leave existing ones alone
    session.proxies.update(proxies)

    try:
        yield session

    finally:
        session.close()


def make_logger(name: str):
    logger = logging.getLogger(name)

    handler = logging.StreamHandler(sys.stderr)

    # that format is "inspired" by what irc3 uses
    formatter = logging.Formatter("%(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    if "DEBUG" in os.environ:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    return logger
