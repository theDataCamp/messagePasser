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

    def delete_macro(self, hotkey):
        session = self.Session()
        session.query(Macro).filter_by(hotkey=hotkey).delete()
        session.commit()
        session.close()
        self._log_transaction("delete", hotkey)

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
        self.transactions.clear()

    def apply_transactions(self, transactions):
        session = self.Session()

        for transaction in transactions:
            operation = transaction.get("operation")
            hotkey = transaction.get("hotkey")
            actions = transaction.get("actions")
            old_hotkey = transaction.get("old_hotkey")

            if operation == "add":
                if not session.query(Macro).filter_by(hotkey=hotkey).first():
                    serialized_actions = json.dumps(actions)
                    new_macro = Macro(hotkey=hotkey, actions=serialized_actions)
                    session.add(new_macro)

            elif operation == "edit":
                if old_hotkey:
                    macro = session.query(Macro).filter_by(hotkey=old_hotkey).first()
                    if macro:
                        macro.hotkey = hotkey  # Update to new hotkey
                        macro.actions = json.dumps(actions)
                else:
                    macro = session.query(Macro).filter_by(hotkey=hotkey).first()
                    if macro:
                        macro.actions = json.dumps(actions)

            elif operation == "delete":
                session.query(Macro).filter_by(hotkey=hotkey).delete()

        session.commit()
        session.close()
