from abc import ABC, abstractmethod
from typing import Callable, List

from bidict import bidict

from pyscrabble.game import Tile
from pyscrabble.network import Stream


def _int_to_byte(n: int) -> bytes:
    return n.to_bytes(1, byteorder='big')


def serializer(func: Callable[['Message'], bytes]) -> Callable[['Message'], bytes]:
    def wrapper(self: 'Message') -> bytes:
        return Message._prefix_map.inv[type(self)] + func(self)
    return wrapper


class Message(ABC):
    @serializer
    def serialize(self) -> bytes:
        return b''

    @staticmethod
    @abstractmethod
    def deserialize(stream: 'Stream'):
        ...

    @classmethod
    def _deserialize(cls, stream: Stream):
        return cls()


class ClientMessage(Message, ABC):
    @staticmethod
    def deserialize(stream: Stream) -> 'ClientMessage':
        return ClientMessage._prefix_map[stream.get_bytes(1)]._deserialize(stream)


class Join(ClientMessage):
    def __init__(self, name: str):
        self.name = name

    @serializer
    def serialize(self) -> bytes:
        b = self.name.encode('utf-8')
        return _int_to_byte(len(b)) + b

    @classmethod
    def _deserialize(cls, stream: Stream) -> 'Join':
        return cls(stream.get_str(stream.get_int()))


class Ready(ClientMessage):
    ...


class KeepAlive(ClientMessage):
    ...


class Leave(ClientMessage):
    ...


class TileExchange(ClientMessage):
    def __init__(self, tile_ids: List[int]):
        self.tile_ids = tile_ids

    @serializer
    def serialize(self) -> bytes:
        return _int_to_byte(len(self.tile_ids)) + bytes(self.tile_ids)

    @classmethod
    def _deserialize(cls, stream: Stream) -> 'TileExchange':
        return cls([tile_id for tile_id in stream.get_bytes(stream.get_int())])


class PlaceTilesTile:
    def __init__(self, position: int, tile_id: int, letter: str=None):
        self.position = position
        self.tile_id = tile_id
        self.letter = letter


class PlaceTiles(ClientMessage):
    def __init__(self, tile_placements: List[PlaceTilesTile]):
        self.tile_placements = tile_placements

    @serializer
    def serialize(self) -> bytes:
        result = _int_to_byte(len(self.tile_placements))
        for tile in self.tile_placements:
            result += _int_to_byte(tile.position) + _int_to_byte(tile.tile_id)
            if tile.letter is None:
                result += b'\x00'
            else:
                letter = tile.letter.encode('utf-8')
                result += _int_to_byte(len(letter)) + letter
        return result

    @classmethod
    def _deserialize(cls, stream: Stream) -> 'PlaceTiles':
        tiles: List[PlaceTilesTile] = []
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

    @serializer
    def serialize(self) -> bytes:
        b = self.text.encode('utf-8')
        return len(b).to_bytes(2, byteorder='big') + b

    @classmethod
    def _deserialize(cls, stream: Stream) -> 'Chat':
        return cls(stream.get_str(stream.get_int(2)))


ClientMessage._prefix_map = bidict({
    b'\x00': Join,
    b'\x01': Ready,
    b'\x02': KeepAlive,
    b'\x03': Leave,
    b'\x04': TileExchange,
    b'\x05': PlaceTiles,
    b'\x06': Chat
})


class ServerMessage(Message, ABC):
    @staticmethod
    def deserialize(stream: Stream) -> 'ServerMessage':
        return ServerMessage._prefix_map[stream.get_bytes(1)]._deserialize(stream)


class PlayerInfo:
    def __init__(self, player_id: int, ready: bool, name: str):
        self.player_id = player_id
        self.ready = ready
        self.name = name


class JoinOk(ServerMessage):
    def __init__(self, player_id: int, players: List[PlayerInfo]):
        self.player_id = player_id
        self.players = players

    @serializer
    def serialize(self) -> bytes:
        result = _int_to_byte(self.player_id) + _int_to_byte(len(self.players))
        for player_info in self.players:
            result += _int_to_byte(player_info.player_id) + _int_to_byte(player_info.ready)
            b = player_info.name.encode('utf-8')
            result += _int_to_byte(len(b)) + b
        return result

    @classmethod
    def _deserialize(cls, stream: Stream) -> 'JoinOk':
        self_player_id = stream.get_int()
        players = [PlayerInfo(stream.get_int(), bool(stream.get_int()), stream.get_str(stream.get_int()))
                   for _ in range(stream.get_int())]
        return cls(self_player_id, players)


class ActionRejected(ServerMessage):
    def __init__(self, reason: str):
        self.reason = reason

    @serializer
    def serialize(self) -> bytes:
        b = self.reason.encode('utf-8')
        return len(b).to_bytes(2, byteorder='big') + b

    @classmethod
    def _deserialize(cls, stream: Stream) -> 'ActionRejected':
        return cls(stream.get_str(stream.get_int(2)))


class PlayerJoined(ServerMessage):
    def __init__(self, player_id: int, name: str):
        self.player_id = player_id
        self.name = name

    @serializer
    def serialize(self) -> bytes:
        b = self.name.encode('utf-8')
        return _int_to_byte(self.player_id) + _int_to_byte(len(b)) + b

    @classmethod
    def _deserialize(cls, stream: Stream) -> 'PlayerJoined':
        return cls(stream.get_int(), stream.get_str(stream.get_int()))


class PlayerLeft(ServerMessage):
    def __init__(self, player_id: int):
        self.player_id = player_id

    @serializer
    def serialize(self) -> bytes:
        return _int_to_byte(self.player_id)

    @classmethod
    def _deserialize(cls, stream: Stream) -> 'PlayerLeft':
        return cls(stream.get_int())


class PlayerReady(ServerMessage):
    def __init__(self, player_id: int):
        self.player_id = player_id

    @serializer
    def serialize(self) -> bytes:
        return _int_to_byte(self.player_id)

    @classmethod
    def _deserialize(cls, stream: Stream) -> 'PlayerReady':
        return cls(stream.get_int())


class StartTurn(ServerMessage):
    def __init__(self, player_id: int, timer: int, tiles_left: int, tiles: List[Tile]):
        self.player_id = player_id
        self.timer = timer
        self.tiles_left = tiles_left
        self.tiles = tiles

    @serializer
    def serialize(self) -> bytes:
        result = _int_to_byte(self.player_id) + self.timer.to_bytes(2, byteorder='big')
        result += _int_to_byte(self.tiles_left) + _int_to_byte(len(self.tiles))
        for tile in self.tiles:
            result += _int_to_byte(tile.id) + _int_to_byte(tile.points)
            if tile.letter is None:
                result += b'\x00'
            else:
                b = tile.letter.encode('utf-8')
                result += _int_to_byte(len(b)) + b
        return result

    @classmethod
    def _deserialize(cls, stream: Stream) -> 'StartTurn':
        player_id = stream.get_int()
        timer = stream.get_int(2)
        tiles_left = stream.get_int()
        tiles: List[Tile] = []
        for _ in range(stream.get_int()):
            tile_id = stream.get_int()
            points = stream.get_int()
            m = stream.get_int()
            letter = stream.get_str(m) if m else None
            tiles.append(Tile(tile_id, points, letter))
        return cls(player_id, timer, tiles_left, tiles)


class EndTurnTile:
    def __init__(self, position: int, points: int, letter: str):
        self.position = position
        self.points = points
        self.letter = letter


class EndTurn(ServerMessage):
    def __init__(self, player_id: int, score: int, placed_tiles: List[EndTurnTile]):
        self.player_id = player_id
        self.score = score
        self.placed_tiles = placed_tiles

    @serializer
    def serialize(self) -> bytes:
        result = _int_to_byte(self.player_id) + self.score.to_bytes(2, byteorder='big')
        result += _int_to_byte(len(self.placed_tiles))
        for tile in self.placed_tiles:
            result += _int_to_byte(tile.position) + _int_to_byte(tile.points)
            b = tile.letter.encode('utf-8')
            result += _int_to_byte(len(b)) + b
        return result

    @classmethod
    def _deserialize(cls, stream: Stream) -> 'EndTurn':
        player_id = stream.get_int()
        score = stream.get_int(2)
        tiles = [EndTurnTile(stream.get_int(), stream.get_int(), stream.get_str(stream.get_int()))
                 for _ in range(stream.get_int())]
        return cls(player_id, score, tiles)


class EndGamePlayer:
    def __init__(self, player_id: int, score: int):
        self.player_id = player_id
        self.score = score


class EndGame(ServerMessage):
    def __init__(self, players: List[EndGamePlayer]):
        self.players = players

    @serializer
    def serialize(self) -> bytes:
        result = _int_to_byte(len(self.players))
        for player in self.players:
            result += _int_to_byte(player.player_id) + player.score.to_bytes(2, byteorder='big')
        return result

    @classmethod
    def _deserialize(cls, stream: Stream) -> 'EndGame':
        return cls([EndGamePlayer(stream.get_int(), stream.get_int(2)) for _ in range(stream.get_int())])


class Shutdown(ServerMessage):
    ...


class PlayerChat(ServerMessage):
    def __init__(self, player_id: int, text: str):
        self.player_id = player_id
        self.text = text

    @serializer
    def serialize(self) -> bytes:
        b = self.text.encode('utf-8')
        return _int_to_byte(self.player_id) + _int_to_byte(len(b)) + b

    @classmethod
    def _deserialize(cls, stream: Stream) -> 'PlayerChat':
        return cls(stream.get_int(), stream.get_str(stream.get_int(2)))


class Notification(ServerMessage):
    def __init__(self, text: str):
        self.text = text

    @serializer
    def serialize(self) -> bytes:
        b = self.text.encode('utf-8')
        return _int_to_byte(len(b)) + b

    @classmethod
    def _deserialize(cls, stream: Stream) -> 'Notification':
        return cls(stream.get_str(stream.get_int(2)))


ServerMessage._prefix_map = bidict({
    b'\x07': JoinOk,
    b'\x08': ActionRejected,
    b'\x09': PlayerJoined,
    b'\x0A': PlayerLeft,
    b'\x0B': PlayerReady,
    b'\x0C': StartTurn,
    b'\x0D': EndTurn,
    b'\x0E': EndGame,
    b'\x0F': Shutdown,
    b'\x10': PlayerChat,
    b'\x11': Notification
})

Message._prefix_map = bidict({**ClientMessage._prefix_map, **ServerMessage._prefix_map})
