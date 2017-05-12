class ModuleManagerHookActions(object):
    """Actions executed on a hook returning true
    """
    NO_ACTION = 0
    LOAD_MODULE = 1
    UNLOAD_MODULE = 2


class ModuleManagerHook(object):
    """Module manager hook descriptor class
    """
    def __init__(self, owner):
        self.owner = owner
        self.attached_callbacks = []

    def attach_callback(self, callback):
        """Attaches a callback to the hook
        """
        if callback not in self.attached_callbacks:
            self.attached_callbacks.append(callback)

    def detach_callback(self, callback):
        """Detaches callback from the hook
        """
        if callback in self.attached_callbacks:
            self.attached_callbacks.remove(callback)

    def find_callback_by_argument(self, argument):
        """Find an attached callbacks by looking at the arguments
           specified for it
        """
        attached_list = []
        for callback in self.attached_callbacks:
            if callback.argument == argument:
                attached_list.append(callback)

        return attached_list
