from typing import List, Union

import requests


class Player:
    def __init__(self):
        self.color: Union[str, None] = None
        self.privilege: Union[str, None] = None
        self.team_color: Union[str, None] = None
        self.name: Union[str, None] = None
        self.account: Union[str, None] = None

    @staticmethod
    def from_dict(data: dict) -> "Player":
        player = Player()

        for k, v in data.items():
            setattr(player, k, v)

        return player


class Server:
    def __init__(self):
        self.hostname: Union[str, None] = None
        self.port: Union[int, None] = None
        self.priority: Union[int, None] = None
        self.flags: Union[List[str], None] = None
        self.country: Union[str, None] = None
        self.players_count: Union[int, None] = None
        self.protocol: Union[str, None] = None
        self.game_mode: Union[str, None] = None
        self.mutators: Union[List[str], None] = None
        self.time_remaining: Union[int, None] = None
        self.max_slots: Union[int, None] = None
        self.mastermode: Union[str, None] = None
        self.modification_percentage: Union[int, None] = None
        self.number_of_game_vars: Union[int, None] = None
        self.version: Union[int, None] = None
        self.version_platform: Union[int, None] = None
        self.version_arch: Union[int, None] = None
        self.game_state: Union[int, None] = None
        self.time_left: Union[int, None] = None
        self.map_name: Union[str, None] = None
        self.map_screenshot: Union[str, None] = None
        self.description: Union[str, None] = None
        self.players: Union[List[Player], None] = None

    @staticmethod
    def from_dict(data: dict) -> "Server":
        # replace players in dict with Player objects
        data["players"] = [Player.from_dict(p) for p in data["players"]]

        server = Server()

        for k, v in data.items():
            setattr(server, k, v)

        return server


class RedflareClient:
    def __init__(self, redflare_url: str):
        self._redflare_api_url = redflare_url + "/api/"

    def servers(self):
        url = self._redflare_api_url + "servers.json"

        response = requests.get(url)
        response.raise_for_status()

        servers = response.json()["servers"]

        return [Server.from_dict(s) for s in servers]
