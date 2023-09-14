import hashlib
import logging
import random
import socket
import json

from constants_manager import constants

HOST = constants.get('HOST')
PORT = constants.get('PORT')
SHARED_SECRET = constants.get('SHARED_SECRET')
BUFFER_SIZE = constants.get('BUFFER_SIZE')
AUTH_SUCCESS = constants.get('AUTH_SUCCESS')
AUTH_FAILED = constants.get('AUTH_FAILED')


def generate_challenge():
    return str(random.randint(100000, 999999))

def validate_response(response, challenge):
    return response == hash_challenge(challenge)

def hash_challenge(challenge):
    return hashlib.sha256((challenge + SHARED_SECRET).encode()).hexdigest()

class Server:
    def __init__(self, host, port, db_manager):
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
                logging.info("Server started and waiting for connections...")

                client, addr = self.server_socket.accept()
                logging.info(f"Connection from {addr}")
                self.handle_connection(client, addr)

        except Exception as e:
            logging.error(f"Error in listen_for_data: {e}")

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
        logging.info("Closing server socket")
        self.server_socket.close()

    def handle_connection(self, client, addr):
        with client:
            if self.authenticate(client):
                logging.info("Authentication successful")
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
        logging.info(f"Received type:{type(payload)} payload:{payload}")
