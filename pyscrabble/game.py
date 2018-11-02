from enum import Enum
from queue import Queue
from threading import Lock, Thread
from typing import List

import pyscrabble.protocol as protocol
from pyscrabble.network import Stream, StreamWorker


class Tile:
    def __init__(self, tile_id: int, points: int, letter: str):
        self.id = tile_id
        self.points = points
        self.letter = letter


class Player:
    def __init__(self, name: str, queue: Queue):
        self.name = name
        self.score = 0
        self.tiles: List[Tile] = []
        self.queue = queue

    def reset(self):
        self.score = 0
        self.tiles.clear()


class SquareType(Enum):
    NORMAL = 'N'
    DLS = 'DLS'
    TLS = 'TLS'
    DWS = 'DWS'
    TWS = 'TWS'


class Square:
    def __init__(self, square_type: SquareType):
        self.type = square_type
        self.tile: Tile = None


class Board:
    __layout = ([SquareType(t) for t in row.split()] for row in [
        'TWS  N   N  DLS  N   N   N  TWS',
        ' N  DWS  N   N   N  TLS  N   N',
        ' N   N  DWS  N   N   N  DLS  N',
        'DLS  N   N  DWS  N   N   N  DLS',
        ' N   N   N   N  DWS  N   N   N',
        ' N  TLS  N   N   N  TLS  N   N',
        ' N   N  DLS  N   N   N  DLS  N',
        'TWS  N   N  DLS  N   N   N  DWS'
    ])
    __layout = [row + row[-2::-1] for row in __layout]
    __layout += __layout[-2::-1]

    def __init__(self):
        self.__squares = [[Square(t) for t in row] for row in Board.__layout]

    def __getitem__(self, item):
        return self.__squares[item]


class Game:
    def __init__(self):
        self.players = {i: None for i in range(4)}
        self.players_lock = Lock()
        self.queue = Queue()

        self.board: Board = None

    def start(self):
        self.board = Board()

    def handle_connection(self, stream: Stream):
        self.players_lock.acquire()
        free_slot = next((i for i in self.players.keys() if self.players[i] is None), None)
        if not free_slot:
            self.players_lock.release()
            stream.send_message(protocol.ActionRejected('Server is full'))
            stream.close()
        else:
            msg = stream.get_msg()
            if isinstance(msg, protocol.Join):
                worker = StreamWorker(stream, self.queue)
                player = Player(msg.name, worker.queue)
                self.players[free_slot] = player
                self.players_lock.release()
                Thread(target=worker.listen_incoming()).start()
                worker.listen_outgoing()
