from abc import ABC, abstractmethod
from queue import Queue
from typing import Type


class Message(ABC):
    @abstractmethod
    def serialize(self) -> bytes:
        ...

    @staticmethod
    @abstractmethod
    def deserialize(stream: 'ByteStream'):
        ...


class ByteStream(ABC):
    def __init__(self, in_msg_type: Type[Message]):
        self.__in_msg_type = in_msg_type

    @abstractmethod
    def get_bytes(self, n: int) -> bytes:
        pass

    def get_int(self, n: int=1, signed=False) -> int:
        return int.from_bytes(self.get_bytes(n), byteorder='big', signed=signed)

    def get_string(self, n: int) -> str:
        return self.get_bytes(n).decode('utf-8')

    def get_message(self) -> Message:
        return self.__in_msg_type.deserialize(self)

    @abstractmethod
    def send_bytes(self, b: bytes):
        pass

    def send_message(self, msg: Message):
        self.send_bytes(msg.serialize())

    @abstractmethod
    def close(self):
        pass


class StreamWorker:
    def __init__(self, stream: ByteStream, incoming_queue: Queue):
        self.__stream = stream
        self.__incoming_queue = incoming_queue
        self.outgoing_queue = Queue()

    def listen_incoming(self):
        while True:
            self.__incoming_queue.put(self.__stream.get_message())

    def listen_outgoing(self):
        while True:
            self.__stream.send_message(self.outgoing_queue.get())
