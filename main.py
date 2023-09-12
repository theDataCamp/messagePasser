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

from db_manager import MacroDBManager
from macro_tree import MacroActionTree

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


# MACROS = {
#     "ctrl_l+alt_l+r": ["KEYS:right"],
#     "ctrl_l+alt_l+l": ["KEYS:left"],
#     "ctrl_l+alt_l+f": ["KEYS:f8"],
#     "ctrl_l+alt_l+.": ["KEYS:ctrl_l+right"],
#     "ctrl_l+alt_l+/": ["KEYS:ctrl_l+left"]
# }


class MacroManager:
    MACROS = {
        "ctrl_l+alt_l+r": ["KEYS:right", "TEXT:Hello"],
        "ctrl_l+alt_l+l": ["KEYS:left"],
        "ctrl_l+alt_l+f": ["KEYS:f8"],
        "ctrl_l+alt_l+.": ["KEYS:ctrl_l+right"],
        "ctrl_l+alt_l+/": ["KEYS:ctrl_l+left"]
    }

    @staticmethod
    def display_macros():
        for key, value in MacroManager.MACROS.items():
            print(f"{key}: {value}")

    @staticmethod
    def get_macros():
        return MacroManager.MACROS

    @staticmethod
    def add_macro(hotkey, action):
        MacroManager.MACROS[hotkey] = [action]

    @staticmethod
    def edit_macro(old_hotkey, new_hotkey, new_action):
        if old_hotkey not in MacroManager.MACROS:
            print("Original key combination not found!")
            return
        del MacroManager.MACROS[old_hotkey]
        MacroManager.MACROS[new_hotkey] = [new_action]

    @staticmethod
    def delete_macro(hotkey):
        if hotkey in MacroManager.MACROS:
            del MacroManager.MACROS[hotkey]
        else:
            print("Key combination not found!")


    @staticmethod
    def add_actions(hotkey, actions):
        MacroManager.MACROS[hotkey] = actions


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
                logging.info(f"Count is 0, loading the following macros from script: {MacroManager.get_macros()}")
                c.executemany("INSERT OR REPLACE INTO macros VALUES (?, ?)",
                              [(hotkey, ','.join(action)) for hotkey, action in MacroManager.get_macros().items()])

    @staticmethod
    def load_macros_from_db():
        # global MACROS
        # logging.info(f"Current MACROS: {MACROS}")
        with DatabaseManager.get_db_connection() as c:
            for hotkey, action in c.execute('SELECT * FROM macros'):
                logging.info(f"loading: {hotkey} with action: {action}")
                MacroManager.add_macro(hotkey, action.split(','))
                # MACROS[hotkey] = action.split(',')

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

    @staticmethod
    def add_macro_to_db(hotkey, action):
        query = f'INSERT OR REPLACE INTO macros VALUES(?, ?)'
        DatabaseManager.execute_db_query(query, (hotkey, action))

    @staticmethod
    def delete_macro_from_db(hotkey):
        query = f'DELETE FROM macros WHERE hotkey = ?'
        DatabaseManager.execute_db_query(query, (hotkey,))

    @staticmethod
    def edit_macro_in_db(existing_hotkey, new_hotkey, new_action):
        DatabaseManager.delete_macro_from_db(existing_hotkey)
        DatabaseManager.add_macro_to_db(new_hotkey, new_action)


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
    try:
        for command in user_input:
            if command.startswith("EXIT:"):
                payload = {"type": "exit"}
            elif command.startswith("TEXT:"):
                text = command[len("TEXT:"):].strip()
                payload = {"type": "text", "data": text}
            elif command.startswith("KEYS:"):
                keys = command[len("KEYS:"):].strip().split('+')
                payload = {"type": "keys", "data": keys}
            else:
                logging.error("Invalid command. Please use TEXT:, KEYS:, or EXIT: as a prefix.")
                return

            message = json.dumps(payload)
            logging.info(f"Sending message: {message}")
            sock.sendall(message.encode('utf-8'))
    except Exception as e:
        logging.error(f"Error processing command for input {user_input}: {e}")


def hash_challenge(challenge):
    return hashlib.sha256((challenge + SHARED_SECRET).encode()).hexdigest()


"""
Client Functions--------------------
"""


def send_data_to_server():
    try:
        with socket.create_connection((HOST, PORT)) as sock:
            if not authenticate_server_with_client(sock):
                logging.error(f"Authentication failed")
                return
            logging.info("Authentication successful")
            # sync_macros(sock)
            main_client_loop(sock)

    except Exception as e:
        logging.error(f"Error in sending data to slave: {e}")


def authenticate_server_with_client(sock):
    challenge = sock.recv(BUFFER_SIZE).decode()
    response = hash_challenge(challenge)
    sock.sendall(response.encode())
    auth_status = sock.recv(BUFFER_SIZE).decode()
    return auth_status == AUTH_SUCCESS


def main_client_loop(sock):
    while True:
        global is_macros_updated
        if is_macros_updated:
            logging.info(f"macros updated, triggering sync_macros")
            # sync_macros(sock)
            is_macros_updated = False

        for hotkey, commands in MacroManager.get_macros().copy().items():
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
    logging.info(f"Current macros to sync {MacroManager.get_macros()}")
    data = list(MacroManager.get_macros().items())
    logging.info(f"data from macros: {data}")
    # Calculate the number of columns to insert (this assumes that all tuples in `data` have the same length)
    num_columns = len(data[0]) if data else 0
    logging.info(f"column count from MACROS: {num_columns}")
    logging.info(f"data len: {len(data)}")
    for item in data:
        logging.info(f"data item: {item}")

    # Generate the appropriate number of placeholders
    placeholders = ', '.join('?' * num_columns)
    # Create the SQL query string
    query = f'INSERT OR REPLACE INTO macros VALUES ({placeholders})'
    for item in data:
        DatabaseManager.execute_db_query(query, item)
    # DatabaseManager.execute_db_query(query, data)
    send_data = json.dumps({"type": "SYNC_MACROS", "data": MacroManager.get_macros()})
    logging.info(f"sending data: {send_data}")
    sock.sendall(send_data.encode('utf-8'))


"""
Server Functions--------------------
"""


def listen_for_data():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((HOST, PORT))
            s.listen()
            logging.info("Listening for input...")

            conn, addr = s.accept()
            handle_server_connection(conn, addr)
    except Exception as e:
        logging.error(f"Error in listen_for_data: {e}")


def handle_server_connection(connection, addr):
    with connection:
        logging.info(f'Connected by {addr}')

        if authenticate_client_with_server(connection):
            logging.info("Authentication successful!")
            connection.sendall(AUTH_SUCCESS.encode())
            main_server_loop(connection)
        else:
            logging.error("Authentication failed!")
            connection.sendall(AUTH_FAILED.encode())


def authenticate_client_with_server(connection):
    challenge = generate_challenge()
    connection.sendall(challenge.encode())
    response = connection.recv(BUFFER_SIZE).decode()
    return validate_response(response, challenge)


def main_server_loop(connection):
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

def create_actions_from_string(action):
    actions = [item.strip() for item in action.split(',')]
    return actions


class App:
    instance = None

    def __init__(self, root):
        self.listener = None
        self.db_manager = MacroDBManager('sqlite:///./macrobs.db')
        self.macro_tree = None
        self.row_num = 0
        App.instance = self
        self.mode = StringVar(value="master")

        Radiobutton(root, text="Master", variable=self.mode, value="master").grid(row=self.row_num, column=0,
                                                                                  sticky="w")
        self.row_num += 1
        Radiobutton(root, text="Slave", variable=self.mode, value="slave").grid(row=self.row_num, column=0, sticky="w")
        self.row_num += 1

        Label(root, text="Slave IP Address:").grid(row=self.row_num, column=0, sticky="e")
        self.ip_entry = Entry(root)
        self.ip_entry.grid(row=self.row_num, column=1)
        self.ip_entry.insert(0, HOST)
        self.row_num += 1

        self.start_button = Button(root, text="Start", command=self.start)
        self.start_button.grid(row=self.row_num, column=0, columnspan=2)
        self.row_num += 1

        self.stop_button = Button(root, text="Stop", state="disabled", command=self.stop)
        self.stop_button.grid(row=self.row_num, column=0, columnspan=2)
        self.row_num += 1

        # Create vertical and horizontal Scrollbars
        self.v_scrollbar = Scrollbar(root, orient='vertical')
        # self.v_scrollbar.grid(row=self.row_num, column=2, sticky='ns')

        self.h_scrollbar = Scrollbar(root, orient='horizontal')
        # self.h_scrollbar.grid(row=self.row_num + 1, column=0, columnspan=2, sticky='ew')
        # Create a Listbox and add it to the grid layout
        self.macro_listbox = Listbox(root, yscrollcommand=self.v_scrollbar.set, xscrollcommand=self.h_scrollbar.set)
        # self.macro_listbox.grid(row=self.row_num - 1, column=0, columnspan=2, sticky="nsew")
        # self.row_num += 2

        self.macro_tree = MacroActionTree(root, self.row_num)
        self.macro_tree.tree.grid(row=self.row_num, column=0, columnspan=3, sticky="nsew")
        self.row_num = self.macro_tree.last_used_row + 1

        # Configure the vertical Scrollbar
        self.v_scrollbar.config(command=self.macro_listbox.yview)

        # Configure the horizontal Scrollbar
        self.h_scrollbar.config(command=self.macro_listbox.xview)

        # Load the macros into the Listbox
        self.load_macros_into_listbox()

        # Add/Edit/Delete buttons for the macros
        self.add_button = Button(root, text="Add Macro", command=self.add_macro)
        self.add_button.grid(row=self.row_num, column=0)

        self.edit_button = Button(root, text="Edit Macro", command=self.edit_macro)
        self.edit_button.grid(row=self.row_num, column=1)

        self.delete_button = Button(root, text="Delete Macro", command=self.delete_macro)
        self.delete_button.grid(row=self.row_num, column=2)

        self.running = False
        self.current_thread = None

    def start(self):
        global HOST
        HOST = self.ip_entry.get()
        if self.mode.get() == "master":
            self.start_client()
        else:
            self.start_server()

    def start_client(self):
        if self.running:
            return
        try:
            self.listener = keyboard.Listener(on_press=on_key_press)
            self.listener.start()

            self.current_thread = threading.Thread(target=send_data_to_server)
            self.current_thread.start()
            self.running = True
            self.start_button.config(state="disabled")
            self.stop_button.config(state="normal")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def start_server(self):
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
        self.macro_tree.clear_items()
        logging.info(f"loading macros into list box: {MacroManager.get_macros()}")
        for hotkey, actions in MacroManager.get_macros().items():
            logging.info(f"hotkey: {hotkey} actions: {actions}")
            self.macro_listbox.insert('end', f"Hotkey: {hotkey}, Action: {actions[0]}")
            self.macro_tree.insert(hotkey, actions)

    def add_macro(self):
        hotkey = simpledialog.askstring("Input", "Enter the hotkey:")
        action = simpledialog.askstring("Input", "Enter the action:") if hotkey else None
        actions = create_actions_from_string(action)
        if hotkey and action:
            logging.info(f"Adding Macro: hotkey:{hotkey} action:{action} or actions: {actions}")
            DatabaseManager.add_macro_to_db(hotkey, action)
            self.db_manager.add_macro(hotkey, actions)
            global is_macros_updated
            is_macros_updated = True
            MacroManager.add_actions(hotkey, actions)
            # MacroManager.add_macro(hotkey, action)
            self.load_macros_into_listbox()

    def edit_macro(self):
        macro, actions = self.macro_tree.get_selected()
        if not macro and not actions:
            messagebox.showwarning("Warning", "Please Select a Macro to edit")
            return
        new_macro = simpledialog.askstring("Edit", "Enter Macro:", initialvalue=macro)
        if new_macro is not None:
            new_action = simpledialog.askstring("Edit", "Enter actions (separated by ','", initialvalue=actions)
            if new_action is not None:
                self.macro_tree.edit_selected(new_macro, new_action)
                DatabaseManager.edit_macro_in_db(macro, new_macro, new_action)
                actions = create_actions_from_string(new_action)
                self.db_manager.edit_macro(macro, new_macro, actions)
                MacroManager.edit_macro(macro, new_macro, new_action)
                global is_macros_updated
                is_macros_updated = True
                self.load_macros_into_listbox()
        # selected = self.macro_listbox.curselection()
        # if not selected:
        #     messagebox.showwarning("Warning", "No macro selected!")
        #     return
        # listbox_entry = self.macro_listbox.get(selected[0])
        #
        # # Parsing hotkey and existing action from listbox entry
        # # Assuming the entry format is 'Hotkey: hotkey_value, Action: action_value'
        # hotkey_part, action_part = listbox_entry.split(", ")
        # existing_hotkey = hotkey_part.split(": ")[1]
        # existing_action = action_part.split(": ")[1]
        #
        # # Asking for new hotkey and action
        # new_hotkey = simpledialog.askstring("Input", f"Edit the hotkey", initialvalue=existing_hotkey)
        # new_action = simpledialog.askstring("Input", f"Edit the action for {new_hotkey}", initialvalue=existing_action)
        #
        # if new_hotkey and new_action:
        #     logging.info(f"edit_macro Updating DB: new hotkey{new_hotkey}  new action:{new_action}")
        #     # Update database
        #     DatabaseManager.edit_macro_in_db(existing_hotkey, new_hotkey, new_action)
        #
        #     # Update MACROS dictionary
        #     logging.info(f"edit_macro: old MACROS: {MacroManager.get_macros()}")
        #     MacroManager.edit_macro(existing_hotkey, new_hotkey, new_action)
        #     logging.info(f"edit_macro: new MACROS: {MacroManager.get_macros()}")
        #     global is_macros_updated
        #     is_macros_updated = True
        #     self.load_macros_into_listbox()

    def delete_macro(self):
        macro, actions = self.macro_tree.get_selected()
        if not macro and not actions:
            messagebox.showwarning("Warning", "Please Select a Macro to delete")
            return
        confirm = messagebox.askyesno("Confirm", "Are you sure you want to delete this macro?")
        if not confirm:
            return

        # DatabaseManager.load_macros_from_db()
        # selected = self.macro_listbox.curselection()
        # if not selected:
        #     messagebox.showwarning("Warning", "No macro selected!")
        #     return

        # Note that curselection returns a tuple, hence selected[0]
        # selected_string = self.macro_listbox.get(selected[0])

        # Extracting the actual hotkey from the selected string
        # hotkey = selected_string.split(",")[0].split(":")[1].strip()

        # Delete from MACROS dictionary
        try:
            DatabaseManager.load_macros_from_db()
            logging.info(f"old MACROS: {MacroManager.get_macros()}")
            MacroManager.delete_macro(macro)
            logging.info(f"new MACROS:{MacroManager.get_macros()}")
            # Delete from database
            logging.info(f"delete_macro: looking for DB hotkey: {macro}")
            DatabaseManager.delete_macro_from_db(macro)
            DatabaseManager.load_macros_from_db()
            self.db_manager.delete_macro(macro)
            self.macro_tree.delete_selected()
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
