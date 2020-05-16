class StdoutHandler:
    formatters = {
        "privmsg": "{date:%H:%M:%S} {channel} <{mask.nick}> {data}",
        "join": "{date:%H:%M:%S} {mask.nick} joined {channel}",
        "part": "{date:%H:%M:%S} {mask.nick} has left {channel} ({data})",
        "quit": "{date:%H:%M:%S} {mask.nick} has quit ({data})",
        "topic": "{date:%H:%M:%S} {mask.nick} has set topic to: {data}",
    }

    def __init__(self, bot):
        self.encoding = bot.encoding
        self.formatters = bot.config.get(
            __name__ + ".formatters",
            self.formatters
        )

    def __call__(self, event):
        fmt = self.formatters.get(event["event"].lower())
        
        if fmt:
            print(fmt.format(**event))
