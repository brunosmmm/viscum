"""Module manager hooks."""


class ModuleManagerHookActions(object):
    """Actions executed on a hook returning true."""

    NO_ACTION = 0
    LOAD_MODULE = 1
    UNLOAD_MODULE = 2


class ModuleManagerHook(object):
    """Module manager hook descriptor class."""

    def __init__(self, owner):
        """Initialize.

        Args
        ----
        owner: str
            module or instance name
        """
        self.owner = owner
        self.attached_callbacks = []

    def attach_callback(self, callback):
        """Attach a callback to the hook.

        Args
        ----
        callback: function
            callback function
        """
        if callback not in self.attached_callbacks:
            self.attached_callbacks.append(callback)

    def detach_callback(self, callback):
        """Detach callback from the hook.

        Args
        ----
        callback: function
            callback function
        """
        if callback in self.attached_callbacks:
            self.attached_callbacks.remove(callback)

    def find_callback_by_argument(self, argument):
        """Find an attached callbacks by the arguments specified for it.

        Args
        ----
        argument: object
           An argument
        """
        attached_list = []
        for callback in self.attached_callbacks:
            if callback.argument == argument:
                attached_list.append(callback)

        return attached_list
