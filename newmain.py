import json


import random
import socket
import sys
import threading
from tkinter import Tk, StringVar, Radiobutton, Entry, Button, Label, messagebox, simpledialog

import pyautogui

from custom_logger import CustomLogger
from observer_interface import Observer
from socket_server import Server
from db_manager import MacroDBManager
from macro_manager import MacroManager
from macro_tree import MacroActionTree
from socket_client import Client, hash_challenge
from constants_manager import ConstantsManager

# Getting a logger for the modulw level logging
module_logger = CustomLogger().get_logger("MainModuleLogger")

# Constants and shared functions
# Initialize the ConstantsManager with a database URL
database_url = "sqlite:///constants.db"  # Using SQLite for this example
constants_manager = ConstantsManager(database_url)


HOST = constants_manager.get('HOST')
PORT = constants_manager.get('PORT')
SHARED_SECRET = constants_manager.get('SHARED_SECRET')
DB_NAME = constants_manager.get('DB_NAME')
BUFFER_SIZE = constants_manager.get('BUFFER_SIZE')
AUTH_SUCCESS = constants_manager.get('AUTH_SUCCESS')
AUTH_FAILED = constants_manager.get('AUTH_FAILED')

"""
Server Functions--------------------
"""


def listen_for_data():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((HOST, PORT))
            s.listen()
            module_logger.info("Listening for input...")

            conn, addr = s.accept()
            handle_server_connection(conn, addr)
    except Exception as e:
        module_logger.error(f"Error in listen_for_data: {e}")


def handle_server_connection(connection, addr):
    with connection:
        module_logger.info(f'Connected by {addr}')

        if authenticate_client_with_server(connection):
            module_logger.info("Authentication successful!")
            connection.sendall(AUTH_SUCCESS.encode())
            main_server_loop(connection)
        else:
            module_logger.error("Authentication failed!")
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
            module_logger.warning("Connection lost...")
            break
        process_received_payload(data_received, connection)


def generate_challenge():
    return str(random.randint(100000, 999999))


def validate_response(response, challenge):
    return response == hash_challenge(challenge)


def process_received_payload(data_received, connection):
    payload = json.loads(data_received)
    module_logger.info(f"Received payload: {payload}")

    payload_type = payload.get("type")
    if payload_type == "SYNC_MACROS":
        module_logger.info("Sync Macros requested")
    elif payload_type == "exit":
        module_logger.info("Exiting...")
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
        module_logger.warning(f"Unknown payload type: {payload_type}")


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


class App(Observer):
    instance = None

    def __init__(self, root):
        self.logger = CustomLogger().get_logger("AppClassLogger")
        self.logger.info("Initializing app")
        self.listener = None
        self.db_manager = MacroDBManager('sqlite:///./macrobs.db')
        self.macro_tree = None
        self.service_to_run = None
        self.row_num = 0
        App.instance = self
        self.mode = StringVar(value="client")

        Radiobutton(root, text="Client", variable=self.mode, value="client").grid(row=self.row_num, column=0,
                                                                                  sticky="w")
        self.row_num += 1
        Radiobutton(root, text="Server", variable=self.mode, value="server").grid(row=self.row_num, column=0,
                                                                                  sticky="w")
        self.row_num += 1

        Label(root, text="Server IP Address:").grid(row=self.row_num, column=0, sticky="e")
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

        self.macro_tree = MacroActionTree(root, self.row_num)
        self.macro_tree.tree.grid(row=self.row_num, column=0, columnspan=1, sticky="nsew")
        self.row_num = self.macro_tree.last_used_row + 1

        # Add/Edit/Delete buttons for the macros
        self.add_button = Button(root, text="Add Macro", command=self.add_macro)
        self.add_button.grid(row=self.row_num, column=0)

        self.edit_button = Button(root, text="Edit Macro", command=self.edit_macro)
        self.edit_button.grid(row=self.row_num, column=1)

        self.delete_button = Button(root, text="Delete Macro", command=self.delete_macro)
        self.delete_button.grid(row=self.row_num, column=2)

        self.running = False
        self.current_thread = None
        self.check_initial_db_for_macros()
        self.db_manager.register_observers(App.instance)

    def update(self, transaction):
        self.logger.info(f"Updating Tree with incoming transaction {transaction}")
        operation = transaction.get("operation")
        hotkey = transaction.get("hotkey")
        actions = transaction.get("actions")
        old_hotkey = transaction.get("old_hotkey")
        self.logger.info(f"Operation:{operation}, hotkey:{hotkey}, actions: {actions}, old_hotkey: {old_hotkey}")

        if operation == "add":
            self.macro_tree.insert(hotkey, actions)
        elif operation == "edit":
            self.macro_tree.edit_by_macro(old_hotkey, hotkey, actions)
        elif operation == "delete":
            self.macro_tree.delete_by_macro(hotkey)

    def check_initial_db_for_macros(self):
        check = self.db_manager.get_all_macros()
        if isinstance(check, list) and not check:
            self.logger.info("No Macros in DB... assigning defaults")
            for hotkey, actions in MacroManager.get_macros().items():
                self.logger.info(f"Adding hotkey:{hotkey} and actions: {actions} to db")
                self.db_manager.add_macro(hotkey, actions)
                self.macro_tree.insert(hotkey, actions)
            self.logger.info("Clearing all DB transactions bc we loaded from MacroManager")
            self.db_manager.clear_transactions()
        elif isinstance(check, list):
            self.logger.info("Macros already in DB, skipping assigning defaults, but loading tree")
            for item in check:
                self.macro_tree.insert(item['hotkey'], item['actions'])
                MacroManager.add_actions(item['hotkey'], item['actions'])
        else:
            messagebox.showerror("Error!", "Macros DB seems to be corrupt, shutting down..")
            sys.exit()

    def start(self):
        constants_manager.set('HOST', self.ip_entry.get())
        if self.mode.get() == "client":
            self.start_client()
        else:
            self.start_server()

    def start_client(self):
        if self.running:
            return
        try:
            self.service_to_run = Client(HOST, PORT, self.db_manager)

            self.current_thread = threading.Thread(target=self.service_to_run.start_client_services)
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
            # TODO: Finish this
            self.service_to_run = Server(HOST, PORT, self.db_manager)
            self.current_thread = threading.Thread(target=self.service_to_run.start)
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

    # TODO: Finsih the add, edity and delete with the correct payload packing to send across
    def add_macro(self):
        hotkey = simpledialog.askstring("Input", "Enter the hotkey:")
        action = simpledialog.askstring("Input", "Enter the action:") if hotkey else None
        actions = create_actions_from_string(action)
        if hotkey and action:
            self.logger.info(f"Adding Macro: hotkey:{hotkey} action:{action} or actions: {actions}")
            self.macro_tree.insert(hotkey, actions)
            self.db_manager.add_macro(hotkey, actions)
            MacroManager.add_actions(hotkey, actions)
            if isinstance(self.service_to_run, Client) and self.service_to_run is not None:
                self.logger.info("We have a Client service and its not empty so we will send the add across to server")
                self.check_and_send_db_transactions()
                # self.service_to_run.send_data()

    def check_and_send_db_transactions(self):
        transactions = self.db_manager.get_all_transactions()
        if transactions is not None:
            if transactions:
                self.logger.info(f"We have transactions to send: {transactions}")
                self.service_to_run.create_db_sync_payload_and_send(transactions)
                self.db_manager.clear_transactions()

    def edit_macro(self):
        macro, actions = self.macro_tree.get_selected()
        if not macro and not actions:
            messagebox.showwarning("Warning", "Please Select a Macro to edit")
            return
        new_macro = simpledialog.askstring("Edit", "Enter Macro:", initialvalue=macro)
        if new_macro is not None:
            new_action = simpledialog.askstring("Edit", "Enter actions (separated by ','", initialvalue=actions)
            if new_action is not None:
                actions = create_actions_from_string(new_action)
                self.macro_tree.edit_selected(new_macro, new_action)
                self.db_manager.edit_macro(macro, new_macro, actions)
                MacroManager.edit_macro(macro, new_macro, new_action)
                self.check_and_send_db_transactions()

    def delete_macro(self):
        macro, actions = self.macro_tree.get_selected()
        if not macro and not actions:
            messagebox.showwarning("Warning", "Please Select a Macro to delete")
            return
        confirm = messagebox.askyesno("Confirm", "Are you sure you want to delete this macro?")
        if not confirm:
            return
        try:
            self.logger.info(f"old MACROS: {MacroManager.get_macros()}")
            MacroManager.delete_macro(macro)
            self.logger.info(f"new MACROS:{MacroManager.get_macros()}")
            # Delete from database
            self.logger.info(f"delete_macro: looking for DB hotkey: {macro}")
            self.db_manager.delete_macro(macro)
            self.macro_tree.delete_selected()
            self.check_and_send_db_transactions()

        except KeyError:
            messagebox.showerror("Error", "Macro not found in dictionary.")


if __name__ == "__main__":
    root = Tk()
    root.title("Client/Server App")
    app = App(root)
    root.mainloop()
