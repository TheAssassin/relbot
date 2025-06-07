import itertools
import random

import irc3
import irccodes
from irc3.plugins.command import command

from relbot.redflare_client import RedflareClient
from relbot.util import make_logger


@irc3.plugin
class RELBotBNPlugin:
    def __init__(self, bot):
        self.logger = make_logger(self.__class__.__name__)

        self.bot = bot
        self.redflare_url = self._relbot_config().get("redflare_url", None)

    def _relbot_config(self):
        return self.bot.config.get("relbot", dict())

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
            colors = ["light red", "pink", "green", "light green", "orange", None]
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

            def make_colored(string: str, color: str | None):
                if not color:
                    return string
                return irccodes.colored(string, color, padding="")

            message = "%s on %s (%s): %s %s on %s (%s)" % (
                make_colored(str(server.players_count), "light red"),
                make_colored(server.description, "orange"),
                ", ".join((make_colored(p, next(colors)) for p in players)),
                make_colored("-".join(server.mutators), "light cyan"),
                make_colored(server.game_mode, "green"),
                make_colored(server.map_name, "pink"),
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
