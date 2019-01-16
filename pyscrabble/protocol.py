import socket
from abc import ABC
from queue import Queue
from typing import Callable, List, Type

import pyscrabble.model as model
import pyscrabble.utils as utils


def _serializer(func: Callable[['Message'], bytes]) -> Callable[['Message'], bytes]:
    def wrapper(self: 'Message') -> bytes:
        return Message.prefix_map_inv[type(self)] + func(self)
    return wrapper


class Message(ABC):
    @_serializer
    def serialize(self) -> bytes:
        return b''

    @staticmethod
    def deserialize(stream: 'Stream') -> 'Message':
        return Message.prefix_map[stream.get_bytes(1)]._deserialize(stream)

    @classmethod
    def _deserialize(cls, stream: 'Stream') -> 'Message':
        return cls()


class ClientMessage(Message, ABC):
    @staticmethod
    def deserialize(stream: 'Stream') -> 'ClientMessage':
        message_type = ClientMessage.prefix_map.get(stream.get_bytes(1))
        if message_type:
            return message_type._deserialize(stream)


class Join(ClientMessage):
    def __init__(self, name: str):
        self.name = name

    @_serializer
    def serialize(self) -> bytes:
        b = self.name.encode('utf-8')
        return utils.int_to_byte(len(b)) + b

    @classmethod
    def _deserialize(cls, stream: 'Stream') -> 'Join':
        return cls(stream.get_str(stream.get_int()))


class Ready(ClientMessage):
    ...


class Leave(ClientMessage):
    ...


class TileExchange(ClientMessage):
    def __init__(self, tile_ids: List[int]):
        self.tile_ids = tile_ids

    @_serializer
    def serialize(self) -> bytes:
        return utils.int_to_byte(len(self.tile_ids)) + bytes(self.tile_ids)

    @classmethod
    def _deserialize(cls, stream: 'Stream') -> 'TileExchange':
        return cls([tile_id for tile_id in stream.get_bytes(stream.get_int())])


class PlaceTilesTile:
    def __init__(self, position: int, tile_id: int, letter: str = None):
        self.position = position
        self.id = tile_id
        self.letter = letter


class PlaceTiles(ClientMessage):
    def __init__(self, tile_placements: List['PlaceTilesTile']):
        self.tile_placements = tile_placements

    @_serializer
    def serialize(self) -> bytes:
        result = utils.int_to_byte(len(self.tile_placements))
        for tile in self.tile_placements:
            result += utils.int_to_byte(tile.position) + utils.int_to_byte(tile.id)
            if tile.letter is None:
                result += b'\x00'
            else:
                letter = tile.letter.encode('utf-8')
                result += utils.int_to_byte(len(letter)) + letter
        return result

    @classmethod
    def _deserialize(cls, stream: 'Stream') -> 'PlaceTiles':
        tiles: List['PlaceTilesTile'] = []
        for _ in range(stream.get_int()):
            position = stream.get_int()
            tile_id = stream.get_int()
            m = stream.get_int()
            letter = stream.get_str(m) if m else None
            tiles.append(PlaceTilesTile(position, tile_id, letter))
        return cls(tiles)


class Chat(ClientMessage):
    def __init__(self, text: str):
        self.text = text

    @_serializer
    def serialize(self) -> bytes:
        b = self.text.encode('utf-8')
        return len(b).to_bytes(2, byteorder='big') + b

    @classmethod
    def _deserialize(cls, stream: 'Stream') -> 'Chat':
        return cls(stream.get_str(stream.get_int(2)))


ClientMessage.prefix_map = {
    b'\x00': Join,
    b'\x01': Ready,
    b'\x02': Leave,
    b'\x03': TileExchange,
    b'\x04': PlaceTiles,
    b'\x05': Chat
}
ClientMessage.prefix_map_inv = {value: key for key, value in ClientMessage.prefix_map.items()}


class ServerMessage(Message, ABC):
    @staticmethod
    def deserialize(stream: 'Stream') -> 'ServerMessage':
        message_type = ServerMessage.prefix_map.get(stream.get_bytes(1))
        if message_type:
            return message_type._deserialize(stream)


class PlayerInfo:
    def __init__(self, player_id: int, ready: bool, name: str):
        self.player_id = player_id
        self.ready = ready
        self.name = name


class JoinOk(ServerMessage):
    def __init__(self, player_id: int, players: List['PlayerInfo']):
        self.player_id = player_id
        self.players = players

    @_serializer
    def serialize(self) -> bytes:
        result = utils.int_to_byte(self.player_id) + utils.int_to_byte(len(self.players))
        for player_info in self.players:
            result += utils.int_to_byte(player_info.player_id) + utils.int_to_byte(player_info.ready)
            b = player_info.name.encode('utf-8')
            result += utils.int_to_byte(len(b)) + b
        return result

    @classmethod
    def _deserialize(cls, stream: 'Stream') -> 'JoinOk':
        self_player_id = stream.get_int()
        players = [PlayerInfo(stream.get_int(), bool(stream.get_int()), stream.get_str(stream.get_int()))
                   for _ in range(stream.get_int())]
        return cls(self_player_id, players)


class ActionRejected(ServerMessage):
    def __init__(self, reason: str):
        self.reason = reason

    @_serializer
    def serialize(self) -> bytes:
        b = self.reason.encode('utf-8')
        return len(b).to_bytes(2, byteorder='big') + b

    @classmethod
    def _deserialize(cls, stream: 'Stream') -> 'ActionRejected':
        return cls(stream.get_str(stream.get_int(2)))


class PlayerJoined(ServerMessage):
    def __init__(self, player_id: int, name: str):
        self.player_id = player_id
        self.name = name

    @_serializer
    def serialize(self) -> bytes:
        b = self.name.encode('utf-8')
        return utils.int_to_byte(self.player_id) + utils.int_to_byte(len(b)) + b

    @classmethod
    def _deserialize(cls, stream: 'Stream') -> 'PlayerJoined':
        return cls(stream.get_int(), stream.get_str(stream.get_int()))


class PlayerLeft(ServerMessage):
    def __init__(self, player_id: int):
        self.player_id = player_id

    @_serializer
    def serialize(self) -> bytes:
        return utils.int_to_byte(self.player_id)

    @classmethod
    def _deserialize(cls, stream: 'Stream') -> 'PlayerLeft':
        return cls(stream.get_int())


class PlayerReady(ServerMessage):
    def __init__(self, player_id: int):
        self.player_id = player_id

    @_serializer
    def serialize(self) -> bytes:
        return utils.int_to_byte(self.player_id)

    @classmethod
    def _deserialize(cls, stream: 'Stream') -> 'PlayerReady':
        return cls(stream.get_int())


class StartTurnPlayer:
    def __init__(self, player_id: int, tile_count: int):
        self.id = player_id
        self.tile_count = tile_count


class StartTurn(ServerMessage):
    def __init__(self, turn_player_id: int, tiles_left: int, tiles: List['model.Tile'],
                 player_tile_counts: List['StartTurnPlayer']):
        self.turn_player_id = turn_player_id
        self.tiles_left = tiles_left
        self.tiles = tiles
        self.player_tile_counts = player_tile_counts

    @_serializer
    def serialize(self) -> bytes:
        result = utils.int_to_byte(self.turn_player_id)
        result += utils.int_to_byte(self.tiles_left) + utils.int_to_byte(len(self.tiles))
        for tile in self.tiles:
            result += utils.int_to_byte(tile.id) + utils.int_to_byte(tile.points)
            if tile.letter is None:
                result += b'\x00'
            else:
                b = tile.letter.encode('utf-8')
                result += utils.int_to_byte(len(b)) + b
        result += utils.int_to_byte(len(self.player_tile_counts))
        for player in self.player_tile_counts:
            result += utils.int_to_byte(player.id) + utils.int_to_byte(player.tile_count)
        return result

    @classmethod
    def _deserialize(cls, stream: 'Stream') -> 'StartTurn':
        player_id = stream.get_int()
        tiles_left = stream.get_int()
        tiles: List['model.Tile'] = []
        for _ in range(stream.get_int()):
            tile_id = stream.get_int()
            points = stream.get_int()
            m = stream.get_int()
            letter = stream.get_str(m) if m else None
            tiles.append(model.Tile(tile_id, points, letter))
        player_tile_counts: List['StartTurnPlayer'] = []
        for _ in range(stream.get_int()):
            player_tile_counts.append(StartTurnPlayer(stream.get_int(), stream.get_int()))
        return cls(player_id, tiles_left, tiles, player_tile_counts)


class EndTurnTile:
    def __init__(self, position: int, points: int, letter: str):
        self.position = position
        self.points = points
        self.letter = letter


class EndTurn(ServerMessage):
    def __init__(self, player_id: int, score: int, placed_tiles: List['EndTurnTile']):
        self.player_id = player_id
        self.score = score
        self.placed_tiles = placed_tiles

    @_serializer
    def serialize(self) -> bytes:
        result = utils.int_to_byte(self.player_id) + self.score.to_bytes(2, byteorder='big', signed=True)
        result += utils.int_to_byte(len(self.placed_tiles))
        for tile in self.placed_tiles:
            result += utils.int_to_byte(tile.position) + utils.int_to_byte(tile.points)
            b = tile.letter.encode('utf-8')
            result += utils.int_to_byte(len(b)) + b
        return result

    @classmethod
    def _deserialize(cls, stream: 'Stream') -> 'EndTurn':
        player_id = stream.get_int()
        score = stream.get_int(2, signed=True)
        tiles = [EndTurnTile(stream.get_int(), stream.get_int(), stream.get_str(stream.get_int()))
                 for _ in range(stream.get_int())]
        return cls(player_id, score, tiles)


class EndGamePlayer:
    def __init__(self, player_id: int, score: int):
        self.player_id = player_id
        self.score = score


class EndGame(ServerMessage):
    def __init__(self, players: List['EndGamePlayer']):
        self.players = players

    @_serializer
    def serialize(self) -> bytes:
        result = utils.int_to_byte(len(self.players))
        for player in self.players:
            result += utils.int_to_byte(player.player_id) + player.score.to_bytes(2, byteorder='big', signed=True)
        return result

    @classmethod
    def _deserialize(cls, stream: 'Stream') -> 'EndGame':
        return cls([EndGamePlayer(stream.get_int(), stream.get_int(2, signed=True)) for _ in range(stream.get_int())])


class Shutdown(ServerMessage):
    ...


class PlayerChat(ServerMessage):
    def __init__(self, player_id: int, text: str):
        self.player_id = player_id
        self.text = text

    @_serializer
    def serialize(self) -> bytes:
        b = self.text.encode('utf-8')
        return utils.int_to_byte(self.player_id) + len(b).to_bytes(2, byteorder='big') + b

    @classmethod
    def _deserialize(cls, stream: 'Stream') -> 'PlayerChat':
        return cls(stream.get_int(), stream.get_str(stream.get_int(2)))


class Notification(ServerMessage):
    def __init__(self, text: str):
        self.text = text

    @_serializer
    def serialize(self) -> bytes:
        b = self.text.encode('utf-8')
        return len(b).to_bytes(2, byteorder='big') + b

    @classmethod
    def _deserialize(cls, stream: 'Stream') -> 'Notification':
        return cls(stream.get_str(stream.get_int(2)))


ServerMessage.prefix_map = {
    b'\x06': JoinOk,
    b'\x07': ActionRejected,
    b'\x08': PlayerJoined,
    b'\x09': PlayerLeft,
    b'\x0A': PlayerReady,
    b'\x0B': StartTurn,
    b'\x0C': EndTurn,
    b'\x0D': EndGame,
    b'\x0E': Shutdown,
    b'\x0F': PlayerChat,
    b'\x10': Notification
}
ServerMessage.prefix_map_inv = {value: key for key, value in ServerMessage.prefix_map.items()}

Message.prefix_map = {**ClientMessage.prefix_map, **ServerMessage.prefix_map}
Message.prefix_map_inv = {**ClientMessage.prefix_map_inv, **ServerMessage.prefix_map_inv}


class Stream:
    def __init__(self, s: socket.socket, in_msg_type: Type['Message']):
        self.__socket = s
        self.__in_msg_type = in_msg_type
        self.__buffer = b''

    def get_bytes(self, n: int) -> bytes:
        result = b''
        while n > 0:
            if self.__buffer:
                bytes_to_take = min(n, len(self.__buffer))
                result += self.__buffer[:bytes_to_take]
                self.__buffer = self.__buffer[bytes_to_take:]
                n -= bytes_to_take
            else:
                self.__buffer = self.__socket.recv(1024)
                if not self.__buffer:
                    self.__socket.close()
                    break
        return result

    def get_int(self, n: int = 1, signed=False) -> int:
        return int.from_bytes(self.get_bytes(n), byteorder='big', signed=signed)

    def get_str(self, n: int) -> str:
        return self.get_bytes(n).decode('utf-8')

    def get_msg(self) -> 'Message':
        return self.__in_msg_type.deserialize(self)

    def send_msg(self, msg: 'Message'):
        self.__socket.sendall(msg.serialize())

    def close(self):
        try:
            self.__socket.shutdown(socket.SHUT_RDWR)
            self.__socket.close()
        except IOError:
            pass


class StreamWorker:
    def __init__(self, stream: 'Stream', queue_in: Queue, *extra_info):
        self.__stream = stream
        self.__queue_in = queue_in
        self.queue_out = Queue()
        self.__extra_info = extra_info

    def listen_incoming(self):
        try:
            while True:
                msg = self.__stream.get_msg()
                if msg:
                    self.__queue_in.put((msg, *self.__extra_info))
                    if isinstance(msg, Leave) or isinstance(msg, Shutdown):
                        break
                else:
                    self.__queue_in.put((None, *self.__extra_info))
                    break
        except socket.error:
            self.__queue_in.put((None, *self.__extra_info))
        finally:
            self.__stream.close()
            self.queue_out.put(None)

    def listen_outgoing(self):
        try:
            while True:
                msg = self.queue_out.get()
                if msg:
                    self.__stream.send_msg(msg)
                    if isinstance(msg, Leave) or isinstance(msg, Shutdown):
                        break
                else:
                    break
        except socket.error:
            self.__queue_in.put((None, *self.__extra_info))
        finally:
            self.__stream.close()
