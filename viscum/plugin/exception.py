"""Module exceptions."""


class ModuleLoadError(Exception):
    """Failure to load plugin for some reason."""

    def __init__(self, message, plugin=""):
        """Initialize.

        Args
        ----
        message: str
           Error message
        plugin: str
           Module or instance name
        """
        plugin_error_msg = "Error loading plugin {}: {}".format(plugin,
                                                                message)
        super(ModuleLoadError, self).__init__(plugin_error_msg)


class ModuleNotLoadedError(Exception):
    """Module has not been loaded."""

    pass


class ModuleAlreadyLoadedError(Exception):
    """Module is already loaded and doesnt support multiple instances."""

    pass


class ModuleInvalidPropertyError(Exception):
    """Invalid property of a module being accessed."""

    pass


class ModulePropertyPermissionError(Exception):
    """Permissions violation error."""

    pass


class ModuleMethodError(Exception):
    """Error while calling a method."""

    pass
