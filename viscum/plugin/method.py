"""Module method descriptor."""

from viscum.plugin.dtype import ModuleDataTypes


class ModuleMethod(object):
    """Method descriptor class."""

    def __init__(self,
                 method_desc,
                 method_args=None,
                 method_return=None,
                 method_call=None,
                 **kwargs):
        """Initialize.

        Args
        ----
        method_desc: str
            Friendly description of method
        method_args: dict
            Dictionary of arguments indexed by name
        method_return: ModuleDataTypes
            Data type
        method_call: function
            Actual method to be called
        kwargs: dict
            Extra keyword arguments to be stored at creation time
        """
        self.method_desc = method_desc
        if method_args is not None:
            self.method_args = method_args
        else:
            self.method_args = {}
        self.method_return = method_return
        self.method_call = method_call
        self.__dict__.update(kwargs)

    def add_arguments(self, arguments):
        """Add more arguments to the method description.

        Args
        ----
        arguments: dict
            Name-indexed argument dictionary
        """
        self.method_args.update(arguments)


class ModuleMethodArgument(object):
    """A method argument, descriptor class."""

    def __init__(self,
                 argument_desc,
                 argument_required=False,
                 data_type=ModuleDataTypes.VOID,
                 **kwargs):
        """Initialize.

        Args
        ----
        argument_desc: str
            Friendly description of argument
        argument_required: bool
            Whether this argument must be present or not
        data_type: ModuleDataTypes
            Data type of argument
        kwargs: dict
            Extra keyword arguments to be stored at creation time
        """
        self.argument_desc = argument_desc
        self.argument_required = argument_required
        self.data_type = data_type
        self.__dict__.update(kwargs)
