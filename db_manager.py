import json
import logging

from sqlalchemy import create_engine, Column, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class Macro(Base):
    __tablename__ = 'macros'
    hotkey = Column(String(50), primary_key=True)
    actions = Column(String(500))


class MacroDBManager:
    def __init__(self, database_url):
        self.engine = create_engine(database_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def add_macro(self, hotkey, actions):
        logging.info(f"Adding: {hotkey} with actions: {actions}")
        session = self.Session()
        serialized_actions = json.dumps(actions)
        new_macro = Macro(hotkey=hotkey, actions=serialized_actions)
        session.add(new_macro)
        session.commit()
        session.close()

    def delete_macro(self, hotkey):
        session = self.Session()
        session.query(Macro).filter_by(hotkey=hotkey).delete()
        session.commit()
        session.close()

    def edit_macro(self, old_hotkey, new_hotkey, new_actions):
        logging.info(f"updating: {old_hotkey} to -> {new_hotkey} actions: {new_actions}")
        session = self.Session()
        macro = session.query(Macro).filter_by(hotkey=old_hotkey).first()
        if macro:
            logging.info(f"found old macro, beginning update")
            macro.hotkey = new_hotkey
            macro.actions = json.dumps(new_actions)
            session.commit()
        session.close()

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
