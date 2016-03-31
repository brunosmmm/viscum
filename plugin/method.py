"""Module method descriptor
"""
from periodicpy.plugmgr.plugin.dtype import ModuleDataTypes

class ModuleMethod(object):
    """Method descriptor class
    """
    def __init__(self,
                 method_desc,
                 method_args=None,
                 method_return=None,
                 method_call=None,
                 **kwargs):
        """The constructor, simple
        """

        self.method_desc = method_desc
        if method_args != None:
            self.method_args = method_args
        else:
            self.method_args = {}
        self.method_return = method_return
        self.method_call = method_call
        self.__dict__.update(kwargs)

    def add_arguments(self, arguments):
        """Add more arguments to the method description
        """
        self.method_args.update(arguments)

class ModuleMethodArgument(object):
    """A method argument, descriptor class
    """
    def __init__(self,
                 argument_desc,
                 argument_required=False,
                 data_type=ModuleDataTypes.VOID,
                 **kwargs):
        """The constructor
        """
        self.argument_desc = argument_desc
        self.argument_required = argument_required
        self.data_type = data_type
        self.__dict__.update(kwargs)
