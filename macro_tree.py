from tkinter import ttk
import tkinter as tk


class MacroActionTree:

    def __init__(self, master, row_num):
        self.last_used_row = row_num
        # Container frame for Treeview and Scrollbars
        self.container = ttk.Frame(master)
        self.container.grid(row=self.last_used_row, sticky='nsew')

        # Configure the grid to handle resizing
        master.grid_rowconfigure(self.last_used_row, weight=1)
        master.grid_columnconfigure(0, weight=1)

        # Treeview
        self.tree = ttk.Treeview(self.container, columns=("Macros", "Actions"), show="headings")
        self.tree.heading("Macros", text="Macros")
        self.tree.heading("Actions", text="Actions")
        self.tree.column("Macros", width=200)
        self.tree.column("Actions", width=400)

        # Vertical Scrollbar
        self.vsb = ttk.Scrollbar(self.container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.vsb.set)

        # Horizontal Scrollbar
        self.hsb = ttk.Scrollbar(self.container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=self.hsb.set)

        # Use grid for geometry management
        self.tree.grid(row=self.last_used_row, column=0, sticky='nsew')
        self.vsb.grid(row=self.last_used_row, column=1, sticky='ns')
        self.last_used_row += 1
        self.hsb.grid(row=self.last_used_row, column=0, sticky='ew')

        # Configure the container's rows and columns to adjust properly
        self.container.grid_rowconfigure(row_num, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

    def insert(self, macro, action):
        self.tree.insert("", "end", values=(macro, action))

    def edit_selected(self, new_macro, new_action):
        selected_item = self.tree.selection()
        if selected_item:
            self.tree.item(selected_item, values=(new_macro, new_action))

    def delete_selected(self):
        selected_item = self.tree.selection()
        if selected_item:
            self.tree.delete(selected_item)

    def get_all(self):
        items = self.tree.get_children()
        return [(self.tree.item(item, "values")[0], self.tree.item(item, "values")[1]) for item in items]

    def get_selected(self):
        selected_item = self.tree.selection()
        if selected_item:
            return self.tree.item(selected_item, "values")
        return None, None

    def clear_items(self):
        # clear all the items from the treeview
        for item in self.tree.get_children():
            self.tree.delete(item)