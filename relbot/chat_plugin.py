import itertools
import random

from irc3.plugins.command import command
import irc3
import ircmessage

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
            ratio = 0
        else:
            ratio = float(legacy_players_count) / float(non_legacy_players_count)

        if ratio == 0:
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

    @command(permission="view")
    def reload_plugin(self, mask, target, args):
        """Reloads this plugin

            %%reload_plugin
        """

        self.bot.reload("relbot.chat_plugin")

        yield "Done!"

    @classmethod
    def reload(cls, old):
        return cls(old.bot)
