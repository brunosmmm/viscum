""" Module exceptions
 @file plugmgr/exception.py
 @author Bruno Morais <brunosmmm@gmail.com>
"""

class ModuleLoadError(Exception):
    """Failure to load plugin for some reason"""
    def __init__(self, message, plugin=""):
        plugin_error_msg = "Error loading plugin {}: {}".format(plugin,message)
        super(ModuleLoadError, self).__init__(plugin_error_msg)

class ModuleNotLoadedError(Exception):
    pass

class ModuleAlreadyLoadedError(Exception):
    pass

class ModuleInvalidPropertyError(Exception):
    pass

class ModulePropertyPermissionError(Exception):
    pass

class ModuleMethodError(Exception):
    pass
