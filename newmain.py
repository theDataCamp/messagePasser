import tkinter as tk
from tkinter import ttk, StringVar
import socket
import threading
from pynput import keyboard
import pyautogui

# Constants
PORT = 65432
BUFFER_SIZE = 1024

MACROS = {
    frozenset([keyboard.Key.ctrl, keyboard.Key.alt, keyboard.KeyCode.from_char('r')]): {'type': 'PRESS_KEY', 'action': 'right'},
    frozenset([keyboard.Key.ctrl, keyboard.Key.alt, keyboard.KeyCode.from_char('t')]): {'type': 'TYPE_TEXT', 'action': 'Hello World'}
}

class AppGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("Master/Slave Selector")

        self.frame = ttk.LabelFrame(self.master, text="Settings", padding=(20, 10))
        self.frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        self.ip_label = ttk.Label(self.frame, text="IP Address:")
        self.ip_label.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)

        self.ip_var = StringVar(value="127.0.0.1")  # Default to localhost
        self.ip_entry = ttk.Entry(self.frame, textvariable=self.ip_var)
        self.ip_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)

        self.role_var = StringVar()
        self.master_radio = ttk.Radiobutton(self.frame, text="Master", value="Master", variable=self.role_var)
        self.master_radio.grid(row=1, column=0, padx=5, pady=5)

        self.slave_radio = ttk.Radiobutton(self.frame, text="Slave", value="Slave", variable=self.role_var)
        self.slave_radio.grid(row=1, column=1, padx=5, pady=5)

        self.start_button = ttk.Button(self.frame, text="Start", command=self.start_role)
        self.start_button.grid(row=2, column=0, columnspan=2, pady=10)
        self.frame.columnconfigure(1, weight=1)

    def start_role(self):
        role = self.role_var.get()
        ip_address = self.ip_var.get()
        if role == "Master":
            self.conn_manager = ConnectionManager(is_master=True, host=ip_address)
            self.hotkey_manager = HotkeyManager(self.conn_manager)
        elif role == "Slave":
            self.conn_manager = ConnectionManager(is_master=False, host=ip_address)


class ConnectionManager:
    def __init__(self, is_master=True, host='127.0.0.1'):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if is_master:
            threading.Thread(target=self.start_master).start()
        else:
            threading.Thread(target=self.start_slave).start()
        self.host = host

    def start_master(self):
        self.s.bind((self.host, PORT))
        self.s.listen()
        self.conn, addr = self.s.accept()
        with self.conn:
            print('Connected by', addr)
            while True:
                command = self.conn.recv(BUFFER_SIZE).decode('utf-8')
                if not command:
                    break
                self.execute_command_on_slave(command)

    def start_slave(self):
        self.s.connect((self.host, PORT))

    def send_command(self, command):
        self.conn.sendall(command.encode('utf-8'))

    @staticmethod
    def execute_command_on_slave(command):
        cmd_type, cmd_action = command.split(":")

        if cmd_type == 'PRESS_KEY':
            pyautogui.press(cmd_action)
        elif cmd_type == 'TYPE_TEXT':
            pyautogui.write(cmd_action)


class HotkeyManager:
    def __init__(self, conn_manager):
        self.conn_manager = conn_manager
        self.listener = keyboard.Listener(on_press=self.on_key_down, on_release=self.on_key_up)
        self.current_keys = set()
        self.listener.start()

    def on_key_down(self, key):
        if any([key in combo for combo in MACROS.keys()]):
            self.current_keys.add(key)
            self.on_activate()

    def on_key_up(self, key):
        self.current_keys.discard(key)

    def on_activate(self):
        action = MACROS.get(frozenset(self.current_keys))
        if action:
            if action['type'] == 'PRESS_KEY':
                print(f'Hotkey for pressing key {action["action"]} activated')
                self.conn_manager.send_command(f'PRESS_KEY:{action["action"]}')
            elif action['type'] == 'TYPE_TEXT':
                print(f'Hotkey for typing text "{action["action"]}" activated')
                self.conn_manager.send_command(f'TYPE_TEXT:{action["action"]}')


if __name__ == "__main__":
    root = tk.Tk()
    app = AppGUI(root)
    root.mainloop()