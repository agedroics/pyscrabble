from queue import Queue
from socket import socket, AF_INET, SOCK_STREAM
from threading import Thread


class Client:
    def __init__(self, player_id: int, name: str, stream: 'Stream', queue_in: Queue):
        self.player_id = player_id
        self.name = name
        self.player: Player = None
        self.ready = False
        self.worker = StreamWorker(stream, queue_in)


class Server:
    def __init__(self):
        self.__socket = None
        self.__game = Game()

    def __handle_connection(self, stream: 'Stream'):
        msg = stream.get_msg()
        if isinstance(msg, proto.Join):
            self.__game.clients_lock.acquire()
            if len(self.__game.clients) == 4:
                self.__game.clients_lock.release()
                stream.send_msg(proto.ActionRejected('Server is full'))
                stream.close()
            elif not self.__game.lobby:
                self.__game.clients_lock.release()
                stream.send_msg(proto.ActionRejected('Game in progress'))
                stream.close()
            else:
                free_id = self.__game.find_free_player_id()
                new_client = Client(free_id, msg.name, stream, self.__game.queue_in)
                self.__game.clients.append(new_client)

                other_clients = []
                player_joined = proto.PlayerJoined(free_id, new_client.name)
                for client in self.__game.clients:
                    if client.player_id != free_id:
                        other_clients.append(proto.PlayerInfo(client.player_id, client.ready, client.name))
                        client.worker.queue_out.put(player_joined)
                new_client.worker.queue_out.put(proto.JoinOk(free_id, other_clients))
                self.__game.clients_lock.release()

                Thread(target=new_client.worker.listen_incoming, args=(new_client,), daemon=True).start()
                new_client.worker.listen_outgoing(new_client)
        else:
            stream.close()

    def __listen_connections(self):
        while True:
            s, _ = self.__socket.accept()
            Thread(target=self.__handle_connection, args=(Stream(s, proto.ClientMessage),), daemon=True).start()

    def start(self, ip: str, port: int):
        if self.__socket is None:
            self.__socket = socket(AF_INET, SOCK_STREAM)
            self.__socket.bind((ip, port))
            self.__socket.listen(1)
            Thread(target=self.__listen_connections, daemon=True).start()
            Thread(target=self.__game.process_incoming_requests, daemon=True).start()

    def stop(self):
        if self.__socket:
            self.__socket.close()


from pyscrabble.common.model import Player
from pyscrabble.common.stream import Stream, StreamWorker
from pyscrabble.server.game import Game

import pyscrabble.common.protocol as proto
