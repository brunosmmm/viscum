
class InterruptAlreadyInstalledError(Exception):
    pass

class MethodNotAvailableError(Exception):
    pass

class HookNotAvailableError(Exception):
    pass

class CannotUnloadError(Exception):
    pass

class HookAlreadyInstalledError(Exception):
    pass

class MethodAlreadyInstalledError(Exception):
    pass

class DeferModuleDiscovery(Exception):
    pass
