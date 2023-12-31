from custom_logger import CustomLogger


class MacroManager:
    logger = CustomLogger().get_logger("MacroManagerClassLogger")
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
            MacroManager.logger.info(f"{key}: {value}")

    @staticmethod
    def get_macros():
        return MacroManager.MACROS

    @staticmethod
    def add_macro(hotkey, action):
        MacroManager.MACROS[hotkey] = [action]

    @staticmethod
    def edit_macro(old_hotkey, new_hotkey, new_action):
        if old_hotkey not in MacroManager.MACROS:
            MacroManager.logger.info("Original key combination not found!")
            return
        del MacroManager.MACROS[old_hotkey]
        MacroManager.MACROS[new_hotkey] = [new_action]

    @staticmethod
    def delete_macro(hotkey):
        if hotkey in MacroManager.MACROS:
            del MacroManager.MACROS[hotkey]
        else:
            MacroManager.logger.info("Key combination not found!")

    @staticmethod
    def add_actions(hotkey, actions):
        MacroManager.logger.info(f"addint {hotkey}, {actions}")
        MacroManager.MACROS[hotkey] = actions
