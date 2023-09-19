# custom_logger.py

import logging
import logging.config
import yaml
import os

"""
Format for the name-> if using a module logger then the {MODULENAME}ModuleLogger, where MODULENAME 
is the name of the module
if using it in a class -> {CLASSBANE}ClassLogger
"""


class CustomLogger:
    _instance = None  # Singleton instance

    DEFAULT_CONFIG = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'simple': {
                'format': '%(asctime)s - %(name)s - [%(levelname)s] [%(threadName)s]'
                          '[%(module)s.%(funcName)s] %(message)s'
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'DEBUG',
                'formatter': 'simple',
            },
        },
        'loggers': {
            '': {
                'handlers': ['console'],
                'level': 'DEBUG',
            }
        }
    }

    CONFIG_PATH = 'logging_config.yaml'

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(CustomLogger, cls).__new__(cls)
            cls._instance.setup_logging()  # This initializes logging configuration
        return cls._instance

    def setup_logging(self):
        if os.path.exists(self.CONFIG_PATH):
            with open(self.CONFIG_PATH, 'r') as f:
                config = yaml.safe_load(f.read())
            logging.config.dictConfig(config)
        else:
            with open(self.CONFIG_PATH, 'w') as f:
                yaml.dump(self.DEFAULT_CONFIG, f)
            logging.config.dictConfig(self.DEFAULT_CONFIG)

    def get_logger(self, logger_name=None):
        return logging.getLogger(logger_name)
