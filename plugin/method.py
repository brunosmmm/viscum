from plugmgr.plugin.dtype import ModuleDataTypes

#driver method
class ModuleMethod(object):
    def __init__(self,
                 method_desc,
                 method_args={},
                 method_return=None,
                 method_call=None,
                 **kwargs):

        self.method_desc = method_desc
        self.method_args = method_args
        self.method_return = method_return
        self.method_call = method_call
        self.__dict__.update(kwargs)

    def add_arguments(self, arguments):
        self.method_args.update(arguments)

class ModuleMethodArgument(object):
    def __init__(self,
                 argument_desc,
                 argument_required=False,
                 data_type=ModuleDataTypes.VOID,
                 **kwargs):
        self.argument_desc = argument_desc
        self.argument_required = argument_required
        self.data_type = data_type
        self.__dict__.update(kwargs)
