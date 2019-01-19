import sys
import tkinter as tk
import tkinter.messagebox
from abc import ABC, abstractmethod
from tkinter import simpledialog
from typing import Tuple, Optional, List, Callable, Any, Dict, Set

import pyscrabble.protocol as proto
from pyscrabble.client import Connection
from pyscrabble.model import SquareType, Tile
from pyscrabble.server import Server

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
        if isinstance(frame, GameFrame):
            self.resizable(True, False)
        else:
            self.minsize(0, 0)
            self.geometry('')
            self.resizable(False, False)
        frame.grid(row=0, column=0, padx=14, pady=10, sticky=tk.NSEW)
        self.__frame = frame
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

        tk.Label(container, text='Player Name:').grid(row=0, column=0, pady=6, sticky=tk.W)

        self.__name_entry = tk.Entry(container)
        self.__name_entry.bind('<Return>', self.__on_start_clicked)
        self.__name_entry.grid(row=0, column=1, columnspan=3, ipady=2, padx=(0, 4), pady=6, sticky=tk.EW)

        tk.Label(container, text='IP Address:').grid(row=1, column=0, pady=(0, 6), sticky=tk.W)

        self.__ip_entry = tk.Entry(container, width=16)
        self.__ip_entry.bind('<Return>', self.__on_start_clicked)
        self.__ip_entry.insert(0, '127.0.0.1')
        self.__ip_entry.grid(row=1, column=1, ipady=2, padx=(0, 14), pady=(0, 6), sticky=tk.EW)

        tk.Label(container, text='Port:').grid(row=1, column=2, pady=(0, 6), sticky=tk.W)

        self.__port_entry = tk.Entry(container, width=6, validate='key',
                                     validatecommand=(self.register(_validate_port), '%d', '%P'))
        self.__port_entry.bind('<Return>', self.__on_start_clicked)
        self.__port_entry.insert(0, 1234)
        self.__port_entry.grid(row=1, column=3, ipady=2, padx=(0, 4), pady=(0, 6))

        self._configure_container(container)

        tk.Button(self, text=button_label, command=self.__on_start_clicked) \
            .grid(ipadx=20, padx=(0, 6), row=1, column=1, sticky=tk.SE)
        tk.Button(self, text='Back', command=lambda: master.set_frame(MainMenu(self.master))) \
            .grid(ipadx=20, row=1, column=2, sticky=tk.SE)

    def __on_start_clicked(self, event=None):
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


class HostGame(StartGame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, 'Start')

    def _configure_container(self, container: tk.LabelFrame):
        container.config(text='Host Game')

        tk.Label(container, text='Language:').grid(row=2, column=0, pady=(0, 6), sticky=tk.W)

        self.__lang = tk.StringVar()
        self.__lang.set('en')

        tk.OptionMenu(container, self.__lang, 'en', 'lv')\
            .grid(row=2, column=1, pady=(0, 6), sticky=tk.W)

    def _button_action(self, name: str, ip: str, port: int):
        global server
        server = Server(self.__lang.get())
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


class AutoScrollbar(tk.Scrollbar):
    def set(self, lo, hi):
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            self.grid_remove()
        else:
            self.grid()
        tk.Scrollbar.set(self, lo, hi)


class ChatFrame(tk.Frame):
    def __init__(self, parent, conn: 'Connection'):
        super().__init__(parent)
        self.__conn = conn

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.__txt = tk.Text(self, state=tk.DISABLED, wrap=tk.WORD, width=40, background='white',
                             borderwidth=1, relief=tk.SUNKEN)
        self.__txt.grid(row=0, column=0, columnspan=2, pady=(0, 6), sticky=tk.NSEW)

        scrollbar = AutoScrollbar(self, orient=tk.VERTICAL, command=self.__txt.yview)
        scrollbar.grid(row=0, column=2, pady=(0, 6), sticky=tk.NS)

        self.__txt.configure(yscrollcommand=scrollbar.set)

        self.__text_entry = tk.Entry(self)
        self.__text_entry.bind('<Return>', self.__on_send)
        self.__text_entry.grid(row=1, column=0, ipady=2, sticky=tk.EW)

        tk.Button(self, text='Send', command=self.__on_send)\
            .grid(row=1, column=1, columnspan=2, ipadx=20, padx=(6, 0), sticky=tk.EW)

    def __on_send(self, *_):
        text = self.__text_entry.get()
        if text:
            self.__conn.send_msg(proto.Chat(self.__text_entry.get()))
            self.__text_entry.delete(0, tk.END)

    def add_text(self, text: str):
        self.__txt.config(state=tk.NORMAL)
        self.__txt.insert(tk.END, f'{text}\n')
        self.__txt.config(state=tk.DISABLED)
        self.__txt.yview_moveto(1)

    def scroll_to_bottom(self):
        self.__txt.yview_moveto(1)


class LobbyFrame(tk.Frame):
    def __init__(self, parent, conn: 'Connection'):
        super().__init__(parent)

        self.__conn = conn
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.__players_frame = tk.LabelFrame(self, text='Players', padx=4)
        self.__players_frame.columnconfigure(0, weight=1)
        self.__players_frame.grid(row=0, column=0, columnspan=3, pady=(0, 6), sticky=tk.NSEW)

        tk.Button(self, text='Ready', command=self.__on_ready)\
            .grid(row=1, column=1, ipadx=20, padx=(0, 6), sticky=tk.E)

        tk.Button(self, text='Back', command=self.__on_back)\
            .grid(row=1, column=2, ipadx=20, sticky=tk.E)

    def __on_ready(self):
        self.__conn.send_msg(proto.Ready())

    def __on_back(self):
        self.__conn.stop()
        global server
        if server:
            server.stop()
            server = None

    def update_contents(self):
        for slave in self.__players_frame.grid_slaves():
            slave.destroy()
        for i, client in enumerate(self.__conn.game.clients.values()):
            tk.Label(self.__players_frame, text=client.name, width=30, anchor=tk.W)\
                .grid(row=i, column=0, pady=(2, 0), sticky=tk.W)
            tk.Label(self.__players_frame, text='READY' if client.ready else '', width=5, anchor=tk.E)\
                .grid(row=i, column=1, padx=(6, 0), pady=(2, 0), sticky=tk.E)


class BoardCanvas(tk.Canvas):
    def __init__(self, parent, conn: 'Connection', on_tile_dropped: Callable[['Tile', int, int, bool], Any]):
        super().__init__(parent, width=750, height=750, scrollregion=(0, 0, 750, 750), relief=tk.SUNKEN, bd=1)

        self.__conn = conn
        self.__on_tile_dropped = on_tile_dropped

        self.bind('<Button-1>', self.__on_press)
        self.bind('<ButtonRelease-1>', self.__on_release)
        self.bind('<ButtonRelease-3>', self.__on_right_release)

        self.temp_tiles: Dict[int, Dict[int, Tuple[Tile, List[int]]]] = {}
        self.__picked_up_tile: 'Tile' = None

    __lookup = {
        SquareType.NORMAL: (None, '#d2c5ac', None),
        SquareType.DLS: ('DOUBLE LETTER SCORE', '#bcd4d1', 'black'),
        SquareType.TLS: ('TRIPLE LETTER SCORE', '#31a2b3', 'white'),
        SquareType.DWS: ('DOUBLE WORD SCORE', '#ffbdaf', 'black'),
        SquareType.TWS: ('TRIPLE WORD SCORE', '#ff6154', 'white')
    }

    def __on_press(self, event):
        with self.__conn.game.lock:
            row = int(min(self.canvasy(event.y), 749) // 50)
            col = int(min(self.canvasx(event.x), 749) // 50)
            if row in self.temp_tiles and col in self.temp_tiles[row]:
                self.__picked_up_tile = self.temp_tiles[row][col][0]

    def __on_release(self, event):
        with self.__conn.game.lock:
            if self.__picked_up_tile and self.__conn.game.player_turn:
                x = self.winfo_rootx() + event.x
                y = self.winfo_rooty() + event.y
                self.__on_tile_dropped(self.__picked_up_tile, x, y, True)
                self.__picked_up_tile = None

    def __on_right_release(self, event):
        self.__on_press(event)
        event.x = -1
        event.y = -1
        self.__on_release(event)

    def redraw(self):
        self.temp_tiles = {}
        self.__picked_up_tile = None
        self.delete(tk.ALL)
        tiles = []
        for row, squares in enumerate(self.__conn.game.board.squares):
            for col, square in enumerate(squares):
                if square.tile:
                    tiles.append((row, col, square.tile))
                else:
                    text, bg_color, text_color = BoardCanvas.__lookup[square.type]
                    self.create_rectangle(col * 50, row * 50, col * 50 + 50, row * 50 + 50,
                                          fill=bg_color, width=2, outline='#f0f0f0')
                    if row == 7 and col == 7:
                        self.create_text(col * 50 + 25, row * 50 + 25,
                                         text='★', font=('Helvetica', 30), fill=text_color)
                    elif text:
                        for i, string in enumerate(text.split(sep=' ')):
                            self.create_text(col * 50 + 25, row * 50 + 13 + i * 12,
                                             text=string, font=('Helvetica', 6, 'bold'), fill=text_color)
        for row, col, tile in tiles:
            self.draw_tile(row, col, tile)

    def draw_tile(self, row: int, col: int, tile: 'Tile', temp: bool = False):
        items = [
            self.create_rectangle(col * 50, row * 50, col * 50 + 50, row * 50 + 50,
                                  fill='#f8f3e2', width=2, outline='red' if temp else 'black'),
            self.create_text(col * 50 + 21, row * 50 + 23, text=tile.letter, font=('Helvetica', 22)),
            self.create_text(col * 50 + 33, row * 50 + 35, text=tile.points, anchor=tk.W, font=('Helvetica', 8, 'bold'))
        ]
        if temp:
            if row not in self.temp_tiles:
                self.temp_tiles[row] = {}
            self.temp_tiles[row][col] = (tile, items)

    def delete_tile(self, tile: 'Tile'):
        for row, tiles in self.temp_tiles.items():
            for col, (tile_, items) in tiles.items():
                if tile_ == tile:
                    for item in items:
                        self.delete(item)
                    del self.temp_tiles[row][col]
                    if not self.temp_tiles[row]:
                        del self.temp_tiles[row]
                    return


class TilesCanvas(tk.Canvas):
    def __init__(self, parent, conn: 'Connection', on_tile_dropped: Callable[['Tile', int, int, bool], Any]):
        super().__init__(parent, relief=tk.RAISED, bd=1)

        self.__conn = conn
        self.__on_tile_dropped = on_tile_dropped

        self.__tiles: List['Tile'] = []
        self.__picked_up_tile: 'Tile' = None
        self.bind('<Button-1>', self.__on_press)
        self.bind('<ButtonRelease-1>', self.__on_release)

        self.exchange_mode = False
        self.selected_tiles: Set['Tile'] = None
        self.__selection_items: Dict['Tile', List[int]] = {}
        self.on_selection_change: Callable[[List['Tile']], Any] = None

    def unselect_tiles(self):
        if self.__selection_items:
            for tile in self.__selection_items:
                for item in self.__selection_items[tile]:
                    self.delete(item)
            self.__selection_items = {}

    def __on_press(self, event):
        with self.__conn.game.lock:
            i = min(event.x // 50, len(self.__tiles) - 1)
            tile = self.__tiles[i]
            if self.exchange_mode:
                if tile in self.selected_tiles:
                    for item in self.__selection_items[tile]:
                        self.delete(item)
                    del self.__selection_items[tile]
                    self.selected_tiles.remove(tile)
                else:
                    self.selected_tiles.add(tile)
                    self.__selection_items[tile] = [
                        self.create_line(i * 50, 0, (i + 1) * 50, 50, width=2),
                        self.create_line(i * 50, 50, (i + 1) * 50, 0, width=2)
                    ]
                if self.on_selection_change:
                    self.on_selection_change(self.selected_tiles)
            else:
                self.__picked_up_tile = tile

    def __on_release(self, event):
        with self.__conn.game.lock:
            if self.__picked_up_tile and self.__conn.game.player_turn:
                x = self.winfo_rootx() + event.x
                y = self.winfo_rooty() + event.y
                self.__on_tile_dropped(self.__picked_up_tile, x, y, False)
                self.__picked_up_tile = None

    def redraw(self):
        self.__tiles = []
        self.__picked_up_tile = None
        self.delete(tk.ALL)
        for tile in self.__conn.game.player_client.player.tiles:
            self.draw_tile(tile)

    def draw_tile(self, tile: 'Tile'):
        i = len(self.__tiles)
        self.create_rectangle(i * 50, 0, i * 50 + 50, 50, fill='#f8f3e2', width=2, outline='black')
        if tile.letter:
            self.create_text(i * 50 + 21, 23, text=tile.letter, font=('Helvetica', 22))
            self.create_text(i * 50 + 33, 35, text=tile.points, anchor=tk.W, font=('Helvetica', 8, 'bold'))
        self.__tiles.append(tile)
        tile_count = len(self.__tiles)
        width = 50 * tile_count
        self.configure(width=width, height=50, scrollregion=(0, 0, width, 50))
        if tile_count == 1:
            self.grid()

    def delete_tile(self, tile: 'Tile'):
        for i, tile_ in enumerate(self.__tiles):
            if tile == tile_:
                del self.__tiles[i]
                tiles = self.__tiles
                self.__tiles = []
                self.delete(tk.ALL)
                for tile in tiles:
                    self.draw_tile(tile)
                if not self.__tiles:
                    self.grid_remove()
                break


class ScrabbleFrame(tk.Frame):
    def __init__(self, parent, conn: 'Connection'):
        super().__init__(parent)

        self.__conn = conn
        self.columnconfigure(0, weight=1)

        self.__board = BoardCanvas(self, conn, self.__on_tile_dropped)
        self.__board.grid(row=0, column=0, columnspan=5, pady=(0, 6), sticky=tk.NSEW)

        self.__tiles = TilesCanvas(self, conn, self.__on_tile_dropped)
        self.__tiles.grid(row=1, rowspan=2, column=0, sticky=tk.E)
        self.__tiles.on_selection_change = self.__on_selection_change

        self.__exchange_btn = tk.Button(self, command=self.__on_exchange)
        self.__exchange_btn.grid(row=1, column=1, ipadx=20, padx=(6, 0), sticky=tk.EW)

        self.__end_turn_btn = tk.Button(self, command=self.__on_end_turn, width=15)
        self.__end_turn_btn.grid(row=2, column=1, ipadx=20, padx=(6, 0), pady=(6, 0), sticky=tk.EW)

    def update_contents(self):
        self.__board.redraw()
        self.__tiles.redraw()
        self.__cancel_exchange()
        if self.__conn.game.player_turn:
            self.__end_turn_btn.configure(state=tk.NORMAL, text='Skip turn')
        else:
            self.__end_turn_btn.configure(state=tk.DISABLED, text='Skip turn')

        if not self.__conn.game.player_turn or self.__conn.game.tiles_left < 7:
            self.__exchange_btn.configure(state=tk.DISABLED)

    def __on_end_turn(self):
        with self.__conn.game.lock:
            if self.__tiles.exchange_mode:
                tile_ids = [tile.id for tile in self.__tiles.selected_tiles]
                self.__conn.send_msg(proto.TileExchange(tile_ids))
                self.__cancel_exchange()
            else:
                tile_placements: List['proto.PlaceTilesTile'] = []
                for row in self.__board.temp_tiles:
                    for col in self.__board.temp_tiles[row]:
                        tile, _ = self.__board.temp_tiles[row][col]
                        tile_placement = proto.PlaceTilesTile(row * 15 + col, tile.id, tile.letter if not tile.points else None)
                        tile_placements.append(tile_placement)
                self.__conn.send_msg(proto.PlaceTiles(tile_placements))

    def __on_exchange(self):
        with self.__conn.game.lock:
            if self.__tiles.exchange_mode:
                self.__cancel_exchange()
            else:
                self.__tiles.exchange_mode = True
                self.__tiles.selected_tiles = set()
                self.__exchange_btn.configure(text='Cancel')
                self.__end_turn_btn.configure(state=tk.DISABLED, text='Select tiles...')

    def __on_selection_change(self, tiles: List['Tile']):
        if tiles:
            self.__end_turn_btn.configure(state=tk.NORMAL, text='Exchange')
        else:
            self.__end_turn_btn.configure(state=tk.DISABLED, text='Select tiles...')

    def __cancel_exchange(self):
        self.__tiles.exchange_mode = False
        self.__exchange_btn.configure(state=tk.NORMAL, text='Exchange tiles')
        self.__end_turn_btn.configure(state=tk.NORMAL, text='End turn' if self.__board.temp_tiles else 'Skip turn')
        self.__tiles.unselect_tiles()

    def __on_tile_dropped(self, tile: 'Tile', x: int, y: int, from_board: bool):
        if self.__board == self.winfo_containing(x, y):
            x = self.__board.canvasx(x - self.__board.winfo_rootx())
            y = self.__board.canvasy(y - self.__board.winfo_rooty())
            row = int(min(y, 749) // 50)
            col = int(min(x, 749) // 50)
            square = self.__conn.game.board.squares[row][col]
            temp_tile = None
            if row in self.__board.temp_tiles and col in self.__board.temp_tiles[row]:
                temp_tile = self.__board.temp_tiles[row][col]
            if not square.tile and not temp_tile:
                canceled = False
                if from_board:
                    self.__board.delete_tile(tile)
                else:
                    while not tile.letter and not canceled:
                        letter = simpledialog.askstring('Input', 'Enter a letter for the blank tile')
                        if letter is None:
                            canceled = True
                        else:
                            letter = letter.upper()
                            if len(letter) != 1 or ord(letter) not in range(ord('A'), ord('Z') + 1):
                                tk.messagebox.showwarning('Warning', 'Input must be one letter from the English alphabet!')
                            else:
                                tile.letter = letter
                    if not canceled:
                        self.__tiles.delete_tile(tile)
                if not canceled:
                    self.__board.draw_tile(row, col, tile, True)
                    self.__end_turn_btn.configure(text='End turn')
        elif from_board:
            self.__board.delete_tile(tile)
            if not self.__board.temp_tiles:
                self.__end_turn_btn.configure(text='Skip turn')
            if tile.points == 0:
                tile.letter = None
            self.__tiles.draw_tile(tile)


class InfoFrame(tk.Frame):
    def __init__(self, parent, conn: 'Connection'):
        super().__init__(parent)

        self.__conn = conn
        self.columnconfigure(0, weight=1)

        self.__tiles_left_lbl = tk.Label(self)
        self.__tiles_left_lbl.grid(row=0, column=0, padx=(0, 6), sticky=tk.W)

        tk.Button(self, text='Leave', command=self.__on_leave)\
            .grid(row=0, column=1, ipadx=20, sticky=tk.E)

        self.__players_frame = tk.Frame(self, bd=1, relief=tk.SUNKEN, padx=2)
        self.__players_frame.columnconfigure(1, weight=1)
        self.__players_frame.grid(row=1, column=0, columnspan=2, pady=(6, 0), sticky=tk.NSEW)

    def redraw(self):
        if self.__conn.game.lobby:
            self.grid_remove()
        else:
            self.grid()
            self.update_contents()

    def update_contents(self):
        for slave in self.__players_frame.grid_slaves():
            slave.destroy()
        tk.Label(self.__players_frame, text='Name', font=('Helvetica', 9, 'bold'))\
            .grid(row=0, column=1, pady=(2, 0), sticky=tk.W)
        tk.Label(self.__players_frame, text='Tiles', font=('Helvetica', 9, 'bold'))\
            .grid(row=0, column=2, padx=(6, 0), pady=(2, 0), sticky=tk.E)
        tk.Label(self.__players_frame, text='Score', font=('Helvetica', 9, 'bold'))\
            .grid(row=0, column=3, padx=(6, 0), pady=(2, 0), sticky=tk.E)
        for i, client in enumerate(self.__conn.game.clients.values()):
            if self.__conn.game.turn_player_id == client.player_id:
                tk.Label(self.__players_frame, text='▶')\
                    .grid(row=i + 1, column=0, pady=(0, 2))
            tk.Label(self.__players_frame, text=client.name, width=30, anchor=tk.W)\
                .grid(row=i + 1, column=1, pady=(0, 2), sticky=tk.W)
            tk.Label(self.__players_frame, text=client.tile_count, width=1, anchor=tk.E)\
                .grid(row=i + 1, column=2, padx=(6, 0), pady=(0, 2), sticky=tk.E)
            tk.Label(self.__players_frame, text=client.player.score)\
                .grid(row=i + 1, column=3, padx=(6, 0), pady=(0, 2), sticky=tk.E)
        self.__tiles_left_lbl.configure(text=f'Tiles left: {self.__conn.game.tiles_left}',
                                        fg='red' if self.__conn.game.tiles_left < 7 else 'black')

    def __on_leave(self):
        self.__conn.stop()
        global server
        if server:
            server.stop()
            server = None


class GameFrame(tk.Frame):
    _update_msgs = {
        proto.JoinOk,
        proto.PlayerJoined,
        proto.PlayerLeft,
        proto.PlayerReady,
        proto.StartTurn,
        proto.EndTurn,
        proto.EndGame
    }

    def __init__(self, master: tk.Tk, name: str, ip: str, port: int):
        super().__init__(master)

        self.__conn = Connection(lambda msg, text: self.after_idle(self.__on_update, msg, text))
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        self.__chat_frame = ChatFrame(self, self.__conn)
        self.__chat_frame.grid(row=1, column=1, sticky=tk.NSEW)

        self.info_frame = InfoFrame(self, self.__conn)
        self.info_frame.grid(row=0, column=1, pady=(0, 6), sticky=tk.EW)

        self.__active_frame = None
        self.__set_active_frame(LobbyFrame(self, self.__conn))

        self.__conn.start(ip, port, name)

    def __on_update(self, msg: 'proto.ServerMessage', text: Optional[str]):
        with self.__conn.game.lock:
            if text:
                self.__chat_frame.add_text(text)

            if isinstance(msg, proto.Shutdown):
                self.master.set_frame(MainMenu(self.master))
            elif isinstance(msg, proto.ActionRejected):
                tk.messagebox.showwarning('Warning', msg.reason)
            elif isinstance(msg, proto.StartTurn):
                if isinstance(self.__active_frame, LobbyFrame):
                    self.__set_active_frame(ScrabbleFrame(self, self.__conn))
                if self.__conn.game.player_turn:
                    self.master.deiconify()
                    self.master.focus_force()
            elif isinstance(msg, proto.EndGame):
                msg.players.sort(key=lambda player: player.score, reverse=True)
                text = '\n'.join(f'{i + 1}. {self.__conn.game.clients[player.player_id].name}: {player.score} points'
                                 for i, player in enumerate(msg.players))
                tk.messagebox.showinfo('Game over!', text)
                self.__set_active_frame(LobbyFrame(self, self.__conn))

            if msg.__class__ in GameFrame._update_msgs:
                self.__active_frame.update_contents()
                self.info_frame.redraw()
        self.update_idletasks()

    def __set_active_frame(self, frame: tk.Frame):
        if self.__active_frame:
            self.__active_frame.destroy()
        frame.grid(row=0, rowspan=2, column=0, padx=(0, 6), sticky=tk.NSEW)
        self.__active_frame = frame
        root = self.winfo_toplevel()
        root.minsize(0, 0)
        root.geometry('')

        def adjust_window():
            root.minsize(root.winfo_width(), 0)
            self.__chat_frame.scroll_to_bottom()

        self.after(100, adjust_window)
