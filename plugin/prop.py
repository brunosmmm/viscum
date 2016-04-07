"""Module property description
"""
from viscum.plugin.dtype import ModuleDataTypes


class ModulePropertyPermissions(object):
    """Property permissions enum"""
    READ = 0
    WRITE = 1
    RW = 2


class ModuleProperty(object):
    """Module property descriptor class
    """
    def __init__(self,
                 property_desc,
                 permissions=ModulePropertyPermissions.RW,
                 getter=None,
                 setter=None,
                 data_type=ModuleDataTypes.VOID,
                 **kwargs):
        """The constructor
        """
        self.property_desc = property_desc
        self.permissions = permissions
        self.getter = getter
        self.setter = setter
        self.data_type = data_type

        # hacky hack
        self.__dict__.update(kwargs)
