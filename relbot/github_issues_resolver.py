import re
import string
import urllib.parse
from typing import NamedTuple, List, Dict

from relbot.util import make_logger


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


class GitHubIssuesResolver:
    def __init__(self, default_organization: str = None, default_repository: str = None, repository_aliases: dict = None):
        self._default_organization = default_organization
        self._default_repository = default_repository
        self._repository_aliases = repository_aliases

        self._logger = make_logger("GitHubIssuesResolver")

    def find_github_issue_ids(self, data) -> List[GitHubIssue]:
        # this regex will just match any string, even if embedded in some other string
        # the idea is that when there's e.g., punctuation following an issue number, it will still trigger the
        # integration
        pattern = r"\s+([A-Za-z-_]+/)?([A-Za-z-_]+)?#([0-9]+)"

        # FIXME: workaround: the space in front of the data allows us to detect issues and PRs at the beginning of messages
        # the space we require in the pattern prevents false-positive matches within random strings, e.g., URLs with query
        # strings
        data = " " + data

        matches = re.findall(pattern, data)
        self._logger.debug("GitHub issue/PR matches: %r", matches)

        # figure out account and repo for all issues to allow for deduplicating them before resolving
        issues: List[GitHubIssue] = []

        for organization, repository, issue_id in matches:
            # the regex might match an empty string, for some reason
            # in that case, we just set the default values
            if not organization:
                organization = self._default_organization

            if not repository:
                repository = self._default_repository

            # substitute short aliases with the actual repo name, if such aliases are configured
            for short_name, real_name in self._repository_aliases.items():
                if repository.lower() == short_name.lower():
                    repository = real_name
                    break

            # our match might contain at least one slash, so we need to get rid of that
            organization = organization.rstrip("/")

            def is_valid_name(s: str):
                for c in s:
                    if c not in string.ascii_letters + string.digits + "-_":
                        return False
                return True

            if not is_valid_name(organization) or not is_valid_name(repository):
                self._logger.warning("Invalid repository owner or name: %s/%s", organization, repository)
                continue

            if not issue_id.isdigit():
                self._logger.warning("Invalid issue ID: %s", issue_id)
                continue

            issues.append(GitHubIssue(organization, repository, issue_id))

        return issues

    @staticmethod
    def find_github_urls(data) -> List[GitHubIssue]:
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

    @staticmethod
    def deduplicate(issues: List[GitHubIssue]):
        issues_map: Dict[str, GitHubIssue] = {}

        for issue in issues:
            issues_map[str(issue)] = issue

        return list(issues_map.values())
