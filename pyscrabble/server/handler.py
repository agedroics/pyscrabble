import random
from abc import ABC
from typing import Dict, Type, Optional


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


from pyscrabble.common.model import Board, Player
from pyscrabble.server.game import Game
from pyscrabble.server.server import Client

import pyscrabble.common.protocol as proto

Handler._mappings: Dict[Type['proto.ClientMessage'], Type['Handler']] = {
    proto.Ready: ReadyHandler,
    proto.Leave: LeaveHandler,
    proto.TileExchange: TileExchangeHandler,
    proto.PlaceTiles: PlaceTilesHandler,
    proto.Chat: ChatHandler
}
