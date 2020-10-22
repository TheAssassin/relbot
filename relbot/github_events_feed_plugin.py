import irc3
import requests
from irc3.plugins.command import command
from irc3.plugins.cron import cron

from relbot.github_events_api_client import GithubEventsAPIClient
from relbot.util import format_github_event, make_logger


@irc3.plugin
class RELBotGitHubEventsFeedPlugin:
    def __init__(self, bot):
        self.logger = make_logger(self.__class__.__name__)

        self.bot = bot

        events_channels = self._get_github_events_channels()

        if events_channels:
            self.logger.info("Setting up GitHub events API integration (channels enabled: %r)", events_channels)
            self.github_events_api_client = GithubEventsAPIClient("blue-nebula")
            self.github_events_api_client.setup()
            self.logger.info("Finished setting up GitHub events API integration")

        else:
            self.logger.info("GitHub events API integration disabled")
            self.github_events_api_client = None

    def _relbot_config(self):
        return self.bot.config.get("relbot", dict())

    def _get_github_events_channels(self):
        config_key = "github_events_channels"

        config_value = self._relbot_config().get(config_key)

        # not too Pythonic, but both str and list are iterable...
        if isinstance(config_value, str):
            return config_value.split()
        elif isinstance(config_value, list):
            return config_value
        else:
            raise ValueError("Unsupported value for %s: %r", config_key, config_value)

    @cron("*/1 * * * *")
    def check_github_events(self):
        channels = self._get_github_events_channels()

        if not channels:
            self.logger.debug("cron job check_github_events skipped: no channels configured")
            return

        self.logger.info("cron job running: check_github_events %r", channels)

        try:
            # need a list to be able to slice and reverse the events
            events = list(self.github_events_api_client.fetch_new_events())

        except requests.exceptions.HTTPError as e:
            # might have run into a rate limit
            # just ignore it for now
            self.logger.error("HTTP error while fetching events from GitHub:", e)

        else:
            for event in reversed(events):
                notice = format_github_event(event)

                self.logger.info(notice)

                for target in channels:
                    self.bot.notice(target, notice)

            else:
                self.logger.info(format_github_event("no new events to report"))

    @command(name="test-gh-events", permssion="admin", show_in_help_list=False)
    def test_proxy(self, mask, target, args):
        """Fetch last n events from GitHub events API

            %%test-gh-events <limit>
        """

        try:
            limit = int(args["<limit>"])
        except ValueError:
            yield "invalid argument: not an int: %s" % args["<limit>"]
            return

        try:
            events = self.github_events_api_client.fetch_events()

        except requests.exceptions.HTTPError as e:
            # might have run into a rate limit
            # just ignore it for now
            print("HTTP error while fetching events from GitHub:", e)

        else:
            for event in reversed(events[:limit]):
                notice = format_github_event(event)
                self.bot.notice(target, notice)
