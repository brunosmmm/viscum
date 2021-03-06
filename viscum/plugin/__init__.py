"""Module Manager Plugin base class implementation."""

from collections import namedtuple
from viscum.plugin.exception import (ModuleLoadError,
                                     ModuleNotLoadedError,
                                     ModuleInvalidPropertyError,
                                     ModulePropertyPermissionError,
                                     ModuleMethodError)
from viscum.plugin.prop import (ModulePropertyPermissions,
                                ModuleProperty)
from viscum.plugin.method import ModuleMethod, ModuleMethodArgument
import json
import copy

# simple description for arguments
ModuleArgument = namedtuple('ModuleArgument', ['arg_name', 'arg_help'])


def read_json_from_file(filename):
    """Read JSON content from a file.

    Args
    ----
    filename: str
       File path
    returns: dictionary
    """
    data = {}
    with open(filename, 'r') as f:
        data = json.load(f)

    return data


def write_json_from_dict(filename, data):
    """Write formatted JSON data in file.

    Args
    ----
    filename: str
       File Path
    data: dict
       Data to be written
    """
    with open(filename, 'w') as f:
        json.dump(f, data)


class ModuleCapabilities(object):
    """Module capabilities enumeration."""

    MultiInstanceAllowed = 0


class Module(object):
    """Module (plugin) main class implementation."""

    # these members are required to be defined in
    # a static way, so information can be retrieved
    # before loading the module (i.e. creating the actual object)
    _required_kw = []  # list of mandatory kwargs for module loading
    _optional_kw = []  # list of optional kwargs for module loading
    _module_desc = ModuleArgument(None, None)  # module identifier
    _capabilities = []  # a list of the module's capabilities
    _properties = {}  # the module's properties, indexed by property name
    _methods = {}  # the module's methods, indexed by method name

    # these members are set at load-time
    _registered_id = None  # instance name of the module when registered
    _mod_handler = None  # a handler to access the module manager methods

    def __init__(self, module_id, handler, **kwargs):
        """Initialize module.

           kwargs will be checked and exceptions raised if
           the input is not satisfactory

        Args
        ----
        module_id: str
            Assigned instance name
        handler: function
            Callback assigned by module manager for transactions
        kwargs: dict
            Invoking arguments
        """
        # check the kwargs passed to constructor
        self._check_kwargs(**kwargs)

        # save passed kwargs
        self._loaded_kwargs = dict(kwargs)

        # create copies of static members
        self._methods = copy.deepcopy(self._methods)
        self._properties = copy.deepcopy(self._properties)

        # register module
        self.module_register(module_id, handler)

    @classmethod
    def get_capabilities(cls):
        """Return module's capabilities."""
        return cls._capabilities

    @classmethod
    def get_module_desc(cls):
        """Return module's description."""
        return cls._module_desc

    @classmethod
    def get_required_kwargs(cls):
        """Return a list of required arguments to spawn module."""
        return cls._required_kw

    @classmethod
    def get_optional_kwargs(cls):
        """Return a list of optional arguments."""
        return cls._optional_kw

    @classmethod
    def _check_kwargs(cls, **kwargs):
        """Verify if required kwargs are met, raise exception if not.

        Args
        ----
        kwargs: dict
            List of keyword arguments to check
        """
        for kwg in cls._required_kw:
            if kwg.arg_name not in kwargs:
                raise ModuleLoadError('missing argument: {}'
                                      .format(kwg.arg_name),
                                      cls._module_desc.arg_name)

    def module_unload(self):
        """Unload module procedure (module-specific, to be overriden)."""
        pass

    def module_register(self, module_id, handler):
        """Register module procedure, simply save information locally.

        Args
        ----
        module_id: str
            Assigned instance name
        handler: function
            Handler function
        """
        self._registered_id = module_id
        self._mod_handler = handler

    def handler_communicate(self, **kwargs):
        """Handle communication (receive messages) from manager.

        Args
        ----
        kwargs: dict
           Arguments
        """
        pass

    def interrupt_handler(self, *args, **kwargs):
        """Get attention of handler and execute some action.

        Args
        ----
        args: list
           Arguments
        kwargs: dict
           Keyword arguments
        """
        if self._mod_handler is None or self._registered_id is None:
            raise ModuleNotLoadedError('module is not registered')

        return self._mod_handler(self._registered_id, *args, **kwargs)

    def log_info(self, message):
        """Log a message, level INFO.

        Args
        ----
        message: str
           The message
        """
        self.interrupt_handler(log_info=message)

    def log_warning(self, message):
        """Log a message, level WARNING.

        Args
        ----
        message: str
           The message
        """
        self.interrupt_handler(log_warning=message)

    def log_error(self, message):
        """Log a message, level ERROR.

        Args
        ----
        message: str
           The message
        """
        self.interrupt_handler(log_error=message)

    def get_property_value(self, property_name):
        """Return the value of a property.

           Permissions are checked
        Args
        ----
        property_name: str
           Name of the property
        """
        if property_name in self._properties:
            if self._properties[property_name].permissions ==\
               ModulePropertyPermissions.READ or\
               self._properties[property_name].permissions ==\
               ModulePropertyPermissions.RW:
                if self._properties[property_name].getter is not None:
                    return self._properties[property_name].getter()
                else:
                    return None
            else:
                raise ModulePropertyPermissionError('property "{}" does not '
                                                    'have read permissions'
                                                    .format(property_name))

        raise ModuleInvalidPropertyError('object does not have property: "{}"'
                                         .format(property_name))

    def set_property_value(self, property_name, value):
        """Set the value of a property.

           Permissions are checked
        Args
        ----
        property_name: str
           Name of the property
        value: object
           Some value
        """
        if property_name in self._properties:
            if self._properties[property_name].permissions ==\
               ModulePropertyPermissions.WRITE or\
               self._properties[property_name].permissions ==\
               ModulePropertyPermissions.RW:
                if self._properties[property_name].setter is not None:
                    return self._properties[property_name].setter(value)
                else:
                    return None
            else:
                raise ModulePropertyPermissionError('property "{}" does not '
                                                    'have write permissions'
                                                    .format(property_name))

        raise ModuleInvalidPropertyError('object does not have property: "{}"'
                                         .format(property_name))

    def get_loaded_kwargs(self, arg_name):
        """Return the arguments that the module was loaded with.

        Args
        ----
        arg_name: str
            Name of argument to be checked
        """
        if arg_name in self._loaded_kwargs:
            return self._loaded_kwargs[arg_name]

        return None

    def call_method(self, __method_name, **kwargs):
        """Call a method declared by the module class.

           Method is called by name, returns whatever the module returns
        Args
        ----
        __method_name: str
            Name of method
        kwargs: dict
            keyword arguments passed to method
        """
        if __method_name in self._methods:
            method_args = self._methods[__method_name].method_args
            for kwg, m_arg in method_args.items():
                if m_arg.required and kwg not in kwargs:
                    # fail, didn't provide required argument
                    raise ModuleMethodError('missing required argument')

            # check for unknown kwargs
            for name, value in kwargs.items():
                if name not in method_args:
                    raise ModuleMethodError('unknown argument'
                                            ' "{}" passed'.format(name))

            return_value = None
            try:
                if self._methods[__method_name].method_call is not None:
                    return_value =\
                        self._methods[__method_name].method_call(**kwargs)
                else:
                    return_value = None
            except Exception:
                # placeholder
                raise

        else:
            raise ModuleMethodError('method {} does not exist'
                                    .format(__method_name))

        return return_value

    @classmethod
    def get_module_type(cls):
        """Return module type (identifier from description)."""
        return cls._module_desc.arg_name

    @classmethod
    def get_module_info(cls):
        """Return a dictionary contaning basic module description."""
        # return some information (serializable)
        module_info = {}
        module_info['module_type'] = cls._module_desc.arg_name
        module_info['module_desc'] = cls._module_desc.arg_help

        return module_info

    @staticmethod
    def build_module_descr(mod_info):
        """Build the description structure from a dictionary.

        Args
        ----
        mod_info: dict
            dictionary containing information
        """
        return ModuleArgument(arg_name=mod_info['module_type'],
                              arg_help=mod_info['module_desc'])

    @staticmethod
    def build_module_property_list(mod_prop):
        """Build the property list structure from a dictionary.

        Args
        ----
        mod_prop: dict
            Name-indexed dictionary of property descriptions
        """
        property_list = {}

        for prop_name, prop_data in mod_prop.items():
            property_list[prop_name] =\
                ModuleProperty(property_desc=prop_data['property_desc'],
                               permissions=prop_data['permissions'],
                               data_type=prop_data['data_type'])

        return property_list

    @staticmethod
    def build_module_method_list(mod_methods):
        """Build the method list structure from a dictionary.

        Args
        ----
        mod_methods: dict
            Name-indexed dictionary of method descriptions
        """
        method_list = {}

        for method_name, method_data in mod_methods.items():
            arg_list = {}
            for arg_name, arg_data in method_data['method_args'].items():
                arg_list[arg_name] =\
                    ModuleMethodArgument(argument_desc=arg_data['arg_desc'],
                                         required=arg_data['arg_required'],
                                         data_type=arg_data['arg_dtype'])

            method_list[method_name] =\
                ModuleMethod(method_desc=method_data['method_desc'],
                             method_args=arg_list,
                             method_return=method_data['method_return'])

        return method_list

    @staticmethod
    def build_module_structure(mod_struct):
        """Return all the basic module structures, built from a complete dictionary.

        Args
        ----
        mod_struct: dict
            Module structure dictionary
        """
        mod_descr = Module.build_module_descr(mod_struct['module_desc'])
        mod_props =\
            Module.build_module_property_list(mod_struct['module_properties'])
        mod_methods =\
            Module.build_module_method_list(mod_struct['module_methods'])

        return (mod_descr, mod_props, mod_methods)

    @staticmethod
    def build_module_structure_from_file(filename):
        """Return the basic module structures, built from JSON file.

        Args
        ----
        filename: str
           File path
        """
        return Module.build_module_structure(read_json_from_file(filename))

    @classmethod
    def get_module_properties(cls):
        """Return a list of the module's properties as a dictionary."""
        property_list = {}

        for property_name, prop in cls._properties.items():
            property_dict = {}
            # build dictionary
            property_dict['property_desc'] = prop.property_desc
            property_dict['permissions'] = prop.permissions
            property_dict['data_type'] = prop.data_type

            property_list[property_name] = property_dict

        return property_list

    @classmethod
    def get_module_methods(cls):
        """Return all the module's methods as a dictionary."""
        method_list = {}

        for method_name, method in cls._methods.items():
            method_dict = {}
            arg_list = {}

            method_dict['method_desc'] = method.method_desc

            # arguments
            for arg_name, arg in method.method_args.items():
                arg_dict = {}
                arg_dict['arg_desc'] = arg.argument_desc
                arg_dict['arg_required'] = arg.required
                arg_dict['arg_dtype'] = arg.data_type

                arg_list[arg_name] = arg_dict

            method_dict['method_args'] = arg_list
            method_dict['method_return'] = method.method_return

            method_list[method_name] = method_dict

        return method_list

    @classmethod
    def dump_module_structure(cls):
        """Dump the module's description as a JSON-serializable dictionary."""
        struct_dict = {}
        struct_dict['module_desc'] = cls.get_module_info()
        struct_dict['module_properties'] = cls.get_module_properties()
        struct_dict['module_methods'] = cls.get_module_methods()

        return struct_dict

    @classmethod
    def read_module_structure(cls, module_desc):
        """Uninmplemented."""
        return

    def _automap_methods(self, protected_methods=True):
        """Automatically connect property descriptions.

        Connects to methods in the class declaration with the naming
        convention as follows:
        Getter => _get_PROPERTYNAME()
        Setter => _set_PROPERTYNAME()

        Args
        ----
        protected_methods: bool
            connects to methods with underscore
        """
        for method_name, method in self._methods.items():
            if protected_methods:
                method_name = '_' + method_name
            try:
                method.method_call = self.__getattribute__(method_name)
            except AttributeError:
                # not found
                pass

    def _automap_properties(self, protected_methods=True):
        """Automatically connect method descriptions.

        Connects to methods of same name in the class declaration
        Args
        ----
        protected_methods: bool
            connects to methods with underscore
        """
        for prop_name, prop in self._properties.items():
            # search for object methods
            getter_name = 'get_'
            setter_name = 'set_'
            if protected_methods:
                getter_name = '_'+getter_name
                setter_name = '_'+setter_name

            try:
                prop.getter = self.__getattribute__(getter_name+prop_name)
            except AttributeError:
                # not found
                pass

            try:
                prop.setter = self.__getattribute__(setter_name+prop_name)
            except AttributeError:
                pass

    @classmethod
    def get_multi_inst_suffix(self):
        """Module-specific: should return a specific suffix.

        To be used if loading a multi-instance enabled module
        """
        return None
