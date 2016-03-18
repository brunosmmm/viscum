from collections import namedtuple
from periodicpy.plugmgr.plugin.exception import ModuleLoadError, ModuleNotLoadedError, ModuleInvalidPropertyError, ModulePropertyPermissionError, ModuleMethodError
from periodicpy.plugmgr.plugin.prop import ModulePropertyPermissions
import json

#simple description for arguments
ModuleArgument = namedtuple('ModuleArgument', ['arg_name', 'arg_help'])

class ModuleCapabilities(object):
    MultiInstanceAllowed = 0

class Module(object):
    _required_kw = []
    _optional_kw = []
    _module_desc = ModuleArgument(None, None)
    _capabilities = []
    _properties = {}
    _methods = {}
    _registered_id = None
    _mod_handler = None

    def __init__(self, module_id, handler, **kwargs):
        self._check_kwargs(**kwargs)

        #save loaded kwargs
        self._loaded_kwargs = dict(kwargs)

        #register module
        self.module_register(module_id, handler)

    @classmethod
    def get_capabilities(cls):
        return cls._capabilities

    @classmethod
    def get_module_desc(cls):
        """get module description"""
        return cls._module_desc

    @classmethod
    def get_required_kwargs(cls):
        """return a list of required arguments to spawn module"""
        return cls._required_kw

    @classmethod
    def get_optional_kwargs(cls):
        """return a list of optional arguments"""
        return cls._optional_kw

    @classmethod
    def _check_kwargs(cls, **kwargs):
        """verify if required kwargs are met"""
        for kwg in cls._required_kw:
            if kwg.arg_name not in kwargs:
                raise ModuleLoadError('missing argument: {}'.format(kwg.arg_name), cls._module_desc.arg_name)

    def module_unload(self):
        """Unload module procedure (module-specific)"""
        pass

    def module_register(self, module_id, handler):
        """Register module procedure"""
        self._registered_id = module_id
        self._mod_handler = handler

    def handler_communicate(self, **kwargs):
        """Handle communication from manager (module-specific)"""
        pass

    def interrupt_handler(self, *args, **kwargs):
        """Get attention of handler"""
        if self._mod_handler == None or self._registered_id == None:
            raise ModuleNotLoadedError('module is not registered')

        return self._mod_handler(self._registered_id, *args, **kwargs)

    def log_info(self, message):
        self.interrupt_handler(log_info=message)

    def log_warning(self, message):
        self.interrupt_handler(log_warning=message)

    def log_error(self, message):
        self.interrupt_handler(log_error=message)

    def get_property_value(self, property_name):
        if property_name in self._properties:
            if self._properties[property_name].permissions == ModulePropertyPermissions.READ or\
               self._properties[property_name].permissions == ModulePropertyPermissions.RW:
                return self._properties[property_name].getter()
            else:
                raise ModulePropertyPermissionError('property "{}" does not have read permissions'.format(property_name))

        raise ModuleInvalidPropertyError('object does not have property: "{}"'.format(property_name))

    def set_property_value(self, property_name, value):
        if property_name in self._properties:
            if self._properties[property_name].permissions == ModulePropertyPermissions.WRITE or\
               self._properties[property_name].permissions == ModulePropertyPermissions.RW:
                self._properties[property_name].setter(value)
            else:
                raise ModulePropertyPermissionError('property "{}" does not have write permissions'.format(property_name))

        raise ModuleInvalidPropertyError('object does not have property: "{}"'.format(property_name))

    def get_loaded_kwarg(self, arg_name):
        if arg_name in self._loaded_kwargs:
            return self._loaded_kwargs[arg_name]

        return None

    def call_method(self, __method_name, **kwargs):
        if __method_name in self._methods:
            for kwg, m_arg in self._methods[__method_name].method_args.iteritems():
                if m_arg.required and kwg not in kwargs:
                    #fail, didn't provide required argument
                    raise ModuleMethodError('missing required argument')

            return_value = None
            try:
                return_value = self._methods[__method_name].method_call(**kwargs)
            except Exception:
                #placeholder
                raise

        else:
            raise ModuleMethodError('method {} does not exist'.format(__method_name))

        return return_value

    @classmethod
    def get_module_type(cls):
        return cls._module_desc.arg_name

    @classmethod
    def get_module_info(cls):

        #return some information (serializable)
        module_info = {}
        module_info['module_desc'] = cls._module_desc.arg_help

        return module_info

    @classmethod
    def get_module_properties(cls):
        property_list = {}

        for property_name, prop in cls._properties.iteritems():
            property_dict = {}
            #build dictionary
            property_dict['property_desc'] = prop.property_desc
            property_dict['permissions'] = prop.permissions
            property_dict['data_type'] = prop.data_type

            property_list[property_name] = property_dict

        return property_list

    @classmethod
    def get_module_methods(cls):
        method_list = {}

        for method_name, method in cls._methods.iteritems():
            method_dict = {}
            arg_list = {}

            method_dict['method_desc'] = method.method_desc

            #arguments
            for arg_name, arg in method.method_args.iteritems():
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
        struct_dict = {}
        struct_dict['module_desc'] = cls.get_module_info()
        struct_dict['module_properties'] = cls.get_module_properties()
        struct_dict['module_methods'] = cls.get_module_methods()

        return struct_dict

    def _automap_methods(self, protected_methods=True):
        for method_name, method in self._methods.iteritems():
            if protected_methods:
                method_name = '_' + method_name
            try:
                method.method_call = self.__getattribute__(method_name)
            except AttributeError:
                #not found
                pass

    def _automap_properties(self, protected_methods=True):
        for prop_name, prop in self._properties.iteritems():
            #search for object methods
            getter_name = 'get_'
            setter_name = 'set_'
            if protected_methods:
                getter_name = '_'+getter_name
                setter_name = '_'+setter_name

            try:
                prop.getter = self.__getattribute__(getter_name+prop_name)
            except AttributeError:
                #not found
                pass

            try:
                prop.setter = self.__getattribute__(setter_name+prop_name)
            except AttributeError:
                pass
