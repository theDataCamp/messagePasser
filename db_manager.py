from sqlalchemy import create_engine, Column, Integer, String, Sequence
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class Macro(Base):
    __tablename__ = 'macros'
    id = Column(Integer, Sequence('macro_id_seq'), primary_key=True)
    hotkey = Column(String(50))
    actions = Column(String(500))


class MacroDBManager:
    def __init__(self, database_url):
        self.engine = create_engine(database_url)
        self.Session = sessionmaker(bind=self.engine)

    def add_macro(self, hotkey, actions):
        session = self.Session()
        new_macro = Macro(hotkey=hotkey, actions=actions)
        session.add(new_macro)
        session.commit()
        session.close()

    def delete_macro(self, hotkey):
        session = self.Session()
        session.query(Macro).filter_by(hotkey=hotkey).delete()
        session.commit()
        session.close()

    def edit_macro(self, hotkey, new_actions):
        session = self.Session()
        macro = session.query(Macro).filter_by(hotkey=hotkey).first()
        macro.actions = new_actions
        session.commit()
        session.close()

    def get_all_macros(self):
        session = self.Session()
        macros = session.query(Macro).all()
        session.close()
        return macros
