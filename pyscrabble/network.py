from queue import Queue
from socket import socket, AF_INET, SOCK_STREAM
from threading import Thread
from typing import Any, Callable, Type

from pyscrabble.protocol import ClientMessage, Message


class Stream:
    def __init__(self, s: socket, in_msg_type: Type[Message]):
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
        return result

    def get_int(self, n: int=1, signed=False) -> int:
        return int.from_bytes(self.get_bytes(n), byteorder='big', signed=signed)

    def get_str(self, n: int) -> str:
        return self.get_bytes(n).decode('utf-8')

    def get_msg(self) -> Message:
        return self.__in_msg_type.deserialize(self)

    def send_message(self, msg: Message):
        self.__socket.sendall(msg.serialize())

    def close(self):
        self.__socket.close()


class StreamWorker:
    def __init__(self, stream: Stream, queue: Queue):
        self.__stream = stream
        self.__incoming_queue = queue
        self.queue = Queue()

    def listen_incoming(self):
        while True:
            self.__incoming_queue.put(self.__stream.get_msg())

    def listen_outgoing(self):
        while True:
            self.__stream.send_message(self.queue.get())


class Server:
    def __init__(self, connection_handler: Callable[[Stream], Any]):
        self.__socket = None
        self.__connection_handler = connection_handler

    def __listen_connections(self):
        while True:
            s, _ = self.__socket.accept()
            Thread(target=self.__connection_handler, args=(Stream(s, ClientMessage),)).start()

    def start(self, ip: str, port: int):
        assert not self.__socket
        self.__socket = socket(AF_INET, SOCK_STREAM)
        self.__socket.bind((ip, port))
        self.__socket.listen(1)
        Thread(target=self.__listen_connections).start()

    def stop(self):
        assert self.__socket
        self.__socket.close()
