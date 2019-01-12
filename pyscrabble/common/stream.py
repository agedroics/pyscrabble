import socket
from queue import Queue
from typing import Type


class Stream:
    def __init__(self, s: socket.socket, in_msg_type: Type['proto.Message']):
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
                print(self.__buffer)
                if not self.__buffer:
                    self.__socket.close()
                    break
        return result

    def get_int(self, n: int = 1, signed=False) -> int:
        return int.from_bytes(self.get_bytes(n), byteorder='big', signed=signed)

    def get_str(self, n: int) -> str:
        return self.get_bytes(n).decode('utf-8')

    def get_msg(self) -> 'proto.Message':
        return self.__in_msg_type.deserialize(self)

    def send_msg(self, msg: 'proto.Message'):
        self.__socket.sendall(msg.serialize())

    def close(self):
        self.__socket.close()


class StreamWorker:
    def __init__(self, stream: 'Stream', queue_in: Queue):
        self.__stream = stream
        self.__queue_in = queue_in
        self.queue_out = Queue()

    def listen_incoming(self, *extra_info):
        try:
            while True:
                msg = self.__stream.get_msg()
                if msg:
                    self.__queue_in.put((msg, *extra_info))
                else:
                    self.__queue_in.put((proto.Leave(), *extra_info))
                    break
        except socket.error:
            self.__queue_in.put((proto.Leave(), *extra_info))
        finally:
            self.__stream.close()

    def listen_outgoing(self, *extra_info):
        try:
            while True:
                msg = self.queue_out.get()
                if msg:
                    self.__stream.send_msg(msg)
                else:
                    break
        except socket.error:
            self.__queue_in.put((proto.Leave(), *extra_info))
        finally:
            self.__stream.close()


import pyscrabble.common.protocol as proto
