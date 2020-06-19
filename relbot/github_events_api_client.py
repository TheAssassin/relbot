import string
from collections import namedtuple
from typing import Iterator

from relbot.util import managed_proxied_session


class UnsupportedEventError(Exception):
    """
    Thrown whenever an event type is not supported or the specific payload format is not understood.
    """
    pass


def format_user_name(name):
    return "@" + name


def format_id(name):
    return "#" + str(name)


class GitHubEvent(namedtuple("GitHubEvent", ["id", "type", "actor", "repo", "date", "payload"])):
    @classmethod
    def from_json(cls, data: dict):
        # we can only handle supported types
        event_type = data["type"]

        payload_class = None

        if event_type == "PushEvent":
            payload_class = PushEventPayload

        elif event_type == "PullRequestEvent":
            payload_class = PullRequestEventPayload

        elif event_type == "CreateEvent":
            payload_class = CreateEventPayload

        elif event_type == "DeleteEvent":
            payload_class = DeleteEventPayload

        elif event_type == "IssuesEvent":
            payload_class = IssuesEventPayload

        elif event_type == "IssueCommentEvent":
            payload_class = IssueCommentEventPayload

        if payload_class is None:
            raise UnsupportedEventError()

        payload = data["payload"]

        event = GitHubEvent(
            data["id"],
            event_type,
            format_user_name(data["actor"]["display_login"]),
            data["repo"]["name"],
            data["created_at"],
            payload_class.from_json(payload),
        )

        return event

    def __str__(self):
        return "[{}] {} {}".format(self.repo, self.actor, str(self.payload))


class PushEventPayload(namedtuple("PushEventPayload", ["size", "ref"])):
    @classmethod
    def from_json(cls, data: dict):
        return cls(data["size"], data["ref"])

    def __str__(self):
        return "pushed {} commits to {}".format(self.size, self.ref)


class CreateEventPayload(namedtuple("CreateEventPayload", ["ref", "ref_type"])):
    @classmethod
    def from_json(cls, data: dict):
        return cls(data["ref"], data["ref_type"])

    def __str__(self):
        return "created {} {}".format(self.ref_type, self.ref)


class DeleteEventPayload(namedtuple("DeleteEventPayload", ["ref", "ref_type"])):
    @classmethod
    def from_json(cls, data: dict):
        return cls(data["ref"], data["ref_type"])

    def __str__(self):
        return "deleted {} {}".format(self.ref_type, self.ref)


class IssuesEventPayload(namedtuple("IssuesEventPayload", ["action", "number", "url", "title", "creator"])):
    SUPPORTED_ACTIONS = ["opened", "closed", "reopened"]

    @classmethod
    def from_json(cls, data: dict):
        action = data["action"]

        # we can safely ignore assignment and labelling events
        if action not in cls.SUPPORTED_ACTIONS:
            raise UnsupportedEventError()

        issue = data["issue"]

        return cls(action, format_id(issue["number"]), issue["html_url"], issue["title"], issue["user"]["login"])

    def __str__(self):
        data = self._asdict()

        assert self.action in self.SUPPORTED_ACTIONS

        if self.action == "opened":
            fmt = "opened issue {number}: {title} ({url})"
        else:
            fmt = "{action} issue {number}: {title} (opened by {creator}, {url}"

        return fmt.format(**data)


class IssueCommentEventPayload(namedtuple("IssueCommentEventPayload", ["number", "url", "title", "creator"])):
    @classmethod
    def from_json(cls, data: dict):
        if data["action"] != "created":
            raise UnsupportedEventError()

        issue = data["issue"]

        return cls(
            format_id(issue["number"]),
            issue["html_url"],
            issue["title"],
            issue["user"]["login"],
        )

    def __str__(self):
        fmt = "commented on issue {number}: {title} (opened by {creator}, {url})"
        return fmt.format(**self._asdict())


class PullRequestEventPayload(namedtuple("PullRequestEventPayload", ["action", "number", "url", "title", "creator", "merged", "merged_by"])):
    SUPPORTED_EVENTS = ["opened", "closed", "reopened"]

    @classmethod
    def from_json(cls, data: dict):
        pr = data["pull_request"]

        action = data["action"]

        if action not in cls.SUPPORTED_EVENTS:
            raise UnsupportedEventError()

        return cls(
            action,
            format_id(data["number"]),
            pr["html_url"],
            pr["title"],
            format_user_name(pr["user"]["login"]),
            pr["merged"],
            format_user_name(pr["merged_by"]["login"]),
        )

    def __str__(self):
        if self.action not in self.SUPPORTED_EVENTS:
            raise ValueError("unsupported action")

        data = self._asdict()

        if self.action == "closed":
            if self.merged:
                fmt = "merged pull request {number}: {title} (opened by {creator}, {url})"
            else:
                fmt = "closed pull request {number} without merging it: {title} (opened by {creator}, {url}"

        elif self.action == "opened":
            fmt = "{action} pull request {number}: {title} (opened by {creator}, {url})"

        else:
            fmt = "{action} pull request {number}: {title} ({url})"

        return fmt.format(**data)


class GithubEventsAPIClient:
    def __init__(self, organization: str):
        # sanity check to make handling the organization name a little easier
        for c in organization:
            assert c in (string.ascii_letters + string.digits + "-_")

        self.organization = organization

        # while the bot is running, we need to remember which messages we've reported already
        # therefore we store the ID of the last reported event
        # we assume that GitHub's API is sane enough to maintain those IDs in a monotonically increasing way
        # while set to <0, nothing should be reported
        self.last_reported_id = -1

        # we store the ETag header so we can send it as If-None-Match to the API endpoint
        # this may then return a 304 No Modified response and doesn't trigger the API limits
        # this way, we can poll somewhat safely every minute
        self.last_modified = None

    def _fetch_data(self) -> dict:
        url = "https://api.github.com/orgs/%s/events" % self.organization

        with managed_proxied_session() as session:
            headers = {}

            if self.last_modified:
                headers["if-modified-since"] = self.last_modified

            response = session.get(url, allow_redirects=True, headers=headers)

        response.raise_for_status()

        if response.status_code == 304:
            return {}

        self.last_modified = response.headers["last-modified"]

        data = response.json()
        return data

    def setup(self):
        """
        Calls GitHub API once initially. The instance remembers which messages were existing at this point, and will
        return only events newer than that.
        """

        data = self._fetch_data()

        initial_event = data[0]
        initial_id = int(initial_event["id"])

        self.last_reported_id = initial_id

    @staticmethod
    def _parse_push_event(payload: dict):
        return PushEventPayload(payload["size"], payload["ref"])

    def fetch_new_events(self) -> Iterator[GitHubEvent]:
        assert self.last_reported_id > 0, "events have never been checked before -- forgot to call setup()?"

        data = self._fetch_data()

        for entry in data:
            try:
                event = GitHubEvent.from_json(entry)

            # we just ignore all events we don't understand
            except UnsupportedEventError:
                continue

            yield event


if __name__ == "__main__":
    client = GithubEventsAPIClient("blue-nebula")

    # for debugging we print all events we can possibly get
    client.last_reported_id = 1

    lines = [str(i) for i in client.fetch_new_events()]
    lines.reverse()

    print("\n".join(lines))

    # check whether the if-modified-since thing works
    assert not list(client.fetch_new_events())