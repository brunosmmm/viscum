"""Module manager-specific exceptions."""


class InterruptAlreadyInstalledError(Exception):
    """Interrupt is already installed."""

    pass


class MethodNotAvailableError(Exception):
    """Requested method is not available."""

    pass


class HookNotAvailableError(Exception):
    """Requested hook is not available."""

    pass


class CannotUnloadError(Exception):
    """Cannot unload module as requested."""

    pass


class HookAlreadyInstalledError(Exception):
    """Hook is already installed."""

    pass


class MethodAlreadyInstalledError(Exception):
    """Method is already installed."""

    pass


class DeferModuleDiscovery(Exception):
    """Defer discovery of a module."""

    pass
