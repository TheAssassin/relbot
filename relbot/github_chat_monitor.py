import re
import string

import irc3
from lxml import html

from relbot.util import managed_proxied_session, make_logger, format_github_event

logger = make_logger("github_integration")


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

    # skip all commands
    if any((data.strip(" \r\n").startswith(i) for i in [bot.config["cmd"], bot.config["re_cmd"]])):
        logger.warning("ignoring command: %s", data)
        return

    # this regex will just match any string, even if embedded in some other string
    # the idea is that when there's e.g., punctuation following an issue number, it will still trigger the
    # integration
    matches = re.findall(r"([A-Za-z-_]+/)?([A-Za-z-_]+)?#([0-9]+)", data)
    logger.debug("GitHub issue/PR matches: %r", matches)

    github_chat_monitor_config = bot.config.get("github_chat_monitor", dict())

    try:
        default_repo_owner = github_chat_monitor_config["default_repo_owner"]
        default_repo_name = github_chat_monitor_config["default_repo_name"]
    except KeyError:
        bot.notice(target, "error: default repo owner and/or name not configured")
        return

    for repo_owner, repo_name, issue_id in matches:
        # the regex might match an empty string, for some reason
        # in that case, we just set the default values
        if not repo_owner:
            repo_owner = default_repo_owner

        if not repo_name:
            repo_name = default_repo_name

        # substitute short aliases with the actual repo name, if such aliases are configured
        for short_name, real_name in [i.split(":") for i in github_chat_monitor_config.get("aliases", [])]:
            if repo_name.lower() == short_name.lower():
                repo_name = real_name
                break

        # our match might contain at least one slash, so we need to get rid of that
        repo_owner = repo_owner.rstrip("/")

        def is_valid_name(s: str):
            for c in s:
                if c not in string.ascii_letters + string.digits + "-_":
                    return False
            return True

        if not is_valid_name(repo_owner) or not is_valid_name(repo_name):
            logger.warning("Invalid repository owner or name: %s/%s", repo_owner, repo_name)
            continue

        if not issue_id.isdigit():
            logger.warning("Invalid issue ID: %s", issue_id)
            continue

        # we just check the issues URL; GitHub should automatically redirect to pull requests
        url = "https://github.com/{}/{}/issues/{}".format(repo_owner, repo_name, issue_id)

        with managed_proxied_session() as session:
            response = session.get(url, allow_redirects=True)

        if response.status_code != 200:
            if response.status_code == 404:
                message = "Could not find anything for {}/{}#{}".format(repo_owner, repo_name, issue_id)
            else:
                message = "Request to GitHub failed"

            bot.notice(target, format_github_event(message))

            return

        tree = html.fromstring(response.content)
        title = tree.cssselect(".gh-header-title .js-issue-title")[0].text.strip(" \r\n")

        url_parts = response.url.split("/")
        if "pull" in url_parts:
            type = "PR"
        elif "issues" in url_parts:
            type = "Issue"
        else:
            type = "Unknown Entity"

        notice = format_github_event("{} #{}: {} ({})".format(type, issue_id, title, response.url))

        bot.notice(target, notice)
