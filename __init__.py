""" Plugin manager
  @file plugmgr/__init__.py
  @author Bruno Morais <brunosmmm@gmail.com>
"""

import importlib
import logging
from periodicpy.plugmgr.plugin import Module, ModuleArgument, ModuleCapabilities
from periodicpy.plugmgr.plugin.exception import ModuleLoadError, ModuleAlreadyLoadedError, ModuleNotLoadedError, ModuleMethodError
from periodicpy.plugmgr.exception import HookNotAvailableError
import re

MODULE_HANDLER_LOGGING_KWARGS = ['log_info', 'log_warning', 'log_error']

#helper functions
def handle_multiple_instance(module_name, loaded_module_list):

    instance_list = []
    for module in loaded_module_list:
        m = re.match(r"{}-([0-9]+)".format(module_name), module)
        if m != None:
            instance_list.append(int(m.group(1)))

    if len(instance_list) == 0:
        return 1

    return sorted(instance_list)[-1] + 1

class ModuleManagerHookActions(object):
    NO_ACTION = 0
    LOAD_MODULE = 1
    UNLOAD_MODULE = 2

class ModuleManager(object):
    """Module manager class"""
    def __init__(self, central_log, plugin_path):

        self.found_modules = {}
        self.loaded_modules = {}
        self.logger = logging.getLogger('{}.drvman'.format(central_log))

        #hooks
        self.attached_hooks = {'drvman.new_node' : [],
                               'drvman.rem_node' : []}

        self.custom_hooks = {}

        self.plugin_path = plugin_path
        #discover modules
        self.discover_modules()

    def install_custom_hook(self, hook_name, callback):
        self.custom_hooks[hook_name] = callback

    def install_driver_hook(self, attach_to, callback, action, driver_class):
        #so simple?
        if attach_to in self.attached_hooks:
            self.attached_hooks[attach_to].append((callback, action, driver_class))
            self.logger.debug('callback {} installed into hook {} with action {}'.format(callback,
                                                                                         attach_to,
                                                                                         action))
            return

        raise HookNotAvailableError('the requested hook is not available')

    #default manager hooks
    def new_node_discovered_event(self, **kwargs):
        for attached_callback in self.attached_hooks['drvman.new_node']:
            if attached_callback[0](**kwargs):
                if attached_callback[1] == ModuleManagerHookActions.LOAD_MODULE:
                    #load the module!
                    self.logger.debug('some hook returned true, loading module {}'.format(attached_callback[2]))
                    #module must accept same kwargs, this is mandatory with this discovery event
                    self.load_module(attached_callback[2].get_module_desc().arg_name,
                                     **kwargs)

    #def driver_post_load_hook()

    def node_removed_event(self, **kwargs):
        pass

    def discover_modules(self):

        module_root = importlib.import_module(self.plugin_path)
        module_list = module_root.MODULES

        for module in module_list:

            #ignore root
            if module == '__init__':
                continue

            try:
                the_mod = importlib.import_module('{}.{}'.format(self.plugin_path, module))
                module_class = the_mod.discover_module(self)
                self.found_modules[module_class.get_module_desc().arg_name] = module_class
                self.logger.info('Discovered module "{}"'.format(module_class.get_module_desc().arg_name))
            except ImportError as error:
                self.logger.warning('could not register python module: {}'.format(error.message))
            except Exception as error:
                #catch anything else because this cannot break the application
                self.logger.warning('could not register module {}: {}'.format(module,error.message))

    def load_module(self, module_name, **kwargs):
        """Load a module that has been previously discovered"""
        if module_name not in self.found_modules:
            raise ModuleLoadError('invalid module name')

        #insert self object in kwargs for now
        kwargs.update({'plugmgr' : self})

        if module_name in self.loaded_modules:
            if ModuleCapabilities.MultiInstanceAllowed not in self.found_modules[module_name].get_capabilities():
                raise ModuleAlreadyLoadedError('module is already loaded')

            #handle multiple instances
            multi_inst_name = module_name + '-{}'.format(handle_multiple_instance(module_name,
                                                                                  self.loaded_modules.keys()))
            self.loaded_modules[multi_inst_name] = self.found_modules[module_name](module_id=multi_inst_name,
                                                                                   handler=self.module_handler,
                                                                                   **kwargs)
            self.logger.info('Loaded module "{}" as "{}"'.format(module_name, multi_inst_name))
            return multi_inst_name

        #load (create object)
        self.loaded_modules[module_name] = self.found_modules[module_name](module_id=module_name,
                                                                           handler=self.module_handler,
                                                                           **kwargs)

        self.logger.info('Loaded module "{}"'.format(module_name))
        return module_name

    def get_module_info(self, module_name):
        if module_name in self.found_modules:
            return self.found_modules[module_name].get_module_info()

        self.logger.warn('requested module "{}" not found'.format(module_name))
        return None

    def get_module_property(self, module_name, property_name):
        try:
            return self.loaded_modules[module_name].get_property_value(property_name)
        except Exception:
            return None

    def get_module_property_list(self, module_name):
        if module_name in self.found_modules:
            return self.found_modules[module_name].get_module_properties()

        self.logger.warn('requested module "{}" not found'.format(module_name))
        return None

    def get_module_method_list(self, module_name):
        if module_name in self.found_modules:
            return self.found_modules[module_name].get_module_methods()

        self.logger.warn('requested module "{}" not found'.format(module_name))
        return None

    def call_module_method(self, instance_name, method_name, **kwargs):
        if instance_name in self.found_modules:
            try:
                return self.loaded_modules[instance_name].call_method(method_name, **kwargs)
            except ModuleMethodError as e:
                self.logger.warn('call to method "{}" of instance "{}" failed with: "{}"'.format(method_name,
                                                                                                 instance_name,
                                                                                                 e.message))
                return None

        self.logger.warn('requested instance "{}" not found'.format(instance_name))
        return None

    def list_loaded_modules(self):

        #build list of modules and return with to which node they're attached

        attached_modules = {}
        for module_name, module in self.loaded_modules.iteritems():
            attached_modules[module_name] = module.get_loaded_kwarg('attached_node')

        return attached_modules

    def unload_module(self, module_name):

        if module_name not in self.loaded_modules:
            raise ModuleNotLoadedError('cant unload {}: module not loaded'.format(module_name))

        #do unloading procedure
        self.loaded_modules[module_name].unload_module()

        #remove
        del self.loaded_modules[module_name]

    def list_discovered_modules(self):
        return [x.get_module_desc() for x in self.found_modules.values()]

    def module_handler(self, which_module, *args, **kwargs):

        if 'get_available_drivers' in args:
            return [x.get_module_desc().arg_name for x in self.found_modules.values()]

        for kwg, value in kwargs.iteritems():
            if kwg in MODULE_HANDLER_LOGGING_KWARGS:
                #dispatch logger
                self._log_module_message(which_module, kwg, value)
                return None

            if kwg == 'call_custom_hook':
                if value[0] in self.custom_hooks:
                    return self.custom_hooks[value[0]](*value[1])

    def _log_module_message(self, module, level, message):

        if level == 'log_info':
            self.logger.info("{}: {}".format(module, message))
        elif level == 'log_warning':
            self.logger.warning("{}: {}".format(module, message))
        elif level == 'log_error':
            self.logger.error("{}: {}".format(module, message))
