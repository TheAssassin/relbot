import itertools
import random
from urllib.parse import urlencode

import requests
from irc3.plugins.command import command
import irc3
import ircmessage
from lxml import html
import re

from .redflare_client import RedflareClient


@irc3.plugin
class RELBotPlugin:
    def __init__(self, bot):
        self.bot = bot
        self.redflare_url = self.bot.config.get("relbot", dict()).get("redflare_url", None)

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

            message = "%s on %s (%s): %s %s on %s" % (
                ircmessage.style(str(server.players_count), fg="red"),
                ircmessage.style("%s" % server.description, fg="orange"),
                ", ".join((ircmessage.style(p, fg=next(colors)) for p in players)),
                ircmessage.style("-".join(server.mutators), fg="teal"),
                ircmessage.style(server.game_mode, fg="green"),
                ircmessage.style(server.map_name, fg="pink"),
            )

            print(repr(message))

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

    @command(name="reload-plugin", permission="view")
    def reload_plugin(self, mask, target, args):
        """Reloads this plugin

            %%reload-plugin
        """

        self.bot.reload("relbot.chat_plugin")

        yield "Done!"

    @command(name="rp", permission="view")
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

    @command(name="chuck", permission="view")
    def chuck(self, mask, target, args):
        """Tell a Chuck Norris joke from the Internet Chuck Norris Database (icndb.com)

            %%chuck
        """

        proxies = {
            "http": "socks5://127.0.0.1:9050",
            "https": "socks5://127.0.0.1:9050",
        }

        url = "http://api.icndb.com/jokes/random"

        response = requests.get(url, allow_redirects=True, proxies=proxies)

        yield response.json()["value"]["joke"]

    @irc3.event(irc3.rfc.PRIVMSG)
    def github_integration(self, mask, target, data, **kwargs):
        """Check every message if it contains GitHub references (i.e., some #xyz number), and provide a link to GitHub
        if possible.
        Uses web scraping instead of any annoying
        Note: cannot use yield to send replies; it'll fail silently then
        """

        # skip all commands
        if any((data.strip(" \r\n").startswith(i) for i in [self.bot.config["cmd"], self.bot.config["re_cmd"]])):
            return

        # some things can't be done easily by a regex
        # we have to intentionally terminate the data with a space
        # that way, we can check that the #123 like patters stand alone using a regex that makes sure there's at least
        # a whitespace character after the interesting bit, ensuring that strings like #123abc are not matched
        # this should prevent some false and unnecessary checks
        data += " "

        matches = re.findall(r"#([0-9]+)\s+", data)

        print(matches)

        for match in matches:
            # we just check the issues URL; GitHub should automatically redirect to pull requests
            url = "https://github.com/blue-nebula/base/issues/{}".format(match)

            proxies = {
                "http": "socks5://127.0.0.1:9050",
                "https": "socks5://127.0.0.1:9050",
            }

            response = requests.get(url, allow_redirects=True, proxies=proxies)

            if response.status_code != 200:
                print("argh", response)

            tree = html.fromstring(response.content)
            title = tree.cssselect(".gh-header-title .js-issue-title")[0].text.strip(" \r\n")

            notice = "[GitHub] {} ({})".format(title, response.url)

            self.bot.notice(target, notice)

    @classmethod
    def reload(cls, old):
        return cls(old.bot)
