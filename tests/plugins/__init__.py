import os
import glob
import re

MODULE_NAME_REGEX = re.compile(r'.*\/([a-zA-Z0-9_]+)\/__init__\.py$')
MODULE_LIST = glob.glob(os.path.dirname(__file__)+'/[a-zA-z0-9_]*/__init__.py')
MODULES = []
for module_file in MODULE_LIST:
    if not os.path.isfile(module_file):
        continue

    m = MODULE_NAME_REGEX.match(module_file)
    if m is not None:
        MODULES.append(m.group(1))
