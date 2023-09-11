import socket
import json


class Server:
    def __init__(self, host, port, db_manager):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((host, port))
        self.server_socket.listen(5)
        self.db_manager = db_manager

    def start(self):
        print("Server started and waiting for connections...")
        while True:
            client, addr = self.server_socket.accept()
            print(f"Connection from {addr}")
            data = client.recv(1024).decode()
            self.handle_data(json.loads(data))
            client.close()

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
        self.server_socket.close()
