from enum import Enum
from typing import List


class Tile:
    def __init__(self, tile_id: int, points: int, letter: str):
        self.id = tile_id
        self.points = points
        self.letter = letter


class Player:
    def __init__(self):
        self.score = 0
        self.tiles: List['Tile'] = []


class SquareType(Enum):
    NORMAL = 'N'
    DLS = 'DLS'
    TLS = 'TLS'
    DWS = 'DWS'
    TWS = 'TWS'


class Square:
    def __init__(self, square_type: 'SquareType'):
        self.type = square_type
        self.tile: 'Tile' = None


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
