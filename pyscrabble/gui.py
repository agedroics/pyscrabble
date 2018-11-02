import sys
import tkinter as tk
import tkinter.messagebox
from abc import ABC, abstractmethod


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title('PyScrabble')
        self.resizable(False, False)
        self.__frame = None
        self.set_frame(MainMenu)

    def set_frame(self, frame_class):
        if self.__frame is not None:
            self.__frame.destroy()
        self.__frame = frame_class(self)
        self.__frame.pack(fill='both', padx=14, pady=10)
        self.update_idletasks()


class MainMenu(tk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master)

        tk.Button(self, text='Host Game', command=lambda: master.set_frame(HostGame), width=30)\
            .pack(fill='x', pady=(0, 6))
        tk.Button(self, text='Join Game', command=lambda: master.set_frame(JoinGame))\
            .pack(fill='x', pady=(0, 6))
        tk.Button(self, text='Exit', command=sys.exit)\
            .pack(fill='x')


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

        container = tk.LabelFrame(self, padx=4)
        container.columnconfigure(0, pad=14)
        container.columnconfigure(2, pad=14)
        container.grid(row=0, column=0, columnspan=3, pady=(0, 6))

        tk.Label(container, text='Player Name:') \
            .grid(row=0, column=0, pady=6, sticky='W')

        self.__name_entry = tk.Entry(container)
        self.__name_entry.grid(row=0, column=1, columnspan=3, padx=(0, 4), pady=6, sticky='WE')

        tk.Label(container, text='IP Address:') \
            .grid(row=1, column=0, pady=(0, 6), sticky='W')

        self.__ip_entry = tk.Entry(container, width=16)
        self.__ip_entry.insert(0, '127.0.0.1')
        self.__ip_entry.grid(row=1, column=1, padx=(0, 14), pady=(0, 6), sticky='WE')

        tk.Label(container, text='Port:') \
            .grid(row=1, column=2, pady=(0, 6), sticky='W')

        self.__port_entry = tk.Entry(container, width=6, validate='key',
                                     validatecommand=(self.register(_validate_port), '%d', '%P'))
        self.__port_entry.insert(0, 1234)
        self.__port_entry.grid(row=1, column=3, padx=(0, 4), pady=(0, 6), sticky='W')

        self._configure_container(container)

        tk.Button(self, text=button_label, command=self.__on_start_clicked) \
            .grid(ipadx=20, padx=(0, 6), row=1, column=1, sticky='E')
        tk.Button(self, text='Back', command=lambda: master.set_frame(MainMenu)) \
            .grid(ipadx=20, row=1, column=2, sticky='E')

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

        tk.Label(container, text='Turn Timer:') \
            .grid(row=2, column=0, pady=(0, 6), sticky='W')

        self.__timer_entry = tk.Entry(container, width=5, validate='key',
                                      validatecommand=(self.register(_validate_timer), '%d', '%P'))
        self.__timer_entry.insert(0, 0)
        self.__timer_entry.grid(row=2, column=1, padx=(0, 4), pady=(0, 6), sticky='W')

    def _button_action(self, name: str, ip: str, port: int):
        pass


class JoinGame(StartGame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, 'Join')

    def _configure_container(self, container: tk.LabelFrame):
        container.config(text='Join Game')

    def _button_action(self, name: str, ip: str, port: int):
        pass
