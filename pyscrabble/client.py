import socket
from abc import ABC
from queue import Queue
from threading import Lock, Thread
from typing import Any, Dict, Callable, Optional, Type

import pyscrabble.protocol as proto
from pyscrabble.model import Board, Player, Tile


class Client:
    def __init__(self, player_id: int, name: str, ready: bool = False):
        self.player_id = player_id
        self.name = name
        self.player: 'Player' = None
        self.ready = ready


class Connection:
    def __init__(self, on_update: Callable[['proto.ServerMessage', Optional[str]], Any]):
        self.__stream: 'proto.Stream' = None
        self.worker: 'proto.StreamWorker' = None
        self.game = Game(on_update)

    def start(self, ip: str, port: int, name: str):
        if not self.__stream:
            self.__stream = proto.Stream(socket.create_connection((ip, port)), proto.ServerMessage)
            self.worker = proto.StreamWorker(self.__stream, self.game.queue_in)
            self.worker.queue_out.put(proto.Join(name))
            Thread(target=self.worker.listen_incoming, daemon=True).start()
            Thread(target=self.worker.listen_outgoing, daemon=True).start()
            Thread(target=self.game.process_incoming_messages, daemon=True).start()

    def stop(self):
        self.worker.queue_out.put(proto.Leave())
        self.game.queue_in.put((None,))


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


class Handler(ABC):
    @staticmethod
    def handle(msg: Optional['proto.ServerMessage'], game: 'Game'):
        if not msg:
            msg = proto.Shutdown()
        handler = Handler._mappings.get(msg.__class__)
        text = None
        if handler:
            with game.lock:
                text = handler._handle(msg, game)
        game.on_update(msg, text)

    @classmethod
    def _handle(cls, msg: 'proto.ServerMessage', game: 'Game') -> Optional[str]:
        pass


class JoinOkHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.JoinOk', game: 'Game') -> None:
        for player in msg.players:
            client = Client(player.player_id, player.name, player.ready)
            game.clients[player.player_id] = client
            if msg.player_id == client.player_id:
                game.player_client = client


class ActionRejectedHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.ActionRejected', game: 'Game') -> None:
        pass


class PlayerJoinedHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.PlayerJoined', game: 'Game') -> str:
        client = Client(msg.player_id, msg.name)
        game.clients[msg.player_id] = client
        return f'{msg.name} has joined'


class PlayerLeftHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.PlayerLeft', game: 'Game') -> str:
        client = game.clients[msg.player_id]
        del game.clients[msg.player_id]
        return f'{client.name} has left'


class PlayerReadyHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.PlayerReady', game: 'Game') -> None:
        client = game.clients[msg.player_id]
        client.ready = not client.ready


class StartTurnHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.StartTurn', game: 'Game') -> str:
        if game.lobby:
            game.lobby = False
            game.board = Board()
            for client in game.clients.values():
                client.player = Player()
        client = game.clients[msg.player_id]
        game.player_turn = client == game.player_client
        game.player_id_turn = msg.player_id
        game.tiles_left = msg.tiles_left
        game.player_client.player.tiles = msg.tiles
        return ('Your' if game.player_turn else f'{client.name}\'s') + ' turn!'


class EndTurnHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.EndTurn', game: 'Game') -> Optional[str]:
        client = game.clients[msg.player_id]
        score_gained = msg.score - client.player.score
        client.player.score = msg.score
        for placed_tile in msg.placed_tiles:
            tile = Tile(None, placed_tile.points, placed_tile.letter)
            game.board[placed_tile.position].tile = tile
        if score_gained:
            return f'{"You" if game.player_turn else client.name} earned {score_gained} points'
        else:
            return f'{"You" if game.player_turn else client.name} skipped'


class EndGameHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.EndGame', game: 'Game') -> str:
        game.lobby = True
        for client in game.clients.values():
            client.ready = False
        msg.players.sort(key=lambda player: player.score, reverse=True)
        return 'Game over!' + ''.join(f'\n{game.clients[player.player_id].name} -> {player.score} points'
                                      for player in msg.players)


class PlayerChatHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.PlayerChat', game: 'Game') -> str:
        return f'{game.clients[msg.player_id].name}: {msg.text}'


class NotificationHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.Notification', game: 'Game') -> str:
        return f'{msg.text}'


Handler._mappings: Dict[Type['proto.ServerMessage'], Type['Handler']] = {
    proto.JoinOk: JoinOkHandler,
    proto.ActionRejected: ActionRejectedHandler,
    proto.PlayerJoined: PlayerJoinedHandler,
    proto.PlayerLeft: PlayerLeftHandler,
    proto.PlayerReady: PlayerReadyHandler,
    proto.StartTurn: StartTurnHandler,
    proto.EndTurn: EndTurnHandler,
    proto.EndGame: EndGameHandler,
    proto.PlayerChat: PlayerChatHandler,
    proto.Notification: NotificationHandler
}
