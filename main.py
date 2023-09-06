import socket
import json
import hashlib
import time
import random
from contextlib import contextmanager
from tkinter.ttk import Scrollbar, Combobox

from pynput import keyboard
import pyautogui
from tkinter import Tk, StringVar, Radiobutton, Entry, Button, Label, messagebox, simpledialog, Listbox, Menu, Toplevel
import threading
import sqlite3

# Constants and shared functions

HOST = '10.0.0.221'
PORT = 65432
SHARED_SECRET = "JosueAlemanIsASecretPassword"
DB_NAME = "macros.db"
is_macros_updated = False

MACROS = {
    "ctrl_l+alt_l+r": ["KEYS:right"],
    "ctrl_l+alt_l+l": ["KEYS:left"],
    "ctrl_l+alt_l+f": ["KEYS:f8"],
    "ctrl_l+alt_l+.": ["KEYS:ctrl_l+right"],
    "ctrl_l+alt_l+,": ["KEYS:ctrl_l+left"]
}

key_press_times = {}


@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        yield c
    finally:
        conn.commit()
        conn.close()


def initialize_db():
    with get_db_connection() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS macros(hotkey TEXT PRIMARY KEY, action TEXT)''')


def execute_db_query(query, params=()):
    with get_db_connection() as c:
        try:
            c.execute(query, params)
        except sqlite3.Error as e:
            print(f"Database error: {e}")


# Load existing macros from the database into MACROS dictionary
def load_macros_from_db():
    global MACROS
    with get_db_connection() as c:
        for hotkey, action in c.execute('SELECT * FROM macros'):
            MACROS[hotkey] = action.split(',')


def on_key_press(key):
    key_name = getattr(key, 'char', None) or key.name
    print(f"Key pressed: {key_name}")
    key_press_times[key_name] = time.time()


def keys_pressed_recently(keys, window=0.5):
    return all(key_press_times.get(key, 0) >= time.time() - window for key in keys)


def process_and_send_command(user_input, sock):
    if user_input.startswith("EXIT:"):
        payload = {"type": "exit"}
    elif user_input.startswith("TEXT:"):
        text = user_input[len("TEXT:"):].strip()
        payload = {"type": "text", "data": text}
    elif user_input.startswith("KEYS:"):
        keys = user_input[len("KEYS:"):].strip().split('+')
        payload = {"type": "keys", "data": keys}
    else:
        print("Invalid command. Please use TEXT:, KEYS:, or EXIT: as a prefix.")
        return

    message = json.dumps(payload)
    sock.sendall(message.encode('utf-8'))


def hash_challenge(challenge):
    return hashlib.sha256((challenge + SHARED_SECRET).encode()).hexdigest()


# Master functions
def send_data_to_slave():
    with socket.create_connection((HOST, PORT)) as sock:
        # Receive challenge from the slave
        challenge = sock.recv(4096).decode()

        # Hash the challenge with the shared secret and send it back
        response = hash_challenge(challenge)
        sock.sendall(response.encode())

        # Receive authentication status
        auth_status = sock.recv(4096).decode()
        if auth_status != "AUTH_SUCCESS":
            print("Authentication failed!")
            return
        print("Authentication successful!")
        sync_macros(sock)

        while True:
            global is_macros_updated
            if is_macros_updated:
                sync_macros(sock)
                is_macros_updated = False

            for hotkey, commands in MACROS.copy().items():
                required_keys = set(hotkey.split('+'))

                if keys_pressed_recently(required_keys):
                    for command in commands:
                        process_and_send_command(command, sock)

                    # Clear the key press times for the macro so it's not triggered repeatedly
                    for key in required_keys:
                        key_press_times.pop(key, None)

                    # Delay to avoid rapid firing and give time for key release
                    time.sleep(0.5)


def sync_macros(sock):
    execute_db_query('INSERT OR REPLACE INTO macros VALUES (?, ?)', list(MACROS.items()))
    send_data = json.dumps({"type": "SYNC_MACROS", "data": MACROS})
    sock.sendall(send_data.encode('utf-8'))


# Slave functions

def listen_for_data():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print("Listening for input...")

        conn, addr = s.accept()
        with conn:
            print('Connected by', addr)

            # Send a random challenge to the master
            challenge = str(random.randint(100000, 999999))
            conn.sendall(challenge.encode())

            # Receive the hashed response
            response = conn.recv(4096).decode()

            # Verify the response
            if response == hash_challenge(challenge):
                print("Authentication successful!")
                conn.sendall("AUTH_SUCCESS".encode())
            else:
                print("Authentication failed!")
                conn.sendall("AUTH_FAILED".encode())
                return

            while True:
                data_received = conn.recv(4096).decode()

                if not data_received:
                    print("Connection lost...")
                    break

                payload = json.loads(data_received)
                if payload["type"] == "SYNC_MACROS":
                    received_macros = payload["data"]
                    sync_macros_to_db(received_macros)
                elif payload["type"] == "exit":
                    print("Exiting...")
                    break
                elif payload["type"] == "text":
                    pyautogui.write(payload["data"])
                elif payload["type"] == "keys":
                    pyautogui.hotkey(*payload["data"])
                elif payload["type"] == "mouse_move":
                    x, y = payload["data"]["x"], payload["data"]["y"]
                    pyautogui.moveTo(x, y)
                elif payload["type"] == "mouse_move_rel":
                    dx, dy = payload["data"]["dx"], payload["data"]["dy"]
                    pyautogui.move(dx, dy)


def sync_macros_to_db(received_macros):
    with get_db_connection() as c:
        c.execute('DELETE FROM macros')
        c.executemany("INSERT OR REPLACE INTO macros VALUES (?, ?)",
                      [(hotkey, ','.join(action)) for hotkey, action in received_macros.items()])


# Tkinter app

class App:
    def __init__(self, root):
        self.mode = StringVar(value="master")

        Radiobutton(root, text="Master", variable=self.mode, value="master").grid(row=0, column=0, sticky="w")
        Radiobutton(root, text="Slave", variable=self.mode, value="slave").grid(row=1, column=0, sticky="w")

        Label(root, text="Slave IP Address:").grid(row=2, column=0, sticky="e")
        self.ip_entry = Entry(root)
        self.ip_entry.grid(row=2, column=1)
        self.ip_entry.insert(0, HOST)

        self.start_button = Button(root, text="Start", command=self.start)
        self.start_button.grid(row=3, column=0, columnspan=2)

        self.stop_button = Button(root, text="Stop", state="disabled", command=self.stop)
        self.stop_button.grid(row=4, column=0, columnspan=2)

        # Create vertical and horizontal Scrollbars
        self.v_scrollbar = Scrollbar(root, orient='vertical')
        self.v_scrollbar.grid(row=5, column=2, sticky='ns')

        self.h_scrollbar = Scrollbar(root, orient='horizontal')
        self.h_scrollbar.grid(row=6, column=0, columnspan=2, sticky='ew')

        # Create a Listbox and add it to the grid layout
        self.macro_listbox = Listbox(root, yscrollcommand=self.v_scrollbar.set, xscrollcommand=self.h_scrollbar.set)
        self.macro_listbox.grid(row=5, column=0, columnspan=2, sticky="nsew")

        # Configure the vertical Scrollbar
        self.v_scrollbar.config(command=self.macro_listbox.yview)

        # Configure the horizontal Scrollbar
        self.h_scrollbar.config(command=self.macro_listbox.xview)

        # Load the macros into the Listbox
        self.load_macros_into_listbox()

        # Add/Edit/Delete buttons for the macros
        self.add_button = Button(root, text="Add Macro", command=self.add_macro)
        self.add_button.grid(row=7, column=0)

        self.edit_button = Button(root, text="Edit Macro", command=self.edit_macro)
        self.edit_button.grid(row=7, column=1)

        self.delete_button = Button(root, text="Delete Macro", command=self.delete_macro)
        self.delete_button.grid(row=7, column=2)

        self.running = False
        self.current_thread = None

    def start(self):
        global HOST
        HOST = self.ip_entry.get()
        if self.mode.get() == "master":
            self.start_master()
        else:
            self.start_slave()

    def start_master(self):
        if self.running:
            return
        try:
            self.listener = keyboard.Listener(on_press=on_key_press)
            self.listener.start()

            self.current_thread = threading.Thread(target=send_data_to_slave)
            self.current_thread.start()
            self.running = True
            self.start_button.config(state="disabled")
            self.stop_button.config(state="normal")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def start_slave(self):
        if self.running:
            return
        try:
            self.current_thread = threading.Thread(target=listen_for_data)
            self.current_thread.start()
            self.running = True
            self.start_button.config(state="disabled")
            self.stop_button.config(state="normal")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def stop(self):
        # Implement any necessary cleanup and stop logic here.
        # NOTE: Stopping threads cleanly can be a bit tricky, especially when they're
        # doing blocking tasks like network communication.
        # Below is a simple method but it might not work in all scenarios.

        if self.current_thread and self.current_thread.is_alive():
            # This forcefully terminates the thread. This can be problematic,
            # especially if resources (like network sockets) aren't properly closed.
            # In real-world scenarios, you would implement a safer method.
            self.current_thread._stop()

        self.running = False
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")

    def load_macros_into_listbox(self):
        self.macro_listbox.delete(0, 'end')  # clear existing items
        for hotkey, actions in MACROS.items():
            self.macro_listbox.insert('end', f"Hotkey: {hotkey}, Action: {actions[0]}")

    def update_db_and_dict(self, hotkey, action):
        with get_db_connection() as c:
            c.execute("INSERT OR REPLACE INTO macros VALUES (?, ?)", (hotkey, action))
        MACROS[hotkey] = [action]
        global is_macros_updated
        is_macros_updated = True
        self.load_macros_into_listbox()

    def add_macro(self):
        hotkey = simpledialog.askstring("Input", "Enter the hotkey:")
        action = simpledialog.askstring("Input", "Enter the action:") if hotkey else None
        if hotkey and action:
            self.update_db_and_dict(hotkey, action)

    def edit_macro(self):
        selected = self.macro_listbox.curselection()
        if not selected:
            messagebox.showwarning("Warning", "No macro selected!")
            return
        listbox_entry = self.macro_listbox.get(selected[0])

        # Parsing hotkey and existing action from listbox entry
        # Assuming the entry format is 'Hotkey: hotkey_value, Action: action_value'
        hotkey_part, action_part = listbox_entry.split(", ")
        existing_hotkey = hotkey_part.split(": ")[1]
        existing_action = action_part.split(": ")[1]

        # Asking for new hotkey and action
        new_hotkey = simpledialog.askstring("Input", f"Edit the hotkey", initialvalue=existing_hotkey)
        new_action = simpledialog.askstring("Input", f"Edit the action for {new_hotkey}", initialvalue=existing_action)

        if new_hotkey and new_action:
            # Update database
            with get_db_connection() as c:
                c.execute("DELETE FROM macros WHERE hotkey = ?", (existing_hotkey,))
                c.execute("INSERT INTO macros (hotkey, action) VALUES (?, ?)", (new_hotkey, new_action))

            # Update MACROS dictionary
            del MACROS[existing_hotkey]
            MACROS[new_hotkey] = [new_action]
            global is_macros_updated
            is_macros_updated = True
            self.load_macros_into_listbox()

    def delete_macro(self):
        selected = self.macro_listbox.curselection()
        if not selected:
            messagebox.showwarning("Warning", "No macro selected!")
            return

        confirm = messagebox.askyesno("Confirm", "Are you sure you want to delete this macro?")
        if not confirm:
            return

        selected_string = self.macro_listbox.get(
            selected[0])  # Note that curselection returns a tuple, hence selected[0]

        # Extracting the actual hotkey from the selected string
        hotkey = selected_string.split(",")[0].split(":")[1].strip()

        # Delete from database
        with get_db_connection() as c:
            c.execute("DELETE FROM macros WHERE hotkey = ?", (hotkey,))

        # Delete from MACROS dictionary
        try:
            del MACROS[hotkey]
            global is_macros_updated
            is_macros_updated = True

        except KeyError:
            messagebox.showerror("Error", "Macro not found in dictionary.")

        self.load_macros_into_listbox()


if __name__ == "__main__":
    initialize_db()
    load_macros_from_db()
    root = Tk()
    root.title("Master/Slave App")
    app = App(root)
    root.mainloop()