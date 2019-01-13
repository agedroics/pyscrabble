from socket import create_connection
from threading import Thread
from typing import Any, Callable


class Client:
    def __init__(self, player_id: int, name: str, ready: bool = False):
        self.player_id = player_id
        self.name = name
        self.player: 'Player' = None
        self.ready = ready


class Connection:
    def __init__(self, on_update: Callable[[str], Any]):
        self.__stream: 'Stream' = None
        self.worker: 'StreamWorker' = None
        self.game = Game(on_update)

    def start(self, ip: str, port: int, name: str):
        if not self.__stream:
            self.__stream = Stream(create_connection((ip, port)), proto.ServerMessage)
            self.worker = StreamWorker(self.__stream, self.game.queue_in, proto.Shutdown)
            self.worker.queue_out.put(proto.Join(name))
            Thread(target=self.worker.listen_incoming, daemon=True).start()
            Thread(target=self.worker.listen_outgoing, daemon=True).start()
            Thread(target=self.game.process_incoming_messages, daemon=True).start()

    def stop(self):
        if self.__stream:
            self.__stream.close()


from pyscrabble.client.game import Game
from pyscrabble.common.model import Player
from pyscrabble.common.stream import Stream, StreamWorker

import pyscrabble.common.protocol as proto
