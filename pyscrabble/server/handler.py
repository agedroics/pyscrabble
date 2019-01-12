from abc import ABC
from typing import Dict, Type


class Handler(ABC):
    @staticmethod
    def handle(msg: 'proto.ClientMessage', client: 'Client', game: 'Game'):
        handler = Handler._mappings.get(msg.__class__)
        if handler:
            game.clients_lock.acquire()
            handler._handle(msg, client, game)
            game.clients_lock.release()

    @classmethod
    def _handle(cls, msg: 'proto.ClientMessage', client: 'Client', game: 'Game'):
        pass


class JoinHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.Join', client: 'Client', game: 'Game'):
        pass


def _start_game(game: 'Game'):
    game.board = Board()
    game.load_tiles()
    game.lobby = False
    for client in game.clients:
        player = client.player = Player()
        player.tiles = game.free_tiles[:7]
        game.free_tiles = game.free_tiles[7:]
    game.turn_player_id = game.clients[0].player_id
    tiles_left = len(game.free_tiles)
    for client in game.clients:
        start_turn = proto.StartTurn(game.turn_player_id, 0, tiles_left, client.player.tiles)
        client.worker.queue_out.put(start_turn)


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


class KeepAliveHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.KeepAlive', client: 'Client', game: 'Game'):
        pass


class LeaveHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.Leave', client: 'Client', game: 'Game'):
        i = game.clients.index(client)
        del game.clients[i]
        client.worker.queue_out.put(None)
        game.send_to_all(proto.PlayerLeft(client.player_id))
        if game.lobby:
            all_ready = len(game.clients) > 1 and all(client.ready for client in game.clients)
            if all_ready:
                _start_game(game)
        elif len(game.clients) < 2:
            game.lobby = True
            end_game = proto.EndGame([proto.EndGamePlayer(client.player_id, client.player.score) for client in game.clients])
            game.send_to_all(end_game)
        elif game.turn_player_id == client.player_id:
            game.send_to_all(proto.EndTurn(client.player_id, 0, []))
            game.turn_player_id = game.clients[i % len(game.clients)].player_id
            tiles_left = len(game.free_tiles)
            for client in game.clients:
                start_turn = proto.StartTurn(game.turn_player_id, 0, tiles_left, client.player.tiles)
                client.worker.queue_out.put(start_turn)


class TileExchangeHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.TileExchange', client: 'Client', game: 'Game'):
        ...


class PlaceTilesHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.PlaceTiles', client: 'Client', game: 'Game'):
        ...


class ChatHandler(Handler):
    @classmethod
    def _handle(cls, msg: 'proto.Chat', client: 'Client', game: 'Game'):
        game.send_to_all(proto.PlayerChat(client.player_id, msg.text))


from pyscrabble.common.model import Board, Player
from pyscrabble.server.game import Game
from pyscrabble.server.server import Client

import pyscrabble.common.protocol as proto

Handler._mappings: Dict[Type['proto.ClientMessage'], Type['Handler']] = {
    proto.Join: JoinHandler,
    proto.Ready: ReadyHandler,
    proto.KeepAlive: KeepAliveHandler,
    proto.Leave: LeaveHandler,
    proto.TileExchange: TileExchangeHandler,
    proto.PlaceTiles: PlaceTilesHandler,
    proto.Chat: ChatHandler
}
