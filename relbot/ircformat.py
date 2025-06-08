"""
IRC formatting based on https://modern.ircdocs.horse/formatting.
"""


from enum import IntEnum


class Color(IntEnum):
    WHITE = 0
    BLACK = 1
    BLUE = 2
    GREEN = 3
    RED = 4
    BROWN = 5
    MAGENTA = 6
    ORANGE = 7
    YELLOW = 8
    LIGHT_GREEN = 9
    CYAN = 10
    LIGHT_CYAN = 11
    LIGHT_BLUE = 12
    PINK = 13
    GREY = 14
    LIGHT_GREY = 15

    def to_string(self):
        return f"\x03{str(self.value).zfill(2)}"


RESET = "\x0F"


def format_text(text: str, color: Color | None):
    if color is None:
        return text

    return f"{color.to_string()}{text}{RESET}"
