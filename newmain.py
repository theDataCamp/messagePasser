import socket
import pyautogui
import tkinter as tk
from tkinter import simpledialog, messagebox
from pynput import keyboard

SECRET_KEY = 'mysecretkey'


class Server:
    def __init__(self, host='0.0.0.0', port=65432):
        self.host = host
        self.port = port

        # Define key combinations
        self.combinations = {
            frozenset([keyboard.Key.ctrl_l, keyboard.Key.alt_l, 'r']): self.action_up,
            frozenset([keyboard.Key.ctrl_l, keyboard.Key.alt_l, 'l']): self.action_hello_world
        }

        # Current keys pressed
        self.current_keys = set()

    def action_up(self):
        pyautogui.press('up')

    def action_hello_world(self):
        pyautogui.write('Hello world')

    def on_key_release(self, key):
        if key in self.current_keys:
            self.current_keys.remove(key)

        for combination, action in self.combinations.items():
            if self.current_keys.issubset(combination):
                action()

    def on_key_press(self, key):
        self.current_keys.add(key)

    def start(self):
        with keyboard.Listener(on_press=self.on_key_press, on_release=self.on_key_release) as listener:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((self.host, self.port))
                s.listen()
                print("Listening for commands...")
                conn, addr = s.accept()
                with conn:
                    print('Connected by', addr)
                    auth_key = conn.recv(1024).decode()
                    if auth_key != SECRET_KEY:
                        print("Authentication failed!")
                        return

                    while True:
                        data = conn.recv(1024).decode()
                        if not data:
                            break
                        if data == 'UP':
                            pyautogui.press('up')
                        elif data == 'DOWN':
                            pyautogui.press('down')
                        elif data.startswith('TYPE '):
                            message = data.split(' ', 1)[1]
                            pyautogui.write(message)

            listener.join()


class Client:
    def __init__(self, host='localhost', port=65432):
        self.host = host
        self.port = port

    def start(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((self.host, self.port))
            s.sendall(SECRET_KEY.encode())
            while True:
                command = input("Enter command (UP, DOWN, TYPE message): ")
                s.sendall(command.encode())
                if command == "exit":
                    break


class AppGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("Remote Control")

        tk.Label(self.master, text="Choose Mode:").pack(pady=10)
        self.mode_var = tk.StringVar(self.master)
        self.mode_var.set("Server")  # Default value

        modes = ["Server", "Client"]
        tk.OptionMenu(self.master, self.mode_var, *modes).pack(pady=10)

        self.ip_label = tk.Label(self.master, text="IP Address:")
        self.ip_label.pack(pady=10)
        self.ip_entry = tk.Entry(self.master)
        self.ip_entry.pack(pady=10)

        self.start_button = tk.Button(self.master, text="Start", command=self.start_mode)
        self.start_button.pack(pady=20)

        self.toggle_client_options()

    def toggle_client_options(self):
        if self.mode_var.get() == "Server":
            self.ip_label.pack_forget()
            self.ip_entry.pack_forget()
        else:
            self.ip_label.pack(pady=10)
            self.ip_entry.pack(pady=10)
        self.master.after(100, self.toggle_client_options)

    def start_mode(self):
        if self.mode_var.get() == "Client":
            client = Client(self.ip_entry.get())
            client.start()
        elif self.mode_var.get() == "Server":
            server = Server()
            server.start()
        else:
            messagebox.showerror("Error", "Invalid mode!")


if __name__ == "__main__":
    root = tk.Tk()
    app = AppGUI(root)
    root.mainloop()
