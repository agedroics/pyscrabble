from queue import Queue
from socket import socket, AF_INET, SOCK_STREAM
from threading import Thread


class Client:
    def __init__(self, player_id: int, name: str, stream: 'Stream', queue_in: Queue):
        self.player_id = player_id
        self.name = name
        self.player: Player = None
        self.ready = False
        self.worker = StreamWorker(stream, queue_in, self)


class Server:
    def __init__(self):
        self.__socket: socket = None
        self.game = Game()

    def __handle_connection(self, stream: 'Stream'):
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
                Thread(target=self.__handle_connection, args=(Stream(s, proto.ClientMessage),), daemon=True).start()
        except IOError:
            pass

    def start(self, ip: str, port: int):
        if self.__socket is None:
            self.__socket = socket(AF_INET, SOCK_STREAM)
            self.__socket.bind((ip, port))
            self.__socket.listen(1)
            Thread(target=self.__listen_connections, daemon=True).start()
            Thread(target=self.game.process_incoming_requests, daemon=True).start()

    def stop(self):
        self.game.send_to_all(proto.Shutdown())
        self.game.queue_in.put((None, None))
        self.__socket.close()


from pyscrabble.common.model import Player
from pyscrabble.common.stream import Stream, StreamWorker
from pyscrabble.server.game import Game

import pyscrabble.common.protocol as proto
