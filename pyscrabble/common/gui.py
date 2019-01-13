import sys
import tkinter as tk
import tkinter.messagebox
from abc import ABC, abstractmethod
from typing import Optional, Type

import pyscrabble.common.protocol as proto
from pyscrabble.client.connection import Connection
from pyscrabble.server.server import Server

server: 'Server' = None


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title('PyScrabble')
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.__frame = None
        self.set_frame(MainMenu(self))

    def set_frame(self, frame):
        if self.__frame:
            self.__frame.destroy()
        self.__frame = frame
        self.__frame.grid(row=0, column=0, padx=14, pady=10, sticky=tk.NSEW)
        self.update_idletasks()


class MainMenu(tk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master)

        tk.Button(self, text='Host Game', command=lambda: master.set_frame(HostGame(self.master)), width=30)\
            .pack(fill=tk.X, pady=(0, 6))
        tk.Button(self, text='Join Game', command=lambda: master.set_frame(JoinGame(self.master)))\
            .pack(fill=tk.X, pady=(0, 6))
        tk.Button(self, text='Exit', command=sys.exit)\
            .pack(fill=tk.X)


def _validate_port(action, text):
    if action == '1':
        try:
            return 1 <= int(text) < 65536
        except ValueError:
            return False
    return True


class StartGame(ABC, tk.Frame):
    def __init__(self, master: tk.Tk, button_label):
        super().__init__(master)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        container = tk.LabelFrame(self, padx=4)
        container.columnconfigure(0, pad=14)
        container.columnconfigure(1, weight=1)
        container.columnconfigure(2, pad=14)
        container.grid(row=0, column=0, columnspan=3, pady=(0, 6), sticky=tk.EW)

        tk.Label(container, text='Player Name:').grid(row=0, column=0, sticky='nsw')

        self.__name_entry = tk.Entry(container)
        self.__name_entry.grid(row=0, column=1, columnspan=3, ipady=2, padx=(0, 4), pady=6, sticky=tk.EW)

        tk.Label(container, text='IP Address:').grid(row=1, column=0, sticky=tk.NW)

        self.__ip_entry = tk.Entry(container, width=16)
        self.__ip_entry.insert(0, '127.0.0.1')
        self.__ip_entry.grid(row=1, column=1, ipady=2, padx=(0, 14), pady=(0, 6), sticky=tk.EW)

        tk.Label(container, text='Port:') .grid(row=1, column=2, sticky=tk.NW)

        self.__port_entry = tk.Entry(container, width=6, validate='key',
                                     validatecommand=(self.register(_validate_port), '%d', '%P'))
        self.__port_entry.insert(0, 1234)
        self.__port_entry.grid(row=1, column=3, ipady=2, padx=(0, 4), pady=(0, 6), sticky=tk.W)

        self._configure_container(container)

        tk.Button(self, text=button_label, command=self.__on_start_clicked) \
            .grid(ipadx=20, padx=(0, 6), row=1, column=1, sticky=tk.SE)
        tk.Button(self, text='Back', command=lambda: master.set_frame(MainMenu(self.master))) \
            .grid(ipadx=20, row=1, column=2, sticky=tk.SE)

    def __on_start_clicked(self):
        name = self.__name_entry.get().strip()
        if name == '':
            tk.messagebox.showwarning('Warning', 'Please enter your name!')
        else:
            self._button_action(name, self.__ip_entry.get(), int(self.__port_entry.get()))

    @abstractmethod
    def _configure_container(self, container: tk.LabelFrame):
        pass

    @abstractmethod
    def _button_action(self, name: str, ip: str, port: int):
        pass


def _validate_timer(action, text):
    if action == '1':
        try:
            return 0 <= int(text) < 10000
        except ValueError:
            return False
    return True


class HostGame(StartGame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, 'Start')

    def _configure_container(self, container: tk.LabelFrame):
        container.config(text='Host Game')

        tk.Label(container, text='Turn Timer:').grid(row=2, column=0, sticky=tk.NW)

        self.__timer_entry = tk.Entry(container, width=5, validate='key',
                                      validatecommand=(self.register(_validate_timer), '%d', '%P'))
        self.__timer_entry.insert(0, 0)
        self.__timer_entry.grid(row=2, column=1, ipady=2, padx=(0, 4), pady=(0, 6), sticky=tk.W)

    def _button_action(self, name: str, ip: str, port: int):
        global server
        server = Server()
        try:
            server.start(ip, port)
            try:
                self.master.set_frame(GameFrame(self.master, name, ip, port))
            except IOError as e:
                tk.messagebox.showerror('Error', e)
                server.stop()
                server = None
        except IOError as e:
            tk.messagebox.showerror('Error', e)
            server = None


class JoinGame(StartGame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, 'Join')

    def _configure_container(self, container: tk.LabelFrame):
        container.config(text='Join Game')

    def _button_action(self, name: str, ip: str, port: int):
        try:
            self.master.set_frame(GameFrame(self.master, name, ip, port))
        except IOError as e:
            tk.messagebox.showerror('Error', e)


class ChatFrame(tk.Frame):
    def __init__(self, parent, conn: 'Connection'):
        super().__init__(parent)
        self.__conn = conn

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.__txt = tk.Text(self, state=tk.DISABLED, wrap=tk.WORD, width=30)
        self.__txt.grid(row=0, column=0, columnspan=2, pady=(0, 6), sticky=tk.NSEW)

        scrollbar = tk.Scrollbar(self, orient=tk.VERTICAL, command=self.__txt.yview)
        scrollbar.grid(row=0, column=2, pady=(0, 6), sticky=tk.NS)

        self.__txt['yscrollcommand'] = scrollbar.set

        self.__text_entry = tk.Entry(self)
        self.__text_entry.bind('<Return>', self.__on_send)
        self.__text_entry.grid(row=1, column=0, ipady=2, sticky=tk.EW)

        tk.Button(self, text='Send', command=self.__on_send)\
            .grid(row=1, column=1, columnspan=2, ipadx=20, padx=(6, 0), sticky=tk.EW)

    def __on_send(self, *_):
        text = self.__text_entry.get()
        if text:
            self.__conn.worker.queue_out.put(proto.Chat(self.__text_entry.get()))
            self.__text_entry.delete(0, tk.END)

    def add_text(self, text: str):
        self.__txt.config(state=tk.NORMAL)
        self.__txt.insert(tk.END, f'{text}\n')
        self.__txt.config(state=tk.DISABLED)
        self.__txt.yview_moveto(1)


class LobbyFrame(tk.Frame):
    def __init__(self, parent, conn: 'Connection'):
        super().__init__(parent)

        self.__conn = conn
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.__players_frame = tk.LabelFrame(self, text='Players', padx=4)
        self.__players_frame.columnconfigure(0, weight=1)
        self.__players_frame.grid(row=0, column=0, columnspan=2, pady=(0, 6), sticky=tk.NSEW)

        tk.Button(self, text='Ready', command=self.__on_ready)\
            .grid(row=1, column=0, ipadx=20, padx=(0, 6), sticky=tk.E)

        tk.Button(self, text='Back', command=self.__on_back)\
            .grid(row=1, column=1, ipadx=20, sticky=tk.E)

    def __on_ready(self):
        self.__conn.worker.queue_out.put(proto.Ready())

    def __on_back(self):
        self.__conn.stop()
        global server
        if server:
            server.stop()
            server = None

    def update(self):
        for slave in self.__players_frame.grid_slaves():
            slave.destroy()
        for i, client in enumerate(self.__conn.game.clients.values()):
            tk.Label(self.__players_frame, text=client.name)\
                .grid(row=i, column=0, pady=(2, 0), sticky=tk.W)
            tk.Label(self.__players_frame, text='READY' if client.ready else '')\
                .grid(row=i, column=1, pady=(2, 0), sticky=tk.E)


class GameFrame(tk.PanedWindow):
    def __init__(self, master: tk.Tk, name: str, ip: str, port: int):
        super().__init__(master, orient=tk.HORIZONTAL, sashwidth=6)

        conn = Connection(self.__on_update)

        self.__lobby_frame = LobbyFrame(self, conn)
        self.add(self.__lobby_frame, width=250, stretch='always')

        self.__chat_frame = ChatFrame(self, conn)
        self.add(self.__chat_frame, stretch='never')

        conn.start(ip, port, name)

    def __on_update(self, src_type: Type[proto.ServerMessage], text: Optional[str]):
        if text:
            self.__chat_frame.add_text(text)
        if src_type == proto.Shutdown:
            self.master.set_frame(MainMenu(self.master))
        elif src_type == proto.ActionRejected:
            tk.messagebox.showwarning('Warning', text)
        elif src_type in _update_msgs:
            self.__lobby_frame.update()


_update_msgs = {proto.JoinOk, proto.PlayerJoined, proto.PlayerReady}
