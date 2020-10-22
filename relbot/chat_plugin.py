import itertools
import os
import random
import sys
from urllib.parse import urlencode

from irc3.plugins.command import command
import irc3
import ircmessage
from lxml import html

from .jokes import JokesManager
from .redflare_client import RedflareClient
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

    @command(permission="view")
    def matches(self, mask, target, args):
        """List interesting Red Eclipse matches

            %%matches
        """

        if not self.redflare_url:
            yield "Redflare URL not configured"
            return

        rfc = RedflareClient(self.redflare_url)
        servers = rfc.servers()

        # i: Server
        non_empty_legacy_servers = [s for s in servers if s.players_count > 0 and not s.version.startswith("2.")]

        if not non_empty_legacy_servers:
            yield "No legacy matches running at the moment."
            return

        for server in sorted(non_empty_legacy_servers, key=lambda s: s.players_count, reverse=True):
            players = [p.name for p in server.players]

            # the colors we use to format player names
            colors = ["red", "pink", "green", "teal", "orange", None]
            # make things a bit more interesting by randomizing the order
            random.shuffle(colors)
            # however, once the order is defined, just apply those colors in the ever same order to nicks in the list
            # it'd be nice to assign some sort of "persistent" colors derived from the nicks
            colors = itertools.cycle(colors)

            # this is the "freem exception"
            # freem doesnt like to be pinged on IRC whenever !matches is called while they are playing
            # the easiest way to fix this is to just change the name in the listing
            # ofc this only works until freem decides to use another nickname
            players = ["_freem_" if p == "freem" else p for p in players]

            if server.time_left < 0:
                time_remaining_str = "∞"
            else:
                time_remaining_str = "%d:%d left" % (server.time_left // 60, server.time_left % 60)

            message = "%s on %s (%s): %s %s on %s (%s)" % (
                ircmessage.style(str(server.players_count), fg="red"),
                ircmessage.style("%s" % server.description, fg="orange"),
                ", ".join((ircmessage.style(p, fg=next(colors)) for p in players)),
                ircmessage.style("-".join(server.mutators), fg="teal"),
                ircmessage.style(server.game_mode, fg="green"),
                ircmessage.style(server.map_name, fg="pink"),
                time_remaining_str,
            )

            self.logger.debug(repr(message))

            yield message

    @command(permission="view")
    def rivalry(self, mask, target, args):
        """Show player counts on legacy and 2.x servers

            %%rivalry
        """

        if not self.redflare_url:
            yield "Redflare URL not configured"
            return

        rfc = RedflareClient(self.redflare_url)
        servers = rfc.servers()

        # i: Server
        non_legacy_servers = [s for s in servers if s.version.startswith("2.")]
        legacy_servers = [s for s in servers if not s in non_legacy_servers]

        non_legacy_players_count = sum([s.players_count for s in non_legacy_servers])
        legacy_players_count = sum([s.players_count for s in legacy_servers])

        message = "%d legacy vs. %d non-legacy players" % (legacy_players_count, non_legacy_players_count)

        if non_legacy_players_count == 0:
            if legacy_players_count == 0:
                ratio = None
            else:
                # with no matches running, legacy wins
                # over 9000!
                ratio = 9001
        else:
            ratio = float(legacy_players_count) / float(non_legacy_players_count)

        if ratio is None:
            message += " -- no matches running o_O"
        elif ratio > 2:
            message += " -- WOOHOO!!!111!1!!11"
        elif ratio > 1:
            message += " -- awesome!"
        elif ratio == 1:
            message += "... meh..."
        else:
            message += "... urgh..."

        yield message

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
