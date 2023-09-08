import socket
import logging
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

# Added logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] [%(threadName)s] '
                                               '[%(module)s.%(funcName)s] %(message)s')

HOST = '10.0.0.221'
PORT = 65432
SHARED_SECRET = "JosueAlemanIsASecretPassword"
DB_NAME = "macros.db"
is_macros_updated = False
BUFFER_SIZE = 4096
AUTH_SUCCESS = "AUTH_SUCCESS"
AUTH_FAILED = "AUTH_FAILED"

MACROS = {
    "ctrl_l+alt_l+r": ["KEYS:right"],
    "ctrl_l+alt_l+l": ["KEYS:left"],
    "ctrl_l+alt_l+f": ["KEYS:f8"],
    "ctrl_l+alt_l+.": ["KEYS:ctrl_l+right"],
    "ctrl_l+alt_l+,": ["KEYS:ctrl_l+left"]
}

key_press_times = {}


class DatabaseManager:
    @staticmethod
    @contextmanager
    def get_db_connection():
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        try:
            yield c
        finally:
            conn.commit()
            conn.close()

    @staticmethod
    def initialize_db():
        with DatabaseManager.get_db_connection() as c:
            c.execute('CREATE TABLE IF NOT EXISTS macros(hotkey TEXT PRIMARY KEY, action TEXT)')

            # Check if the table is empty
            c.execute('SELECT COUNT(*) FROM macros')
            count = c.fetchone()[0]
            logging.info(f"Checking to see if macros table is empty, has a count of {count}")

            # If the table is empty, populate it with default macros
            if count == 0:
                logging.info(f"Count is 0, loading the following macros from script: {MACROS}")
                c.executemany("INSERT OR REPLACE INTO macros VALUES (?, ?)",
                              [(hotkey, ','.join(action)) for hotkey, action in MACROS.items()])

    @staticmethod
    def load_macros_from_db():
        global MACROS
        logging.info(f"Current MACROS: {MACROS}")
        with DatabaseManager.get_db_connection() as c:
            for hotkey, action in c.execute('SELECT * FROM macros'):
                logging.info(f"loading: {hotkey} with action: {action}")
                MACROS[hotkey] = action.split(',')

    @staticmethod
    def sync_macros_to_db(received_macros):
        logging.info(f" Received macros to sync: {received_macros}")
        with DatabaseManager.get_db_connection() as c:
            c.execute('DELETE FROM macros')
            c.executemany("INSERT OR REPLACE INTO macros VALUES (?, ?)",
                          [(hotkey, ','.join(action)) for hotkey, action in received_macros.items()])

    @staticmethod
    def execute_db_query(query, params=()):
        logging.info(f"Executing {query} with params: {params}")
        with DatabaseManager.get_db_connection() as c:
            try:
                c.execute(query, params)
            except sqlite3.Error as e:
                logging.error(f"Database error: {e}")


def on_key_press(key):
    try:
        key_name = key.char  # For regular keys
        logging.info(f"it is a char (regular keys)")

    except AttributeError:
        key_name = key.name  # For special keys
        logging.info(f"it is a name (special key)")

    logging.info(f"Key pressed: {key_name}")
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
        logging.error("Invalid command. Please use TEXT:, KEYS:, or EXIT: as a prefix.")
        return

    message = json.dumps(payload)
    logging.info(f"Sending message: {message}")
    sock.sendall(message.encode('utf-8'))


def hash_challenge(challenge):
    return hashlib.sha256((challenge + SHARED_SECRET).encode()).hexdigest()


"""
Master Functions--------------------
"""


def send_data_to_slave():
    try:
        with socket.create_connection((HOST, PORT)) as sock:
            if not authenticate_with_slave(sock):
                logging.error(f"Authentication failed")
                return
            logging.info("Authentication successful")
            sync_macros(sock)
            main_master_loop(sock)

    except Exception as e:
        logging.error(f"Error in sending data to slave: {e}")


def authenticate_with_slave(sock):
    challenge = sock.recv(BUFFER_SIZE).decode()
    response = hash_challenge(challenge)
    sock.sendall(response.encode())
    auth_status = sock.recv(BUFFER_SIZE).decode()
    return auth_status == AUTH_SUCCESS


def main_master_loop(sock):
    while True:
        global is_macros_updated
        if is_macros_updated:
            logging.info(f"macros updates, triggering sync_macros")
            sync_macros(sock)
            is_macros_updated = False

        for hotkey, commands in MACROS.copy().items():
            if should_execute_macro(hotkey):
                for command in commands:
                    process_and_send_command(command, sock)

                time.sleep(0.5)  # Delay to avoid rapid firing


def should_execute_macro(hotkey):
    required_keys = set(hotkey.split('+'))
    if keys_pressed_recently(required_keys):
        for key in required_keys:
            key_press_times.pop(key, None)
        return True
    return False


def sync_macros(sock):
    logging.info(f"Current macros to sync {MACROS}")
    data = list(MACROS.items())
    logging.info(f"data from macros: {data}")
    # Calculate the number of columns to insert (this assumes that all tuples in `data` have the same length)
    num_columns = len(data[0]) if data else 0
    logging.info(f"column count from MACROS: {num_columns}")

    # Generate the appropriate number of placeholders
    placeholders = ', '.join('?' * num_columns)
    # Create the SQL query string
    query = f'INSERT OR REPLACE INTO macros VALUES ({placeholders})'
    DatabaseManager.execute_db_query(query, data)
    send_data = json.dumps({"type": "SYNC_MACROS", "data": MACROS})
    logging.info(f"sending data: {send_data}")
    sock.sendall(send_data.encode('utf-8'))


"""
Slave Functions--------------------
"""


def listen_for_data():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((HOST, PORT))
            s.listen()
            logging.info("Listening for input...")

            conn, addr = s.accept()
            handle_slave_connection(conn, addr)
    except Exception as e:
        logging.error(f"Error in listen_for_data: {e}")


def handle_slave_connection(connection, addr):
    with connection:
        logging.info(f'Connected by {addr}')

        if authenticate_master(connection):
            logging.info("Authentication successful!")
            connection.sendall(AUTH_SUCCESS.encode())
            main_slave_loop(connection)
        else:
            logging.error("Authentication failed!")
            connection.sendall(AUTH_FAILED.encode())


def authenticate_master(connection):
    challenge = generate_challenge()
    connection.sendall(challenge.encode())
    response = connection.recv(BUFFER_SIZE).decode()
    return validate_response(response, challenge)


def main_slave_loop(connection):
    while True:
        data_received = connection.recv(BUFFER_SIZE).decode()
        if not data_received:
            logging.warning("Connection lost...")
            break
        process_received_payload(data_received, connection)


def generate_challenge():
    return str(random.randint(100000, 999999))


def validate_response(response, challenge):
    return response == hash_challenge(challenge)


def process_received_payload(data_received, connection):
    payload = json.loads(data_received)
    logging.info(f"Received payload: {payload}")

    payload_type = payload.get("type")
    if payload_type == "SYNC_MACROS":
        handle_sync_macros(payload)
    elif payload_type == "exit":
        logging.info("Exiting...")
        connection.close()
    elif payload_type == "text":
        pyautogui.write(payload["data"])
    elif payload_type == "keys":
        pyautogui.hotkey(*payload["data"])
    elif payload_type == "mouse_move":
        handle_mouse_move(payload)
    elif payload_type == "mouse_move_rel":
        handle_mouse_move_relative(payload)
    else:
        logging.warning(f"Unknown payload type: {payload_type}")


def handle_sync_macros(payload):
    received_macros = payload["data"]
    DatabaseManager.sync_macros_to_db(received_macros)
    DatabaseManager.load_macros_from_db()
    if App.instance:
        App.instance.load_macros_into_listbox()


def handle_mouse_move(payload):
    x, y = payload["data"]["x"], payload["data"]["y"]
    pyautogui.moveTo(x, y)


def handle_mouse_move_relative(payload):
    dx, dy = payload["data"]["dx"], payload["data"]["dy"]
    pyautogui.move(dx, dy)


# Tkinter app

class App:
    instance = None

    def __init__(self, root):
        self.listener = None
        App.instance = self
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
        if self.current_thread and self.current_thread.is_alive():
            self.current_thread._stop()

        self.running = False
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")

    def load_macros_into_listbox(self):
        self.macro_listbox.delete(0, 'end')  # clear existing items
        logging.info(f"loading macros into list box: {MACROS}")
        for hotkey, actions in MACROS.items():
            logging.info(f"hotkey: {hotkey} actions: {actions}")
            self.macro_listbox.insert('end', f"Hotkey: {hotkey}, Action: {actions[0]}")

    def update_db_and_dict(self, hotkey, action):
        logging.info(f"Updating DB and Dict with hotkey:{hotkey} action:{action}")
        with DatabaseManager.get_db_connection() as c:
            c.execute("INSERT OR REPLACE INTO macros VALUES (?, ?)", (hotkey, action))
        MACROS[hotkey] = [action]
        global is_macros_updated
        is_macros_updated = True
        self.load_macros_into_listbox()

    def add_macro(self):
        hotkey = simpledialog.askstring("Input", "Enter the hotkey:")
        action = simpledialog.askstring("Input", "Enter the action:") if hotkey else None
        if hotkey and action:
            logging.info(f"Adding Macro: hotkey:{hotkey} action:{action}")
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
            logging.info(f"edit_macro Updating DB: new hotkey{new_hotkey}  new action:{new_action}")
            # Update database
            with DatabaseManager.get_db_connection() as c:
                c.execute("DELETE FROM macros WHERE hotkey = ?", (existing_hotkey,))
                c.execute("INSERT INTO macros (hotkey, action) VALUES (?, ?)", (new_hotkey, new_action))

            # Update MACROS dictionary
            logging.info(f"edit_macro: old MACROS: {MACROS}")
            del MACROS[existing_hotkey]
            MACROS[new_hotkey] = [new_action]
            logging.info(f"edit_macro: new MACROS: {MACROS}")
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
        # Note that curselection returns a tuple, hence selected[0]
        selected_string = self.macro_listbox.get(selected[0])

        # Extracting the actual hotkey from the selected string
        hotkey = selected_string.split(",")[0].split(":")[1].strip()

        # Delete from database
        logging.info(f"delete_macro: looking for DB hotkey: {hotkey}")
        with DatabaseManager.get_db_connection() as c:
            c.execute("DELETE FROM macros WHERE hotkey = ?", (hotkey,))

        # Delete from MACROS dictionary
        try:
            logging.info(f"old MACROS: {MACROS}")
            del MACROS[hotkey]
            logging.info(f"new MACROS:{MACROS}")
            global is_macros_updated
            is_macros_updated = True

        except KeyError:
            messagebox.showerror("Error", "Macro not found in dictionary.")

        self.load_macros_into_listbox()


if __name__ == "__main__":
    DatabaseManager.initialize_db()
    DatabaseManager.load_macros_from_db()
    root = Tk()
    root.title("Master/Slave App")
    app = App(root)
    root.mainloop()
