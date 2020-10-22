import re

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

    # skip all commands
    if any((data.strip(" \r\n").startswith(i) for i in [bot.config["cmd"], bot.config["re_cmd"]])):
        logger.warning("ignoring command: %s", data)
        return

    # this regex will just match any string, even if embedded in some other string
    # the idea is that when there's e.g., punctuation following an issue number, it will still trigger the
    # integration
    issue_ids = re.findall(r"#([0-9]+)", data)
    logger.debug("found IDs: %r", issue_ids)

    for issue_id in issue_ids:
        # we just check the issues URL; GitHub should automatically redirect to pull requests
        url = "https://github.com/blue-nebula/base/issues/{}".format(issue_id)

        with managed_proxied_session() as session:
            response = session.get(url, allow_redirects=True)

        if response.status_code != 200:
            if response.status_code == 404:
                message = "Could not find anything for #{}".format(issue_id)
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

    else:
        logger.debug("could not find any GitHub IDs in message")
