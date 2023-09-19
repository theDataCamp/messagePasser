import hashlib
import json
import logging
import socket
import time

from pynput import keyboard

from constants_manager import ConstantsManager
from custom_logger import CustomLogger
from macro_manager import MacroManager

# Getting a logger for the modulw level logging
module_logger = CustomLogger().get_logger("SocketClientModuleLogger")

# Constants and shared functions
# Initialize the ConstantsManager with a database URL
database_url = "sqlite:///constants.db"  # Using SQLite for this example
constants_manager = ConstantsManager(database_url)

BUFFER_SIZE = constants_manager.get('BUFFER_SIZE')
AUTH_SUCCESS = constants_manager.get('AUTH_SUCCESS')
AUTH_FAILED = constants_manager.get('AUTH_FAILED')
SHARED_SECRET = constants_manager.get('SHARED_SECRET')
key_press_times = {}


def on_key_press(key):
    try:
        key_name = key.char  # For regular keys
        module_logger.info(f"it is a char (regular keys)")

    except AttributeError:
        key_name = key.name  # For special keys
        module_logger.info(f"it is a name (special key)")

    logging.info(f"Key pressed: {key_name}")
    key_press_times[key_name] = time.time()


def keys_pressed_recently(keys, window=0.5):
    return all(key_press_times.get(key, 0) >= time.time() - window for key in keys)


def hash_challenge(challenge):
    return hashlib.sha256((challenge + SHARED_SECRET).encode()).hexdigest()


class Client:
    def __init__(self, host, port, db_manager):
        self.logger = CustomLogger().get_logger("ClientClassLogger")
        self.host = host
        self.port = port
        self.client_socket = None
        # self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # self.client_socket.connect((host, port))
        # self.db_manager = db_manager
        self.listener = keyboard.Listener(on_press=on_key_press)
        self.transaction_queue = []

    def start_client_services(self):
        logging.info("Starting main client loop...")
        try:
            self.listener.start()
            self.logger.info("Keyboard listener started")
            with socket.create_connection((self.host, self.port)) as self.client_socket:
                self.logger.info("Client socket created successfully, authenticating...")
                if not self.authenticate_server_with_client():
                    self.logger.error("Authentication failed :(")
                    return
                self.logger.info("Authentication Success!")
                self.main_client_loop()
        except Exception as e:
            self.logger.error(f"Error in sending data to slave: {e}")

    def main_client_loop(self):
        while True:
            for hotkey, commands in MacroManager.get_macros().copy().items():
                if self.should_execute_macro(hotkey):
                    for command in commands:
                        self.process_and_send_command(command)

                    time.sleep(0.5)  # Delay to avoid rapid firing

    def should_execute_macro(self, hotkey):
        required_keys = set(hotkey.split('+'))
        if keys_pressed_recently(required_keys):
            for key in required_keys:
                key_press_times.pop(key, None)
            self.logger.info(f"Will execute macro: {hotkey}")
            return True
        return False

    def process_and_send_command(self, user_input):
        try:
            self.logger.info(f"Processing command: {user_input}")

            if user_input.startswith("EXIT:"):
                payload = {"type": "exit"}
            elif user_input.startswith("TEXT:"):
                text = user_input[len("TEXT:"):].strip()
                payload = {"type": "text", "data": text}
            elif user_input.startswith("KEYS:"):
                keys = user_input[len("KEYS:"):].strip().split('+')
                payload = {"type": "keys", "data": keys}
            else:
                self.logger.error("Invalid command. Please use TEXT:, KEYS:, or EXIT: as a prefix.")
                return

            self.send_data(payload)
        except Exception as e:
            self.logger.error(f"Error processing command for input {user_input}: {e}")

    def authenticate_server_with_client(self):
        challenge = self.client_socket.recv(BUFFER_SIZE).decode()
        response = hash_challenge(challenge)
        self.client_socket.sendall(response.encode())
        auth_status = self.client_socket.recv(BUFFER_SIZE).decode()
        return auth_status == AUTH_SUCCESS

    def send_data(self, data):
        message = json.dumps(data)
        self.logger.info(f"Sending message {message} to server")
        self.client_socket.sendall(message.encode('utf-8'))

    def close(self):
        self.client_socket.close()
