import hashlib
import logging
import random
import socket
import json

import pyautogui

from constants_manager import ConstantsManager
from custom_logger import CustomLogger

# Getting a logger for the modulw level logging
module_logger = CustomLogger().get_logger("SocketServerModuleLogger")

# Constants and shared functions
# Initialize the ConstantsManager with a database URL
database_url = "sqlite:///constants.db"  # Using SQLite for this example
constants_manager = ConstantsManager(database_url)

HOST = constants_manager.get('HOST')
PORT = constants_manager.get('PORT')
SHARED_SECRET = constants_manager.get('SHARED_SECRET')
BUFFER_SIZE = constants_manager.get('BUFFER_SIZE')
AUTH_SUCCESS = constants_manager.get('AUTH_SUCCESS')
AUTH_FAILED = constants_manager.get('AUTH_FAILED')


def generate_challenge():
    return str(random.randint(100000, 999999))


def validate_response(response, challenge):
    return response == hash_challenge(challenge)


def hash_challenge(challenge):
    return hashlib.sha256((challenge + SHARED_SECRET).encode()).hexdigest()


class Server:
    def __init__(self, host, port, db_manager):
        self.logger = CustomLogger().get_logger("ServerClassLogger")
        self.server_socket = None
        # self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # self.server_socket.bind((host, port))
        # self.server_socket.listen(5)
        self.db_manager = db_manager

    def start(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as self.server_socket:
                self.server_socket.bind((HOST, PORT))
                self.server_socket.listen()
                self.logger.info("Server started and waiting for connections...")

                client, addr = self.server_socket.accept()
                logging.info(f"Connection from {addr}")
                self.handle_connection(client, addr)

        except Exception as e:
            self.logger.error(f"Error in listen_for_data: {e}")

    # TODO: change this to handle correct data if we want to do it this way
    def handle_data(self, data):
        action = data['action']
        hotkey = data['hotkey']
        actions = data.get('actions', '')

        if action == "add":
            self.db_manager.add_macro(hotkey, actions)
        elif action == "edit":
            self.db_manager.edit_macro(hotkey, actions)
        elif action == "delete":
            self.db_manager.delete_macro(hotkey)

    def close(self):
        self.logger.info("Closing server socket")
        self.server_socket.close()

    def handle_connection(self, client, addr):
        with client:
            if self.authenticate(client):
                self.logger.info("Authentication successful")
                client.sendall(AUTH_SUCCESS.encode())
                self.main_server_loop(client)

    def authenticate(self, client):
        challenge = generate_challenge()
        client.sendall(challenge.encode())
        response = client.recv(BUFFER_SIZE).decode()
        return validate_response(response, challenge)

    def main_server_loop(self, client):
        while True:
            data_received = client.recv(BUFFER_SIZE).decode()
            if not data_received:
                logging.warning("Connection lost with client")
                break
            self.process_received_payload(data_received, client)

    # TODO: Finsih this
    def process_received_payload(self, data_received, client):
        payload = json.loads(data_received)
        self.logger.info(f"Received type:{type(payload)} payload:{payload}")
        payload_type = payload.get("type")
        if payload_type == "SYNC_MACROS":
            self.logger.info(f"Sync Macros requested")
            transactions = payload["data"]
            self.logger.info(f"Applying transactions to DB: {transactions}")
            self.db_manager.apply_transactions(transactions)
        elif payload_type == "exit":
            self.logger.info("Exiting...")
            client.close()
        elif payload_type == "text":
            pyautogui.write(payload["data"])
        elif payload_type == "keys":
            pyautogui.hotkey(*payload["data"])
        elif payload_type == "mouse_move":
            self.handle_mouse_move(payload)
        elif payload_type == "mouse_move_rel":
            self.handle_mouse_move_relative(payload)
        else:
            self.logger.warning(f"Unknown payload type: {payload_type}")

    def handle_mouse_move(self, payload):
        x, y = payload["data"]["x"], payload["data"]["y"]
        pyautogui.moveTo(x, y)

    def handle_mouse_move_relative(self, payload):
        dx, dy = payload["data"]["dx"], payload["data"]["dy"]
        pyautogui.move(dx, dy)
