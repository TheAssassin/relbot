import os
import random
import sys
from urllib.parse import urlencode

from irc3.plugins.command import command
import irc3
from lxml import html

from .jokes import JokesManager
from .urbandictionary_client import UrbanDictionaryClient, UrbanDictionaryError
from .util import managed_proxied_session, make_logger
from .wikipedia_client import WikipediaAPIError, WikipediaAPIClient


@irc3.plugin
class RELBotPlugin:
    def __init__(self, bot):
        self.logger = make_logger("RELBotPlugin")

        self.bot = bot
        self.redflare_url = self._relbot_config().get("redflare_url", None)

        try:
            self.jokes_manager = JokesManager(self._relbot_config()["jokes_file"])
        except KeyError:
            self.jokes_manager = None

    def _relbot_config(self):
        return self.bot.config.get("relbot", dict())

    @command(name="test-proxy", permssion="admin", show_in_help_list=False)
    def test_proxy(self, mask, target, args):
        """bla

            %%test-proxy
        """

        with managed_proxied_session() as session:
            response = session.get("https://check.torproject.org/")

        doc = html.fromstring(response.text)
        yield doc.cssselect("h1.not")[0].text.strip()

    @command(name="reload-plugin", permission="admin")
    def reload_plugin(self, mask, target, args):
        """Reloads this plugin

            %%reload-plugin
        """

        self.bot.reload("relbot.chat_plugin")

        yield "Done!"

    @command(name="rp", permission="admin")
    def rp(self, *args, **kwargs):
        """Reloads this plugin

            %%rp
        """
        return self.reload_plugin(*args, **kwargs)

    @command(name="lmgtfy", permission="view")
    def lmgtfy(self, mask, target, args):
        """Let me google that for you!

            %%lmgtfy <args>...
        """

        querystring = urlencode({
            "q": " ".join(args["<args>"]),
        })

        yield "https://lmgtfy.com/?{}".format(querystring)

    @command(name="ud", permission="view")
    def urbandictionary(self, mask, target, args):
        """Search a term on urbandictionary.com

            %%ud <args>...
        """

        term = " ".join(args["<args>"])

        try:
            definition = UrbanDictionaryClient.top_definition(term)
        except UrbanDictionaryError as e:
            yield "error while fetching data from urbandictionary.com: %s" % str(e)
        except:
            yield "unknown error occured"
        else:
            yield "%s: %s (example: %s)" % (definition.word, definition.meaning, definition.example)

            notice = "see %s for more definitions" % UrbanDictionaryClient.build_url(term)
            self.bot.notice(target, notice)


    @command(name="wiki", permission="view")
    def wikipedia_search(self, mask, target, args):
        """Search a term on en.wikipedia.org

            %%wiki <args>...
        """

        args_args = args["<args>"]

        # by default, fetch only one result
        num_results = 1

        # it can be overwritten with a user-specified value, though
        if len(args_args) > 1:
            try:
                num_results = int(args_args[-1])

            except ValueError:
                pass

            else:
                # in case the conversion worked, we remove the last item from the list
                args_args.pop()

        term = " ".join(args_args)

        try:
            search_results = list(WikipediaAPIClient.search_for_term(term))

        except WikipediaAPIError as e:
            yield "Wikipedia API error: %s" % str(e)

        except:
            yield "unknown error occured"

        else:
            for page in search_results[:num_results]:
                url = WikipediaAPIClient.get_page_url(page.title)
                yield "%s: %s (%s)" % (page.title, page.snippet, url)

    @command(name="chuck", permission="view")
    def chuck(self, mask, target, args):
        """Tell a Chuck Norris joke from the Internet Chuck Norris Database (icndb.com)

            %%chuck
        """

        url = "http://api.icndb.com/jokes/random"

        with managed_proxied_session() as session:
            response = session.get(url, allow_redirects=True)

        yield response.json()["value"]["joke"]

    @command(name="joke", permission="view")
    def joke(self, mask, target, args):
        """
        Tell a Blue Nebula (code) joke.

            %%joke
        """

        if self.jokes_manager is None:
            yield "Jokes file not configured"

        else:
            joke = self.jokes_manager.get_random()

            if joke is None:
                yield "No jokes found"
            else:
                yield joke

    @command(name="register-joke", permission="jokes-admin")
    def register_joke(self, mask, target, args):
        """
        Register code joke.

            %%register-joke <args>...
        """

        if self.jokes_manager is None:
            yield "Jokes file not configured"

        else:
            self.jokes_manager.register_joke(" ".join(args["<args>"]))
            yield "Done!"

    @command(name="cookie", permission="view")
    def cookie(self, mask, target, args):
        """
        Give someone a cookie from the jar.

            %%cookie <nick>
        """

        upper_limit = 10

        if random.randint(0, upper_limit) == (upper_limit // 2):
            yield "The jar is empty! Bummer! Gonna go buy some more!"

        else:
            yield "%s gets a cookie from the jar." % args["<nick>"]

    @command(name="bug", permission="view")
    def bug(self, mask, target, args):
        """Show link to issue tracker.

            %%bug
        """

        yield "https://github.com/TheAssassin/relbot/issues/new"

    @command(name="restart-bot", permission="admin")
    def restart(self, mask, target, args):
        """Restart entire bot.

            %%restart-bot
        """

        os.execl(sys.executable, sys.executable, *sys.argv)

    @classmethod
    def reload(cls, old):
        return cls(old.bot)
