import socket
import json


class Client:
    def __init__(self, host, port, db_manager):
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.connect((host, port))
        self.db_manager = db_manager

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
