import socket as sock
import threading
from queue import Queue
from typing import Type

from pyscrabble import protocol as prot
from pyscrabble.common import Message, ByteStream, StreamWorker


class Connection(ByteStream):
    def __init__(self, in_msg_type: Type[Message], socket: sock.socket):
        super().__init__(in_msg_type)
        self.__socket = socket
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
        return result

    def send_bytes(self, b: bytes):
        self.__socket.sendall(b)

    def close(self):
        self.__socket.close()


class Client(StreamWorker):
    def __init__(self, conn: Connection, incoming_queue: Queue, player_id: int, name: str):
        super().__init__(conn, incoming_queue)
        self.id = player_id
        self.name = name


class Server:
    __max_players = 4

    def __init__(self, ip: str, port: int):
        self._clients = {i: None for i in range(1, Server.__max_players)}
        self._clients_lock = threading.Lock()
        self.__socket = sock.socket(sock.AF_INET, sock.SOCK_STREAM)
        self.__socket.bind((ip, port))
        self.__socket.listen(1)
        while True:
            socket, _ = self.__socket.accept()
            threading.Thread(target=_process_connection, args=(self, Connection(prot.ClientMessage, socket))).start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.__socket.close()


def _process_connection(server: Server, conn: Connection):
    server._clients_lock.acquire()
    free_slot = next((i for i in server._clients.keys() if server._clients[i] is None), None)
    if free_slot is None:
        server._clients_lock.release()
        conn.send_message(prot.ActionRejected('Server is full'))
        conn.close()
    else:
        msg = prot.ClientMessage.deserialize(conn)
        if isinstance(msg, prot.Join):
            client = Client(conn, incoming_queue, free_slot, msg.name)
            server._clients[free_slot] = client
            server._clients_lock.release()
            threading.Thread(target=client.listen_incoming())
            client.listen_outgoing()
