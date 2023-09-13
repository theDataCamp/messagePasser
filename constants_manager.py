# constants_manager.py
import yaml

"""
Uses:
from constants_manager import constants

print(constants.get('BUFFER_SIZE'))
print(constants['AUTH_SUCCESS'])
print('BUFFER_SIZE' in constants)  # Check if key exists

The PyYAML library does its best to infer 
the types of values in a YAML document based on the YAML specification. 
So, for common scalar types like strings, integers, and floats, 
PyYAML will automatically handle the conversion for you.
"""


class ConstantsManager:
    def __init__(self, filename='constants.yaml'):
        with open(filename, 'r') as file:
            self._constants = yaml.safe_load(file)

    def get(self, key, default=None):
        return self._constants.get(key, default)

    def __getitem__(self, key):
        return self._constants[key]

    def __contains__(self, key):
        return key in self._constants


# Singleton instance for easy import and use
constants = ConstantsManager()
