import json
import logging

from sqlalchemy import create_engine, Column, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from custom_logger import CustomLogger

Base = declarative_base()


class Macro(Base):
    __tablename__ = 'macros'
    hotkey = Column(String(50), primary_key=True)
    actions = Column(String(500))


class MacroDBManager:
    def __init__(self, database_url):
        self.logger = CustomLogger().get_logger("MacroDBManagerClassLogger")
        self.engine = create_engine(database_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        # in memory transactions
        self.transactions = []
        self.observers = []

    def register_observers(self, observer):
        self.observers.append(observer)

    def remove_observer(self, observer):
        self.observers.remove(observer)

    def notify_observers(self, transaction):
        self.logger.info("Notifying observers")
        for observer in self.observers:
            self.logger.info(f"Notifying Observer: {observer} about transaction: {transaction}")
            observer.update(transaction)

    def _log_transaction(self, operation, hotkey, actions=None, old_hotkey=None):
        transaction = {
            'operation': operation,
            'hotkey': hotkey,
            'actions': actions,
            'old_hotkey':old_hotkey
        }
        self.transactions.append(transaction)

    def add_macro(self, hotkey, actions):
        self.logger.info(f"Adding: {hotkey} with actions: {actions}")
        session = self.Session()
        serialized_actions = json.dumps(actions)
        new_macro = Macro(hotkey=hotkey, actions=serialized_actions)
        session.add(new_macro)
        session.commit()
        session.close()
        self._log_transaction("add", hotkey, actions)
        self.notify_observers(self.transactions[-1])

    def delete_macro(self, hotkey):
        session = self.Session()
        session.query(Macro).filter_by(hotkey=hotkey).delete()
        session.commit()
        session.close()
        self._log_transaction("delete", hotkey)
        self.notify_observers(self.transactions[-1])

    def edit_macro(self, old_hotkey, new_hotkey, new_actions):
        self.logger.info(f"updating: {old_hotkey} to -> {new_hotkey} actions: {new_actions}")
        session = self.Session()
        macro = session.query(Macro).filter_by(hotkey=old_hotkey).first()
        if macro:
            logging.info(f"found old macro, beginning update")
            macro.hotkey = new_hotkey
            macro.actions = json.dumps(new_actions)
            session.commit()
        session.close()
        self._log_transaction("edit", new_hotkey, new_actions, old_hotkey)
        self.notify_observers(self.transactions[-1])

    def get_all_macros(self):
        session = self.Session()
        macros = session.query(Macro).all()
        result = []
        for macro in macros:
            result.append({
                'hotkey': macro.hotkey,
                'actions': json.loads(macro.actions)
            })
        session.close()
        return result

    def get_macro(self, hotkey):
        session = self.Session()
        macro = session.query(Macro).filter_by(hotkey=hotkey).first()
        if macro:
            macro.actions = json.loads(macro.actions)
        session.close()
        return macro

    def get_all_transactions(self):
        return self.transactions

    def clear_transactions(self):
        self.logger.info("Clearing all transactions")
        self.transactions.clear()

    def apply_transactions(self, transactions):
        session = self.Session()
        self.logger.info(f"Going to apply the following transactions: {transactions}")
        for transaction in transactions:
            operation = transaction.get("operation")
            hotkey = transaction.get("hotkey")
            actions = transaction.get("actions")
            old_hotkey = transaction.get("old_hotkey")
            self.logger.info(f"Operation:{operation}, hotkey:{hotkey}, actions: {actions}, old_hotkey: {old_hotkey}")

            if operation == "add":
                self.logger.info(f"We have an 'add' operation, we check to make sure it doesnt exist")
                if not session.query(Macro).filter_by(hotkey=hotkey).first():
                    serialized_actions = json.dumps(actions)
                    new_macro = Macro(hotkey=hotkey, actions=serialized_actions)
                    self.logger(f"Adding new macro: {new_macro}")
                    session.add(new_macro)

            elif operation == "edit":
                self.logger.info(f"Edit operation requested")
                if old_hotkey:
                    self.logger.info(f"Olf Hotkey present, checking to see if it exists")
                    macro = session.query(Macro).filter_by(hotkey=old_hotkey).first()
                    if macro:
                        self.logger.info(f"Old Hotkey exists, updating to new hotkey and new actions")
                        macro.hotkey = hotkey  # Update to new hotkey
                        macro.actions = json.dumps(actions)
                else:
                    self.logger.info(f"We will be only updating the actions to the hotkey (if exists): {hotkey}")
                    macro = session.query(Macro).filter_by(hotkey=hotkey).first()
                    if macro:
                        self.logger.info(f"macro exists, we will update with new actions: {actions}")
                        macro.actions = json.dumps(actions)

            elif operation == "delete":
                self.logger.info(f"Delete operation requested")
                session.query(Macro).filter_by(hotkey=hotkey).delete()

        session.commit()
        session.close()
