import gzip
import random
from abc import ABC
from queue import Queue
from socket import socket, AF_INET, SOCK_STREAM
from threading import Thread, Lock
from typing import List, Set, Tuple, Dict, Type, Optional

from pkg_resources import resource_stream

import pyscrabble.protocol as proto
from pyscrabble.model import Player, Board, Tile

words: Set[str] = None


def load_words():
    global words
    if not words:
        with resource_stream(__name__, 'words') as stream:
            with gzip.open(stream, mode='rt') as f:
                words = set(line.strip() for line in f)
        words.remove('')


class Client:
    def __init__(self, player_id: int, name: str, stream: 'proto.Stream', queue_in: Queue):
        self.player_id = player_id
        self.name = name
        self.player: Player = None
        self.ready = False
        self.worker = proto.StreamWorker(stream, queue_in, self)


class Server:
    def __init__(self):
        self.__socket: socket = None
        self.game = Game()

    def __handle_connection(self, stream: 'proto.Stream'):
        msg = stream.get_msg()
        if isinstance(msg, proto.Join):
            self.game.clients_lock.acquire()
            if len(self.game.clients) == 4:
                self.game.clients_lock.release()
                stream.send_msg(proto.ActionRejected('Server is full'))
                stream.close()
            elif not self.game.lobby:
                self.game.clients_lock.release()
                stream.send_msg(proto.ActionRejected('Game in progress'))
                stream.close()
            else:
                free_id = self.game.find_free_player_id()
                new_client = Client(free_id, msg.name, stream, self.game.queue_in)
                self.game.clients.append(new_client)

                player_infos = []
                player_joined = proto.PlayerJoined(free_id, new_client.name)
                for client in self.game.clients:
                    player_infos.append(proto.PlayerInfo(client.player_id, client.ready, client.name))
                    if client != new_client:
                        client.worker.queue_out.put(player_joined)
                new_client.worker.queue_out.put(proto.JoinOk(free_id, player_infos))
                self.game.clients_lock.release()

                Thread(target=new_client.worker.listen_incoming, daemon=True).start()
                new_client.worker.listen_outgoing()
        else:
            stream.close()

    def __listen_connections(self):
        try:
            while True:
                s, _ = self.__socket.accept()
                Thread(target=self.__handle_connection, args=(proto.Stream(s, proto.ClientMessage),), daemon=True).start()
        except IOError:
            pass

    def start(self, ip: str, port: int):
        if self.__socket is None:
            self.__socket = socket(AF_INET, SOCK_STREAM)
            self.__socket.bind((ip, port))
            self.__socket.listen(1)
            load_words()
            Thread(target=self.__listen_connections, daemon=True).start()
            Thread(target=self.game.process_incoming_requests, daemon=True).start()

    def stop(self):
        self.game.send_to_all(proto.Shutdown())
        self.game.queue_in.put((None, None))
        self.__socket.close()


class Game:
    _tiles: List[Tuple[str, int]] = [
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
    _tiles = [Tile(tile_id, points, letter) for tile_id, (letter, points) in enumerate(_tiles)]

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


class Handler(ABC):
    @staticmethod
    def handle(msg: Optional['proto.ClientMessage'], client: 'Client', game: 'Game'):
        handler = Handler._mappings.get(msg.__class__) if msg else LeaveHandler
        if handler:
            with game.clients_lock:
                handler._handle(msg, client, game)

    @classmethod
    def _handle(cls, msg: 'proto.ClientMessage', client: 'Client', game: 'Game'):
        pass


def _start_game(game: 'Game'):
    game.board = Board()
    game.load_tiles()
    game.lobby = False
    game.turns_without_score = 0
    for client in game.clients:
        client.ready = False
        player = client.player = Player()
        player.tiles = game.free_tiles[:7]
        game.free_tiles = game.free_tiles[7:]
    game.send_to_all(proto.Notification('Game started!'))
    game.turn_player_id = game.clients[random.randint(0, len(game.clients) - 1)].player_id
    tiles_left = len(game.free_tiles)
    for client in game.clients:
        start_turn = proto.StartTurn(game.turn_player_id, tiles_left, client.player.tiles)
        client.worker.queue_out.put(start_turn)


def _end_game(game: 'Game'):
    game.lobby = True
    for client in game.clients:
        client.player.score -= sum(tile.points for tile in client.player.tiles)
    end_game = proto.EndGame([proto.EndGamePlayer(client.player_id, client.player.score) for client in game.clients])
    game.send_to_all(end_game)


class ReadyHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.Ready', client: 'Client', game: 'Game'):
        if game.lobby:
            client.ready = not client.ready
            all_ready = len(game.clients) > 1 and all(client.ready for client in game.clients)
            if all_ready:
                _start_game(game)
            else:
                game.send_to_all(proto.PlayerReady(client.player_id))


class LeaveHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.Leave', client: 'Client', game: 'Game'):
        i = game.clients.index(client)
        del game.clients[i]
        game.send_to_all(proto.PlayerLeft(client.player_id))
        if game.lobby:
            all_ready = len(game.clients) > 1 and all(client.ready for client in game.clients)
            if all_ready:
                _start_game(game)
        elif len(game.clients) < 2:
            _end_game(game)
        elif game.turn_player_id == client.player_id:
            game.turn_player_id = game.clients[i % len(game.clients)].player_id
            tiles_left = len(game.free_tiles)
            for client_ in game.clients:
                start_turn = proto.StartTurn(game.turn_player_id, tiles_left, client_.player.tiles)
                client_.worker.queue_out.put(start_turn)


class TileExchangeHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.TileExchange', client: 'Client', game: 'Game'):
        tiles_left = len(game.free_tiles)
        if tiles_left < 7:
            client.worker.queue_out.put(proto.ActionRejected('There are less than 7 tiles left!'))
        elif game.turn_player_id != client.player_id:
            client.worker.queue_out.put(proto.ActionRejected('Not player\'s turn!'))
        elif not msg.tile_ids:
            client.worker.queue_out.put(proto.ActionRejected('Tile exchange requires at least one selected tile!'))
        else:
            tiles = [tile for tile in client.player.tiles if tile.id in msg.tile_ids]
            tile_count = len(tiles)
            if len(msg.tile_ids) == tile_count:
                client.player.tiles = [tile for tile in client.player.tiles if tile not in tiles]
                game.free_tiles += tiles
                random.shuffle(game.free_tiles)
                client.player.tiles += game.free_tiles[:tile_count]
                game.free_tiles = game.free_tiles[tile_count:]
                if game.turns_without_score == 5:
                    _end_game(game)
                    game.send_to_all(proto.Notification('Game has reached 6 consecutive turns without scoring!'))
                else:
                    game.turns_without_score += 1
                    game.send_to_all(proto.EndTurn(game.turn_player_id, client.player.score, []))
                    game.turn_player_id = game.clients[(game.clients.index(client) + 1) % len(game.clients)].player_id
                    for client_ in game.clients:
                        start_turn = proto.StartTurn(game.turn_player_id, tiles_left, client_.player.tiles)
                        client_.worker.queue_out.put(start_turn)
            else:
                client.worker.queue_out.put(proto.ActionRejected('Selected tiles do not belong to player!'))


class PlaceTilesHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.PlaceTiles', client: 'Client', game: 'Game'):
        ...


class ChatHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.Chat', client: 'Client', game: 'Game'):
        game.send_to_all(proto.PlayerChat(client.player_id, msg.text))


Handler._mappings: Dict[Type['proto.ClientMessage'], Type['Handler']] = {
    proto.Ready: ReadyHandler,
    proto.Leave: LeaveHandler,
    proto.TileExchange: TileExchangeHandler,
    proto.PlaceTiles: PlaceTilesHandler,
    proto.Chat: ChatHandler
}
