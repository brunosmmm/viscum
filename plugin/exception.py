""" Module exceptions
"""

class ModuleLoadError(Exception):
    """Failure to load plugin for some reason"""
    def __init__(self, message, plugin=""):
        plugin_error_msg = "Error loading plugin {}: {}".format(plugin,message)
        super(ModuleLoadError, self).__init__(plugin_error_msg)

class ModuleNotLoadedError(Exception):
    """Raised when the manager is asked for an instance of a plugin that has not been loaded
    """
    pass

class ModuleAlreadyLoadedError(Exception):
    """Raised when the system tries to load a plugin that is already loaded and doesn't support multiple instances
    """
    pass

class ModuleInvalidPropertyError(Exception):
    """Invalid property of a module being accessed
    """
    pass

class ModulePropertyPermissionError(Exception):
    """Permissions violation error
    """
    pass

class ModuleMethodError(Exception):
    """Error while calling a method
    """
    pass
