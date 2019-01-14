import gzip
import random
from queue import Queue
from threading import Lock
from typing import List, Tuple, Set

from pkg_resources import resource_stream


class Game:
    def __init__(self):
        self.board: 'Board' = None
        self.free_tiles: List['Tile'] = None
        self.clients: List['Client'] = []
        self.clients_lock = Lock()
        self.lobby = True
        self.turn_player_id: int = None
        self.queue_in = Queue()
        self.turns_without_score: int = None

    def find_free_player_id(self) -> int:
        taken_ids = set((client.player_id for client in self.clients))
        free_ids = (i for i in range(256) if i not in taken_ids)
        return next(free_ids)

    def send_to_all(self, msg: 'proto.ServerMessage', exception_id: int = None):
        for client in self.clients:
            if exception_id != client.player_id:
                client.worker.queue_out.put(msg)

    def load_tiles(self):
        self.free_tiles = Game._tiles.copy()
        random.shuffle(self.free_tiles)

    def process_incoming_requests(self):
        while True:
            msg, client = self.queue_in.get()
            if client:
                Handler.handle(msg, client, self)
            else:
                break


from pyscrabble.server.handler import Handler
from pyscrabble.common.model import Board, Tile
from pyscrabble.server.server import Client

import pyscrabble.common.protocol as proto

Game._tiles: List[Tuple[str, int]] = [
    *2 * [(None, 0)],

    *12 * [('E', 1)],
    *9 * [('A', 1)],
    *9 * [('I', 1)],
    *8 * [('O', 1)],
    *6 * [('N', 1)],
    *6 * [('R', 1)],
    *6 * [('T', 1)],
    *4 * [('L', 1)],
    *4 * [('S', 1)],
    *4 * [('U', 1)],

    *4 * [('D', 2)],
    *3 * [('G', 2)],

    *2 * [('B', 3)],
    *2 * [('C', 3)],
    *2 * [('M', 3)],
    *2 * [('P', 3)],

    *2 * [('F', 4)],
    *2 * [('H', 4)],
    *2 * [('V', 4)],
    *2 * [('W', 4)],
    *2 * [('Y', 4)],

    ('K', 5),

    ('J', 8),
    ('X', 8),

    ('Q', 10),
    ('Z', 10)
]
Game._tiles = [Tile(tile_id, points, letter) for tile_id, (letter, points) in enumerate(Game._tiles)]

words: Set[str] = None


def load_words():
    global words
    if not words:
        with resource_stream(__name__, 'words') as stream:
            with gzip.open(stream, mode='rt') as f:
                words = set(line.strip() for line in f)
        words.remove('')
