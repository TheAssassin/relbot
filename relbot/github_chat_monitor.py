import re
import string
import urllib.parse
from typing import NamedTuple, List, Dict

import irc3
from lxml import html

from relbot.util import managed_proxied_session, make_logger, format_github_event

logger = make_logger("github_integration")


class GitHubChatMonitorError(Exception):
    def __init__(self, message):
        self._message = message

    def __str__(self):
        return self._message


class GitHubIssue(NamedTuple):
    repo_owner: str
    repo_name: str
    issue_id: int

    def __str__(self):
        # calculate the unique ID for every issue and put it in a dict
        # this ensures we don't have duplicates in there
        issue_tuple = (self.repo_owner, self.repo_name, self.issue_id)

        # the unique text ID is not case-sensitive, so we just enforce lower-case to make them unique
        issue_text_id = "{}/{}#{}".format(*issue_tuple).lower()

        return issue_text_id


def parse_github_issue_ids(bot, data) -> List[GitHubIssue]:
    # this regex will just match any string, even if embedded in some other string
    # the idea is that when there's e.g., punctuation following an issue number, it will still trigger the
    # integration
    pattern = r"\s+([A-Za-z-_]+/)?([A-Za-z-_]+)?#([0-9]+)"

    # FIXME: workaround: the space in front of the data allows us to detect issues and PRs at the beginning of messages
    # the space we require in the pattern prevents false-positive matches within random strings, e.g., URLs with query
    # strings
    data = " " + data

    matches = re.findall(pattern, data)
    logger.debug("GitHub issue/PR matches: %r", matches)

    github_chat_monitor_config = bot.config.get("github_chat_monitor", dict())

    try:
        default_repo_owner = github_chat_monitor_config["default_repo_owner"]
        default_repo_name = github_chat_monitor_config["default_repo_name"]
    except KeyError:
        raise GitHubChatMonitorError("default repo owner and/or name not configured")

    # figure out account and repo for all issues to allow for deduplicating them before resolving
    issues: List[GitHubIssue] = []

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

        issues.append(GitHubIssue(repo_owner, repo_name, issue_id))

    return issues


def parse_github_urls(data) -> List[GitHubIssue]:
    matches = re.findall(r"(https://github.com/.+/.+/(?:issues|pull)/\d+[^\s#]+)", data)

    issues: List[GitHubIssue] = []

    for match in matches:
        url = urllib.parse.urlparse(match)
        if url.scheme != "https" or url.netloc != "github.com":
            continue

        path_fragments = url.path.split("/")
        if len(path_fragments) < 5:
            continue

        _, repo_owner, repo_name, _, issue_id = path_fragments[:5]
        issues.append(GitHubIssue(repo_owner, repo_name, issue_id))

    return issues


def deduplicate(issues: List[GitHubIssue]):
    issues_map: Dict[str, GitHubIssue] = {}

    for issue in issues:
        issues_map[str(issue)] = issue

    return list(issues_map.values())


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
        issues: List[GitHubIssue] = parse_github_issue_ids(bot, data) + parse_github_urls(data)

    except GitHubChatMonitorError as e:
        bot.notice(target, "Error: {}".format(str(e)))
        return

    except:
        message = "Unknown error while parsing GitHub issues"
        logger.exception(message)
        bot.notice(target, message)
        return

    issues = deduplicate(issues)
    logger.debug("deduplicated issues: %r", issues)

    for repo_owner, repo_name, issue_id in issues:
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

            continue

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
