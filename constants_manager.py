# constants_manager.py
import logging

from sqlalchemy import create_engine, Column, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import json

Base = declarative_base()

"""
How to use:

from constants_manager import ConstantsManager

# Initialize the ConstantsManager with a database URL
database_url = "sqlite:///constants.db"  # Using SQLite for this example
constants_manager = ConstantsManager(database_url)

# Set a constant value
constants_manager.set('BUFFER_SIZE', 8192)  # Setting it to an integer value

# Get the constant value
buffer_size = constants_manager.get('BUFFER_SIZE')
print(f"BUFFER_SIZE: {buffer_size}")  # Should print: BUFFER_SIZE: 8192

# Set a string constant
constants_manager.set('NEW_CONSTANT', 'HelloWorld')

# Get the string constant
new_value = constants_manager.get('NEW_CONSTANT')
print(f"NEW_CONSTANT: {new_value}")  # Should print: NEW_CONSTANT: HelloWorld

# Set a list constant
constants_manager.set('LIST_CONSTANT', [1, 2, 3, 4])

# Get the list constant
list_value = constants_manager.get('LIST_CONSTANT')
print(f"LIST_CONSTANT: {list_value}")  # Should print: LIST_CONSTANT: [1, 2, 3, 4]


"""


class Constants(Base):
    __tablename__ = 'constants'
    name = Column(String(50), primary_key=True)
    value = Column(String(500))


class ConstantsManager:
    _instance = None  # Singleton instance
    _is_initialized = False  # Additional flag to handle initialization

    DEFAULT_CONSTANTS = {
        'BUFFER_SIZE': 4096,
        'AUTH_SUCCESS': 'AUTH_SUCCESS',
        'AUTH_FAILED': 'AUTH_FAILED',
        'SHARED_SECRET': 'ThisIsATestSecretPassword',
        'HOST': '10.0.0.112',
        'PORT': 65432,
        'DB_NAME': 'macros.db'
    }

    def __new__(cls, database_url=None):
        if not cls._instance:
            logging.debug("This is the first creation of this instance")
            cls._instance = super(ConstantsManager, cls).__new__(cls)
            cls._instance._cache = {}
            if database_url:
                cls._instance.engine = create_engine(database_url)
                Base.metadata.create_all(cls._instance.engine)
                cls._instance.Session = sessionmaker(bind=cls._instance.engine)
                cls._instance._load_constants_into_cache()
        return cls._instance

    def _load_constants_into_cache(self):
        if not self._is_initialized:
            logging.debug("First time being initialized")
            session = self.Session()

            # Fetch existing constants from the DB
            logging.debug("Fetching constants from DB")
            constants_from_db = session.query(Constants).all()
            existing_constants = {const.name: json.loads(const.value) for const in constants_from_db}

            # Set defaults for any constants not in the DB
            logging.debug("Set defaults for any constants not in the DB")
            for name, value in self.DEFAULT_CONSTANTS.items():
                if name not in existing_constants:
                    logging.debug(f"{name} was not in DB, adding it to DB now")
                    serialized_value = json.dumps(value)
                    const = Constants(name=name, value=serialized_value)
                    session.add(const)
                    existing_constants[name] = value

            # Update the cache
            logging.debug("Updating constants cache with all existing constants (DB and default values)")
            self._cache = existing_constants

            session.commit()
            session.close()
            self._is_initialized = True

    def get(self, name):
        cached_value = self._cache.get(name)
        if cached_value is not None:
            return cached_value

        # If the value wasn't in cache (for some reason), fetch from the database and deserialize
        logging.info(f"{name} not found in cache, searching DB for it")
        session = self.Session()
        const = session.query(Constants).filter_by(name=name).first()
        session.close()
        if const:
            deserialized_value = json.loads(const.value)
            self._cache[name] = deserialized_value  # Cache it for future retrievals
            return deserialized_value
        logging.info(f"{name} was not found in cache or DB")
        return None  # If the constant wasn't found

    def set(self, name, value):
        session = self.Session()
        serialized_value = json.dumps(value)  # Convert value to its JSON string representation
        const = session.query(Constants).filter_by(name=name).first()
        if not const:
            const = Constants(name=name)
            session.add(const)
        const.value = serialized_value
        self._cache[name] = value  # Cache the original type
        session.commit()
        session.close()
