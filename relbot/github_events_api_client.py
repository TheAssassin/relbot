import string
from collections import namedtuple
from typing import Iterator, List

from relbot.util import managed_proxied_session, make_logger


class UnsupportedEventError(Exception):
    """
    Thrown whenever an event type is not supported or the specific payload format is not understood.
    """

    def __init__(self, event_type: str):
        self.event_type = event_type

    def __str__(self):
        return "Unsupported event: {}".format(self.event_type)


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

        elif event_type == "ReleaseEvent":
            payload_class = ReleaseEvent

        if payload_class is None:
            raise UnsupportedEventError(event_type)

        payload = data["payload"]
        
        # needed for create events
        repo = data.get("repo", None)

        event = GitHubEvent(
            int(data["id"]),
            event_type,
            format_user_name(data["actor"]["display_login"]),
            data["repo"]["name"],
            data["created_at"],
            payload_class.from_json(payload, repo),
        )

        return event

    def __str__(self):
        return "[{}] {} {}".format(self.repo, self.actor, str(self.payload))


class PushEventPayload(namedtuple("PushEventPayload", ["size", "ref"])):
    @classmethod
    def from_json(cls, data: dict, repo: dict):
        return cls(data["size"], data["ref"])

    def __str__(self):
        return "pushed {} commits to {}".format(self.size, self.ref)


class CreateEventPayload(namedtuple("CreateEventPayload", ["ref", "ref_type"])):
    @classmethod
    def from_json(cls, data: dict, repo: dict):
        ref_type = data["ref_type"]

        ref = data["ref"]

        if not ref:
            ref = repo["name"]

        return cls(ref, ref_type)

    def __str__(self):
        return "created {} {}".format(self.ref_type, self.ref)


class DeleteEventPayload(namedtuple("DeleteEventPayload", ["ref", "ref_type"])):
    @classmethod
    def from_json(cls, data: dict, repo: dict):
        return cls(data["ref"], data["ref_type"])

    def __str__(self):
        return "deleted {} {}".format(self.ref_type, self.ref)


class IssuesEventPayload(namedtuple("IssuesEventPayload", ["action", "number", "url", "title", "creator"])):
    SUPPORTED_ACTIONS = ["opened", "closed", "reopened"]

    @classmethod
    def from_json(cls, data: dict, repo: dict):
        action = data["action"]

        # we can safely ignore assignment and labelling events
        if action not in cls.SUPPORTED_ACTIONS:
            raise UnsupportedEventError()

        issue = data["issue"]

        return cls(
            action,
            format_id(issue["number"]),
            issue["html_url"],
            issue["title"],
            format_user_name(issue["user"]["login"]),
        )

    def __str__(self):
        data = self._asdict()

        assert self.action in self.SUPPORTED_ACTIONS

        if self.action == "opened":
            fmt = "opened issue {number}: {title} ({url})"
        else:
            fmt = "{action} issue {number}: {title} (opened by {creator}, {url}"

        return fmt.format(**data)


class IssueCommentEventPayload(namedtuple("IssueCommentEventPayload", ["number", "url", "title", "creator", "type"])):
    @classmethod
    def from_json(cls, data: dict, repo: dict):
        if data["action"] != "created":
            raise UnsupportedEventError(data["action"])

        issue = data["issue"]

        if issue.get("pull_request", None):
            type_ = "pull request"
        else:
            type_ = "issue"

        return cls(
            format_id(issue["number"]),
            issue["html_url"],
            issue["title"],
            format_user_name(issue["user"]["login"]),
            type_
        )

    def __str__(self):
        fmt = "commented on {type} {number}: {title} (opened by {creator}, {url})"
        return fmt.format(**self._asdict())


class ReleaseEvent(namedtuple("ReleaseEvent", ["action", "release_name", "repo_name", "creator", "url", "prerelease"])):
    @classmethod
    def from_json(cls, data: dict, repo: dict):
        release = data["release"]

        return cls(
            data["action"],
            release["name"],
            repo["name"],
            format_user_name(release["author"]["login"]),
            release["html_url"],
            release["prerelease"],
        )

    def __str__(self):
        fmt = "{action} {type} in repository {repo_name}: {release_name} (created by {creator}, {url})"

        type_ = "release"

        if self.prerelease:
            type_ = "prerelease"

        return fmt.format(type=type_, **self._asdict())


class PullRequestEventPayload(namedtuple("PullRequestEventPayload", ["action", "number", "url", "title", "creator", "merged", "merged_by"])):
    SUPPORTED_EVENTS = ["opened", "closed", "reopened"]

    @classmethod
    def from_json(cls, data: dict, repo: dict):
        pr = data["pull_request"]

        action = data["action"]

        if action not in cls.SUPPORTED_EVENTS:
            raise UnsupportedEventError()

        try:
            merged_by = format_user_name(pr["merged_by"]["login"])
        except TypeError:
            merged_by = None

        return cls(
            action,
            format_id(data["number"]),
            pr["html_url"],
            pr["title"],
            format_user_name(pr["user"]["login"]),
            pr["merged"],
            merged_by,
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
        self.logger = make_logger("GitHubEventsAPIClient")

        # sanity check to make handling the organization name a little easier
        for c in organization:
            assert c in (string.ascii_letters + string.digits + "-_")

        self.organization = organization

        # while the bot is running, we need to remember which messages we've reported already
        # therefore we store the ID of the last reported event
        # we assume that GitHub's API is sane enough to maintain those IDs in a monotonically increasing way
        # while set to <0, nothing should be reported
        self.last_reported_id = -1

        # we store the last response
        # the client can use it to check whether anything has changed, and if this is not the case return the cached
        # data
        self.cached_response = None

    def fetch_events(self) -> List[GitHubEvent]:
        url = "https://api.github.com/orgs/%s/events" % self.organization

        with managed_proxied_session() as session:
            headers = {}

            # we use the last-modified header of the cached response to avoid running into API rate limits
            # that way, we save responses as long as nothing has changed, as GitHub will return a 304 response
            # this way, we can poll somewhat safely every minute
            if self.cached_response:
                for header in ["last-modified", "retry-after", "date"]:
                    try:
                        headers["if-modified-since"] = self.cached_response.headers[header]

                    except KeyError:
                        self.logger.warning("cached response did not contain header %s, trying next", header)

                    else:
                        break

                else:
                    self.logger.error(
                        "cached response did contain any header we could use for if-modified-since, "
                        "will likely run into rate limit"
                    )

            response = session.get(url, allow_redirects=True, headers=headers)

        response.raise_for_status()

        if response.status_code == 304:
            self.logger.info("using cached response")
            response = self.cached_response

        elif response.status_code == 200:
            self.cached_response = response

        else:
            raise ValueError("invalid response status code %d" % response.status_code)

        self.logger.info(
            "GitHub API limit: %s/%s",
            response.headers["X-RateLimit-Remaining"],
            response.headers["X-RateLimit-Limit"]
        )

        data = response.json()

        events = []

        for entry in data:
            try:
                event = GitHubEvent.from_json(entry)

            # we just ignore all events we don't understand
            except UnsupportedEventError as e:
                self.logger.debug(str(e))
                continue

            except:  # noqa
                self.logger.exception("Failed to parse event (unknown error), skipping")

            else:
                events.append(event)

        # make sure the events are sorted in a descending order (this is how GitHub returns them by default)
        events.sort(key=lambda i: i.id, reverse=True)

        # sanity check (of course, this only works with 2+ events)
        if len(events) > 2:
            assert events[0].id > events[1].id

        return events

    def setup(self):
        """
        Calls GitHub API once initially. The instance remembers which messages were existing at this point, and will
        return only events newer than that.
        """

        events = self.fetch_events()

        # make sure fetch_new_events ignores all events which happened up to this point
        try:
            initial_event = events[0]
            self.last_reported_id = int(initial_event.id)

        except IndexError:
            self.last_reported_id = 0

    def fetch_new_events(self) -> Iterator[GitHubEvent]:
        assert int(self.last_reported_id) >= 0, "events have never been checked before -- forgot to call setup()?"

        # we need to make sure all entries are sorted properly
        events = self.fetch_events()

        for event in events:
            if int(event.id) <= int(self.last_reported_id):
                break

            yield event

        # events might be an empty list
        if events:
            self.last_reported_id = int(events[0].id)


if __name__ == "__main__":
    client = GithubEventsAPIClient("blue-nebula")

    # for debugging we print all events we can possibly get
    client.last_reported_id = 1

    events = client.fetch_events()

    print("\n".join([str(e) for e in events]))

    # try to fetch last event again by convincing the bot it has reported each event but the last one
    if events:
        client.last_reported_id = events[1].id

        new_events = list(client.fetch_new_events())
        assert len(new_events) == 1

        # check whether the if-modified-since thing works
        assert not list(client.fetch_new_events())

    else:
        print("cannot run checks: no events available")
