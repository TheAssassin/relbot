FROM python:3-alpine

RUN apk add libxml2-dev libxslt-dev gcc musl-dev

# run as non-root user
RUN adduser -S app
USER app

WORKDIR /app

COPY pyproject.toml poetry.lock .
COPY relbot/ relbot/

RUN pip install .

# stores config.ini, jokes.txt etc.
VOLUME /app/data
# therefore, we start the bot from there
WORKDIR /app/data

CMD ["python", "-m", "irc3", "config.ini"]
