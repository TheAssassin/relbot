import re

import irc3
from lxml import html

from relbot.github_issues_matcher import GitHubIssuesMatcher
from relbot.util import managed_proxied_session, make_logger, format_github_event

logger = make_logger("github_integration")


class GitHubChatMonitorError(Exception):
    def __init__(self, message):
        self._message = message

    def __str__(self):
        return self._message


@irc3.event(irc3.rfc.PRIVMSG)
def github_chat_monitor(bot, mask, target, data, **kwargs):
    """
    Check every message if it contains GitHub references (i.e., some #xyz number), and provide a link to GitHub
    if possible.
    Uses web scraping instead of any annoying
    Note: cannot use yield to send replies; it'll fail silently then
    """

    # do not react on notices
    # this should prevent the bot from replying to other bots
    if kwargs["event"].lower() != "privmsg":
        logger.debug("ignoring %s event", kwargs["event"])
        return

    # also ignore quote part in what looks like one of these annoying Matrix IRC bridge reply messages
    match = re.search(r'^<[^"]+\s".*">\s(.*)', data)
    if match:
        logger.debug("ignoring quoted part in potential Matrix IRC bridge reply")
        data = match.group(1)

    # skip all commands
    if any((data.strip(" \r\n").startswith(i) for i in [bot.config["cmd"], bot.config["re_cmd"]])):
        logger.warning("ignoring command: %s", data)
        return

    try:
        github_chat_monitor_config = bot.config.get("github_chat_monitor", dict())

        default_organization = github_chat_monitor_config["default_organization"]
        default_repository = github_chat_monitor_config["default_repository"]

    except KeyError:
        bot.notice(target, "Error: default repo owner and/or name not configured")
        return

    except:
        message = "Unknown error while parsing GitHub issues"
        logger.exception(message)
        bot.notice(target, message)
        return

    try:
        aliases = github_chat_monitor_config["aliases"]
        parsed_aliases = {i: j for i, j in (i.split(":") for i in aliases)}

    except (KeyError, TypeError):
        parsed_aliases = {}

    resolver = GitHubIssuesMatcher(default_organization, default_repository, parsed_aliases)

    issues = resolver.find_github_issue_ids(data) + resolver.find_github_urls(data)

    issues = resolver.deduplicate(issues)
    logger.debug("deduplicated issues: %r", issues)

    for repo_owner, repo_name, issue_id in issues:
        # we just check the issues URL; GitHub should automatically redirect to pull requests
        url = f"https://github.com/{repo_owner}/{repo_name}/issues/{issue_id}"

        with managed_proxied_session() as session:
            response = session.get(url, allow_redirects=True)

        if response.status_code != 200:
            if response.status_code == 404:
                # by providing a link, issues and PRs can still be accessed easily in case a repo is private
                # if it just doesn't exist, users will see an error message on GitHub
                message = (
                    f"Could not find any information on {repo_owner}/{repo_name}#{issue_id} "
                    f"(repository might be private, you can still try to open {url})"
                )
            else:
                message = "Request to GitHub failed"

            bot.notice(target, format_github_event(message))

            continue

        tree = html.fromstring(response.content)
        try:
            title = tree.cssselect("[data-testid=issue-header] bdi")[0].text.strip(" \r\n")
        except IndexError:
            title = tree.cssselect(".gh-header-title .js-issue-title")[0].text.strip(" \r\n")

        url_parts = response.url.split("/")
        if "pull" in url_parts:
            type = "PR"
        elif "issues" in url_parts:
            type = "Issue"
        elif "discussions" in url_parts:
            type = "Discussion"
        else:
            type = "Unknown Entity"

        notice = format_github_event("{} #{}: {} ({})".format(type, issue_id, title, response.url))

        bot.notice(target, notice)
