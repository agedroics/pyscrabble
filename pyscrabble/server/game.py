import random
from queue import Queue
from threading import Lock
from typing import List


class Game:
    def __init__(self):
        self.board: 'Board' = None
        self.free_tiles: List['Tile'] = None
        self.clients: List['Client'] = []
        self.clients_lock = Lock()
        self.lobby = True
        self.turn_player_id: int = None
        self.queue_in = Queue()

    def find_free_player_id(self) -> int:
        taken_ids = set((client.player_id for client in self.clients))
        free_ids = (i for i in range(256) if i not in taken_ids)
        return next(free_ids)

    def send_to_all(self, msg: 'ServerMessage', exception_id: int = None):
        for client in self.clients:
            if exception_id != client.player_id:
                client.worker.queue_out.put(msg)

    def load_tiles(self):
        self.free_tiles = random.shuffle([Tile(i, i, chr(i)) for i in range(65, 91)])

    def process_incoming_requests(self):
        while True:
            msg, client = self.queue_in.get()
            Handler.handle(msg, client, self)


from pyscrabble.server.handler import Handler
from pyscrabble.common.model import Board, Tile
from pyscrabble.common.protocol import ServerMessage
from pyscrabble.server.server import Client
