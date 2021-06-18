# relbot

A modular IRC bot, written in Python using asyncio.


## Background

relbot's origins are in the [Blue Nebula](https://blue-nebula.org) community. It provides various services to the project's IRC channels. Due to its modular nature, it can (and is) also used in other communities (most notably [NewPipe](https://newpipe.net)).

Blue Nebula's working title in the first days of the fork was "Red Eclipse Legacy", whose abbreviation is "REL". Hence, the bot is called `relbot`.


## Features (and related commands)

- `!ud`: [UrbanDictionary](https://urbandictionary.com) search integration
- `!wiki`: [Wikipedia](https://en.wikipedia.org) search integration
- GitHub integration
    - monitor channels' messages for bits that look like GitHub issues or PRs and provide links to them (e.g., `my/repo#123`)
    - forward actions made on GitHub on IRC through notifications (events feed)
- Blue Nebula specific
    - `!matches`: check for running Blue Nebula matches (powered by [Blueflare](https://github.com/TheAssassin/blueflare)).
    - `!rivalry`: counts players on all servers by the version they play, and compares the total counts (friendly competition with Red Eclipse 2)
- `!chuck`: Chuck Norris joke integration (powered by [Internet Chuck Norris Database](https://icndb.com))
- `!joke`: Code joke integration (uses its own database, jokes can be registered by authorized persons using `!register-joke`)
- `!cookie`: Give cookies to people from a virtual jar

There might be additional features, as this list is only updated occasionally. Use `!help` for an up-to-date list.
