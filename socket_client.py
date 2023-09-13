import hashlib
import logging
import socket
import json
import time

from pynput import keyboard

from macro_manager import MacroManager

BUFFER_SIZE = 4096
AUTH_SUCCESS = "AUTH_SUCCESS"
AUTH_FAILED = "AUTH_FAILED"
SHARED_SECRET = "JosueAlemanIsASecretPassword"
key_press_times = {}


def on_key_press(key):
    try:
        key_name = key.char  # For regular keys
        logging.info(f"it is a char (regular keys)")

    except AttributeError:
        key_name = key.name  # For special keys
        logging.info(f"it is a name (special key)")

    logging.info(f"Key pressed: {key_name}")
    key_press_times[key_name] = time.time()


class Client:
    def __init__(self, host, port, db_manager):
        self.host = host
        self.port = port
        self.client_socket = None
        # self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # self.client_socket.connect((host, port))
        self.db_manager = db_manager
        self.listener = keyboard.Listener(on_press=on_key_press)
        self.transaction_queue = []

    def start_client_services(self):
        logging.info("Starting main client loop...")
        try:
            self.listener.start()
            logging.info("Keyboard listener started")
            with socket.create_connection((self.host, self.port)) as self.client_socket:
                logging.info("Client socket created successfully, authenticating...")
                if not self.authenticate_server_with_client():
                    logging.error("Authentication failed :(")
                    return
                logging.info("Authentication Success!")
                self.main_client_loop()
        except Exception as e:
            logging.error(f"Error in sending data to slave: {e}")

    def main_client_loop(self):
        while True:
            for hotkey, commands in MacroManager.get_macros().copy().items():
                if self.should_execute_macro(hotkey):
                    for command in commands:
                        self.process_and_send_command(command)

                    time.sleep(0.5)  # Delay to avoid rapid firing

    def should_execute_macro(self, hotkey):
        required_keys = set(hotkey.split('+'))
        if self.keys_pressed_recently(required_keys):
            for key in required_keys:
                key_press_times.pop(key, None)
            logging.info(f"Will execute macro: {hotkey}")
            return True
        return False

    def process_and_send_command(self, user_input):
        try:
            logging.info(f"Processing commands: {user_input}")
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
                self.client_socket.sendall(message.encode('utf-8'))
        except Exception as e:
            logging.error(f"Error processing command for input {user_input}: {e}")

    def keys_pressed_recently(self, keys, window=0.5):
        return all(key_press_times.get(key, 0) >= time.time() - window for key in keys)

    def authenticate_server_with_client(self):
        challenge = self.client_socket.recv(BUFFER_SIZE).decode()
        response = self.hash_challenge(challenge)
        self.client_socket.sendall(response.encode())
        auth_status = self.client_socket.recv(BUFFER_SIZE).decode()
        return auth_status == AUTH_SUCCESS

    def hash_challenge(self, challenge):
        return hashlib.sha256((challenge + SHARED_SECRET).encode()).hexdigest()

    def add_macro(self, hotkey, actions):
        # Update local DB
        self.db_manager.add_macro(hotkey, actions)
        # Send transaction to server
        data = {
            'action': 'add',
            'hotkey': hotkey,
            'actions': actions
        }
        self.send_data(data)

    def edit_macro(self, hotkey, new_actions):
        # Update local DB
        self.db_manager.edit_macro(hotkey, new_actions)
        # Send transaction to server
        data = {
            'action': 'edit',
            'hotkey': hotkey,
            'actions': new_actions
        }
        self.send_data(data)

    def delete_macro(self, hotkey):
        # Update local DB
        self.db_manager.delete_macro(hotkey)
        # Send transaction to server
        data = {
            'action': 'delete',
            'hotkey': hotkey
        }
        self.send_data(data)

    def send_data(self, data):
        self.client_socket.send(json.dumps(data).encode())

    def close(self):
        self.client_socket.close()
