from periodicpy.plugmgr.plugin.dtype import ModuleDataTypes

class ModulePropertyPermissions(object):
    READ = 0
    WRITE = 1
    RW = 2

#driver property
class ModuleProperty(object):
    def __init__(self,
                 property_desc,
                 permissions=ModulePropertyPermissions.RW,
                 getter=None,
                 setter=None,
                 data_type=ModuleDataTypes.VOID,
                 **kwargs):

        self.property_desc = property_desc
        self.permissions = permissions
        self.getter = getter
        self.setter = setter
        self.data_type = data_type

        #hacky hack
        self.__dict__.update(kwargs)
