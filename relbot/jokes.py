import random


class JokesManager:
    def __init__(self, jokes_file: str):
        self.jokes_file = jokes_file

    def _load_jokes(self):
        with open(self.jokes_file, "r") as f:
            jokes = f.read().splitlines()

        return jokes

    def get_random(self):
        try:
            jokes = self._load_jokes()
        except IOError:
            return None
        else:
            return random.choice(jokes)

    def register_joke(self, joke: str):
        try:
            jokes = self._load_jokes()
        except IOError:
            jokes = []

        joke = joke.strip("\n\r \t")

        if joke in jokes:
            return

        with open(self.jokes_file, "a") as f:
            f.write("{}\n".format(joke))
