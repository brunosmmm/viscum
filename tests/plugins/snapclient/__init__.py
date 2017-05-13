from viscum.plugin import (Module,
                           ModuleArgument,
                           ModuleCapabilities)


class SnapClientDriver(Module):
    """SnapCast client dummy driver only for display purposes"""
    _module_desc = ModuleArgument('snapclient',
                                  'SnapCast client dummy driver')
    _capabilities = [ModuleCapabilities.MultiInstanceAllowed]

    def __init__(self, **kwargs):
        super(SnapClientDriver, self).__init__(**kwargs)

        # don't do anything!


def discover_module(**kwargs):
    return SnapClientDriver
