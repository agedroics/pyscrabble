from abc import ABC
from typing import Dict, Type, Optional


class Handler(ABC):
    @staticmethod
    def handle(msg: Optional['proto.ServerMessage'], game: 'Game'):
        handler = Handler._mappings.get(msg.__class__) if msg else ShutdownHandler
        if handler:
            with game.lock:
                text = handler._handle(msg, game)
            game.on_update(msg.__class__ if msg else proto.Shutdown, text)

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
    def _handle(cls, msg: 'proto.ActionRejected', game: 'Game') -> str:
        return msg.reason


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
        game.tiles_left = msg.tiles_left
        game.player_client.player.tiles = msg.tiles
        return f'{client.name}\'s turn'


class EndTurnHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.EndTurn', game: 'Game') -> str:
        client = game.clients[msg.player_id]
        score_gained = msg.score - client.player.score
        client.player.score = msg.score
        for placed_tile in msg.placed_tiles:
            tile = Tile(None, placed_tile.points, placed_tile.letter)
            game.board[placed_tile.position].tile = tile
        return f'{client.name} earned {score_gained} points'


class EndGameHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.EndGame', game: 'Game') -> str:
        game.lobby = True
        msg.players.sort(lambda player: player.score, True)
        return '\n'.join(f'{game.clients[player.player_id].name}: {player.score}' for player in msg.players)


class ShutdownHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.Shutdown', game: 'Game') -> None:
        pass


class PlayerChatHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.PlayerChat', game: 'Game') -> str:
        return f'{game.clients[msg.player_id].name}: {msg.text}'


class NotificationHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.Notification', game: 'Game') -> str:
        return f'{msg.text}'


from pyscrabble.client.game import Game, Client
from pyscrabble.common.model import Tile, Board, Player

import pyscrabble.common.protocol as proto

Handler._mappings: Dict[Type['proto.ServerMessage'], Type['Handler']] = {
    proto.JoinOk: JoinOkHandler,
    proto.ActionRejected: ActionRejectedHandler,
    proto.PlayerJoined: PlayerJoinedHandler,
    proto.PlayerLeft: PlayerLeftHandler,
    proto.PlayerReady: PlayerReadyHandler,
    proto.StartTurn: StartTurnHandler,
    proto.EndTurn: EndTurnHandler,
    proto.EndGame: EndGameHandler,
    proto.Shutdown: ShutdownHandler,
    proto.PlayerChat: PlayerChatHandler,
    proto.Notification: NotificationHandler
}
