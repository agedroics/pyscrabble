import gzip
import random
import socket
from abc import ABC
from queue import Queue
from threading import Thread, Lock
from typing import List, Set, Tuple, Dict, Type, Optional

from pkg_resources import resource_stream

import pyscrabble.protocol as proto
from pyscrabble.model import Player, Board, Tile, SquareType

words: Set[str] = None


def load_words():
    global words
    if not words:
        with resource_stream(__name__, 'words') as stream:
            with gzip.open(stream, mode='rt') as f:
                words = set(line.strip() for line in f)


class Client:
    def __init__(self, player_id: int, name: str, stream: 'proto.Stream', queue_in: Queue):
        self.player_id = player_id
        self.name = name
        self.player: Player = None
        self.ready = False
        self.worker = proto.StreamWorker(stream, queue_in, self)

    def send_msg(self, msg: 'proto.ServerMessage'):
        self.worker.queue_out.put(msg)


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
                        client.send_msg(player_joined)
                new_client.send_msg(proto.JoinOk(free_id, player_infos))
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
            self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.__socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
                client.send_msg(msg)

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


def _lobby_only(handler):
    def handler_(cls, msg, client, game):
        if game.lobby:
            handler(cls, msg, client, game)
    return handler_


def _turn_only(handler):
    def handler_(cls, msg, client, game):
        if not game.lobby:
            if client.player_id == game.turn_player_id:
                handler(cls, msg, client, game)
            else:
                client.send_msg(proto.ActionRejected('Not player\'s turn!'))
    return handler_


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
    game.turns_without_score = 0
    for client in game.clients:
        client.ready = False
        player = client.player = Player()
        player.tiles = game.free_tiles[:7]
        game.free_tiles = game.free_tiles[7:]
    game.send_to_all(proto.Notification('Game started!'))
    game.turn_player_id = game.clients[random.randint(0, len(game.clients) - 1)].player_id
    tiles_left = len(game.free_tiles)
    player_tile_counts = [proto.StartTurnPlayer(client.player_id, 7) for client in game.clients]
    for client in game.clients:
        start_turn = proto.StartTurn(game.turn_player_id, tiles_left, client.player.tiles, player_tile_counts)
        client.send_msg(start_turn)
    game.lobby = False


class ReadyHandler(Handler):
    @classmethod
    @_lobby_only
    def _handle(cls, msg: 'proto.Ready', client: 'Client', game: 'Game'):
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
            if len(game.clients) > 1 and all(client.ready for client in game.clients):
                _start_game(game)
        elif len(game.clients) < 2:
            for client_ in game.clients:
                deduction = sum(tile.points for tile in client_.player.tiles)
                client_.send_msg(proto.Notification(f'Deducted {deduction} points'))
                client_.player.score -= sum(tile.points for tile in client_.player.tiles)
            end_game = proto.EndGame([proto.EndGamePlayer(client.player_id, client.player.score)
                                      for client in game.clients])
            game.send_to_all(end_game)
            game.lobby = True
        elif game.turn_player_id == client.player_id:
            game.free_tiles += client.player.tiles
            random.shuffle(game.free_tiles)
            game.turn_player_id = game.clients[i % len(game.clients)].player_id
            tiles_left = len(game.free_tiles)
            player_tile_counts = [proto.StartTurnPlayer(client.player_id, len(client.player.tiles))
                                  for client in game.clients]
            for client_ in game.clients:
                client_.send_msg(proto.StartTurn(game.turn_player_id, tiles_left, client_.player.tiles,
                                                 player_tile_counts))


def _end_turn_without_score(client: 'Client', game: 'Game'):
    if game.turns_without_score == 5:
        game.send_to_all(proto.Notification('6 consecutive scoreless turns have occurred!'))
        for client_ in game.clients:
            deduction = sum(tile.points for tile in client_.player.tiles)
            client_.send_msg(proto.Notification(f'Deducted {deduction} points'))
            client_.player.score -= sum(tile.points for tile in client_.player.tiles)
        end_game = proto.EndGame([proto.EndGamePlayer(client.player_id, client.player.score)
                                  for client in game.clients])
        game.send_to_all(end_game)
        game.lobby = True
    else:
        game.turns_without_score += 1
        game.send_to_all(proto.EndTurn(game.turn_player_id, client.player.score, []))
        game.turn_player_id = game.clients[(game.clients.index(client) + 1) % len(game.clients)].player_id
        player_tile_counts = [proto.StartTurnPlayer(client.player_id, len(client.player.tiles))
                              for client in game.clients]
        for client_ in game.clients:
            start_turn = proto.StartTurn(game.turn_player_id, len(game.free_tiles), client_.player.tiles,
                                         player_tile_counts)
            client_.send_msg(start_turn)


class TileExchangeHandler(Handler):
    @classmethod
    @_turn_only
    def _handle(cls, msg: 'proto.TileExchange', client: 'Client', game: 'Game'):
        if len(game.free_tiles) < 7:
            client.send_msg(proto.ActionRejected('There are less than 7 tiles left!'))
        elif not msg.tile_ids:
            client.send_msg(proto.ActionRejected('Tile exchange requires at least one selected tile!'))
        else:
            tiles = [tile for tile in client.player.tiles if tile.id in msg.tile_ids]
            tile_count = len(tiles)
            if len(msg.tile_ids) == tile_count:
                client.player.tiles = [tile for tile in client.player.tiles if tile not in tiles]
                game.free_tiles += tiles
                random.shuffle(game.free_tiles)
                client.player.tiles += game.free_tiles[:tile_count]
                game.free_tiles = game.free_tiles[tile_count:]
                game.send_to_all(proto.Notification(f'{client.name} exchanged tiles'), client.player_id)
                client.send_msg(proto.Notification('You exchanged tiles'))
                _end_turn_without_score(client, game)
            else:
                client.send_msg(proto.ActionRejected('Selected tiles do not belong to player!'))


class FullTile:
    def __init__(self, tile: 'Tile', place_tiles_tile: 'proto.PlaceTilesTile'):
        self.id = tile.id
        self.letter = tile.letter if tile.letter else place_tiles_tile.letter
        self.points = tile.points
        self.row = place_tiles_tile.position // 15
        self.col = place_tiles_tile.position % 15
        self.position = place_tiles_tile.position


class WordCounter:
    def __init__(self):
        self.word = ''
        self.points = 0
        self.multiplier = 1
        self.is_connected = False


class PlaceTilesHandler(Handler):
    @classmethod
    @_turn_only
    def _handle(cls, msg: 'proto.PlaceTiles', client: 'Client', game: 'Game'):
        if not msg.tile_placements:
            game.send_to_all(proto.Notification(f'{client.name} skipped'), client.player_id)
            client.send_msg(proto.Notification('You skipped'))
            _end_turn_without_score(client, game)
            return

        player_tiles_by_id = {tile.id: tile for tile in client.player.tiles}
        tiles = [FullTile(player_tiles_by_id[tile.id], tile)
                 for tile in msg.tile_placements if tile.id in player_tiles_by_id]
        tile_count = len(tiles)
        if len(msg.tile_placements) != tile_count:
            client.send_msg(proto.ActionRejected('Placed tiles do not belong to player!'))
            return

        if any(not tile.letter for tile in tiles):
            client.send_msg(proto.ActionRejected('Blank tiles must be assigned a letter!'))
            return

        if all(tile.row == tiles[0].row for tile in tiles):
            def accessor(coord1, coord2):
                return game.board.squares[coord1][coord2]
        elif all(tile.col == tiles[0].col for tile in tiles):
            def accessor(coord1, coord2):
                return game.board.squares[coord2][coord1]
            for tile in tiles:
                tile.row, tile.col = tile.col, tile.row
        else:
            client.send_msg(proto.ActionRejected('Tiles must form a horizontal or vertical line!'))
            return

        row = tiles[0].row
        tiles.sort(key=lambda tile: tile.col)
        tiles_by_col = {tile.col: tile for tile in tiles}
        for tile in tiles:
            if tile.row not in range(15) or tile.col not in range(15) or tiles_by_col.get(tile.col) != tile or accessor(tile.row, tile.col).tile:
                client.send_msg(proto.ActionRejected('Tiles are overlapping or out of bounds!'))
                return

        for col in range(tiles[0].col + 1, tiles[-1].col + 1):
            if not accessor(row, col).tile and col not in tiles_by_col:
                client.send_msg(proto.ActionRejected('Tiles must form a single line!'))
                return

        if not accessor(7, 7).tile:
            if row != 7 or 7 not in tiles_by_col:
                client.send_msg(proto.ActionRejected('The center square must be populated!'))
                return
            elif tile_count == 1:
                client.send_msg(proto.ActionRejected('The first word must be at least 2 characters long!'))
                return

        def count_word(tile_from: 'FullTile', horizontal: bool = False) -> Optional['WordCounter']:
            counter = WordCounter()
            for i in range((tile_from.col if horizontal else tile_from.row) - 1, -1, -1):
                tile = accessor(row, i).tile if horizontal else accessor(i, tile_from.col).tile
                if not tile:
                    break
                counter.points += tile.points
                counter.word = tile.letter + counter.word
                counter.is_connected = True

            for i in range(tile_from.col if horizontal else tile_from.row, 15):
                square = accessor(row, i) if horizontal else accessor(i, tile_from.col)
                if square.tile:
                    tile = square.tile
                    counter.points += tile.points
                    counter.is_connected = True
                elif (i in tiles_by_col) if horizontal else (i == tile_from.row):
                    tile = tiles_by_col[i] if horizontal else tile_from
                    if square.type == SquareType.DLS:
                        counter.points += 2 * tile.points
                    elif square.type == SquareType.TLS:
                        counter.points += 3 * tile.points
                    else:
                        counter.points += tile.points
                    if square.type == SquareType.DWS:
                        counter.multiplier *= 2
                    elif square.type == SquareType.TWS:
                        counter.multiplier *= 3
                else:
                    break
                counter.word += tile.letter

            return counter if len(counter.word) > 1 else None

        word_counters = []
        horizontal_counter = count_word(tiles[0], True)
        if horizontal_counter:
            word_counters.append(horizontal_counter)
        for tile in tiles:
            word_counter = count_word(tile)
            if word_counter:
                word_counters.append(word_counter)

        if all(not counter.is_connected for counter in word_counters) and accessor(7, 7).tile:
            client.send_msg(proto.ActionRejected('Must connect with pre-existing tiles!'))
            return

        global words
        invalid_words = {counter.word for counter in word_counters if counter.word not in words}
        if invalid_words:
            client.send_msg(proto.ActionRejected(f'Invalid word{"" if len(invalid_words) == 1 else "s"}: {", ".join(invalid_words)}'))
            return

        for counter in word_counters:
            score = counter.points * counter.multiplier
            client.player.score += score
            game.send_to_all(proto.Notification(f'{counter.word} - {score} points'))

        if tile_count == 7:
            client.player.score += 50
            game.send_to_all(proto.Notification('Bingo! - 50 points'))

        for tile in tiles:
            accessor(tile.row, tile.col).tile = tile

        placed_tiles = [proto.EndTurnTile(tile.position, tile.points, tile.letter) for tile in tiles]
        game.send_to_all(proto.EndTurn(game.turn_player_id, client.player.score, placed_tiles))
        game.turns_without_score = 0

        tile_ids = {tile.id for tile in tiles}
        client.player.tiles = [tile for tile in client.player.tiles if tile.id not in tile_ids]

        if game.free_tiles:
            take_tiles_count = min(len(game.free_tiles), tile_count)
            client.player.tiles += game.free_tiles[:take_tiles_count]
            game.free_tiles = game.free_tiles[take_tiles_count:]
        elif not client.player.tiles:
            game.send_to_all(proto.Notification(f'{client.name} has played out!'), client.player_id)
            client.send_msg(proto.Notification('You have played out!'))
            all_sums = 0
            for client_ in game.clients:
                if client_ != client:
                    deduction = sum(tile.points for tile in client_.player.tiles)
                    client_.player.score -= deduction
                    all_sums += deduction
                    client_.send_msg(proto.Notification(f'Deducted {deduction} points'))
            client.player.score += all_sums
            client.send_msg(proto.Notification(f'Awarded {all_sums} points'))
            end_game = proto.EndGame([proto.EndGamePlayer(client.player_id, client.player.score)
                                      for client in game.clients])
            game.send_to_all(end_game)
            game.lobby = True
            return

        game.turn_player_id = game.clients[(game.clients.index(client) + 1) % len(game.clients)].player_id
        player_tile_counts = [proto.StartTurnPlayer(client.player_id, len(client.player.tiles))
                              for client in game.clients]
        for client_ in game.clients:
            start_turn = proto.StartTurn(game.turn_player_id, len(game.free_tiles), client_.player.tiles,
                                         player_tile_counts)
            client_.send_msg(start_turn)


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
