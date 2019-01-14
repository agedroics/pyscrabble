from queue import Queue
from threading import Lock
from typing import Any, Dict, Callable, Optional


class Game:
    def __init__(self, on_update: Callable[['proto.ServerMessage', Optional[str]], Any]):
        self.board: 'Board' = None
        self.tiles_left: int = None
        self.clients: Dict[int, 'Client'] = {}
        self.lock = Lock()
        self.lobby = True
        self.player_client: 'Client' = None
        self.player_turn: bool = None
        self.queue_in = Queue()
        self.on_update = on_update
        self.player_id_turn: int = None

    def process_incoming_messages(self):
        while True:
            msg, = self.queue_in.get()
            Handler.handle(msg, self)
            if not msg or isinstance(msg, proto.Shutdown):
                break


from pyscrabble.client.connection import Client
from pyscrabble.client.handler import Handler
from pyscrabble.common.model import Board

import pyscrabble.common.protocol as proto
