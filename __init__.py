""" Plugin manager
  @file plugmgr/__init__.py
  @author Bruno Morais <brunosmmm@gmail.com>
"""

import importlib
import imp
import logging
from periodicpy.plugmgr.plugin import Module, ModuleArgument, ModuleCapabilities
from periodicpy.plugmgr.plugin.exception import ModuleLoadError, ModuleAlreadyLoadedError, ModuleNotLoadedError, ModuleMethodError
from periodicpy.plugmgr.exception import HookNotAvailableError, CannotUnloadError
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
        self.attached_hooks = {'modman.module_loaded' : [],
                               'modman.module_unloaded' : [],
                               'modman.tick' : []}

        self.custom_hooks = {}
        self.custom_methods = {}

        self.plugin_path = plugin_path
        self.tick_counter = 0

    def module_system_tick(self):
        self.tick_counter += 1
        self._trigger_manager_hook('modman.tick', uptime=self.tick_counter)

    def install_custom_hook(self, hook_name):
        self.logger.debug('custom hook {} installed'.format(hook_name))
        self.custom_hooks[hook_name] = []

    def install_custom_method(self, method_name, callback):
        self.logger.debug('custom method "{}" installed, calls {}'.format(method_name, callback))
        self.custom_methods[method_name] = callback

    def attach_custom_hook(self, attach_to, callback, action, argument):
        if attach_to in self.custom_hooks:
            self.custom_hooks[attach_to].append((callback, action, argument))
            self.logger.debug('callback {} installed into custom hook {} with action {}'.format(callback,
                                                                                                attach_to,
                                                                                                action))
            return

        raise HookNotAvailableError('the requested hook is not available')

    def attach_manager_hook(self, attach_to, callback, action, driver_class):
        if attach_to in self.attached_hooks:
            self.attached_hooks[attach_to].append((callback, action, driver_class))
            self.logger.debug('callback {} installed into hook {} with action {}'.format(callback,
                                                                                         attach_to,
                                                                                         action))
            return

        raise HookNotAvailableError('the requested hook is not available')

    def discover_modules(self):

        module_root = imp.load_source('plugins', self.plugin_path+'/__init__.py')
        module_list = module_root.MODULES

        for module in module_list:
            #ignore root
            if module == '__init__':
                continue

            try:
                the_mod = imp.load_source(module, '{}/{}/__init__.py'.format(self.plugin_path, module))
                module_class = the_mod.discover_module(modman=self, plugin_path='{}/{}/'.format(self.plugin_path, module))
                self.found_modules[module_class.get_module_desc().arg_name] = module_class
                self.logger.info('Discovered module "{}"'.format(module_class.get_module_desc().arg_name))
            except ImportError as error:
                self.logger.warning('could not register python module: {}'.format(error.message))
            except Exception as error:
                raise
                #catch anything else because this cannot break the application
                self.logger.warning('could not register module {}: {}'.format(module,error.message))

    def load_module(self, module_name, **kwargs):
        self._load_module(module_name, **kwargs)

    def _load_module(self, module_name, loaded_by='modman', **kwargs):
        """Load a module that has been previously discovered"""
        if module_name not in self.found_modules:
            raise ModuleLoadError('invalid module name: "{}"'.format(module_name))

        #insert self object in kwargs for now
        kwargs.update({'plugmgr' : self,
                       'loaded_by' : loaded_by})

        if module_name in self.loaded_modules:
            if ModuleCapabilities.MultiInstanceAllowed not in self.found_modules[module_name].get_capabilities():
                raise ModuleAlreadyLoadedError('module is already loaded')

            #handle multiple instances
            multi_inst_name = module_name + '-{}'.format(handle_multiple_instance(module_name,
                                                                                  self.loaded_modules.keys()))
            self.loaded_modules[multi_inst_name] = self.found_modules[module_name](module_id=multi_inst_name,
                                                                                   handler=self.module_handler,
                                                                                   **kwargs)
            self.logger.info('Loaded module "{}" as "{}", loaded by "{}"'.format(module_name, multi_inst_name, loaded_by))
            self._trigger_manager_hook('modman.module_loaded', instance_name=multi_inst_name)
            return multi_inst_name

        #load (create object)
        self.loaded_modules[module_name] = self.found_modules[module_name](module_id=module_name,
                                                                           handler=self.module_handler,
                                                                           **kwargs)

        self.logger.info('Loaded module "{}", loaded by "{}"'.format(module_name, loaded_by))
        #trigger hooks
        self._trigger_manager_hook('modman.module_loaded', instance_name=module_name)
        return module_name

    def get_loaded_module_list(self):
        return self.loaded_modules.keys()

    def get_instance_type(self, instance_name):
        if instance_name in self.loaded_modules:
            return self.loaded_modules[instance_name].get_module_type()

        self.logger.warn('requested instance "{}" not found'.format(instance_name))
        return None

    def get_module_structure(self, module_name):
        if module_name in self.found_modules:
            return self.found_modules[module_name].dump_module_structure()

        self.logger.warn('requested module "{}" not found'.format(module_name))
        return None

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

    def set_module_property(self, instance_name, property_name, value):
        try:
            self.loaded_modules[instance_name].set_property_value(property_name, value)
            return True
        except Exception:
            return False

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

    def call_module_method(self, __instance_name, __method_name, **kwargs):
        if __instance_name in self.found_modules:
            try:
                return self.loaded_modules[__instance_name].call_method(__method_name, **kwargs)
            except ModuleMethodError as e:
                self.logger.warn('call to method "{}" of instance "{}" failed with: "{}"'.format(__method_name,
                                                                                                 __instance_name,
                                                                                                 e.message))
                return None

        self.logger.warn('requested instance "{}" not found'.format(__instance_name))
        return None

    def list_loaded_modules(self):

        #build list of modules and return with to which node they're attached

        attached_modules = {}
        for module_name, module in self.loaded_modules.iteritems():
            attached_modules[module_name] = module.get_loaded_kwarg('attached_node')

        return attached_modules

    def unload_module(self, module_name):
        self._unload_module(module_name)

    def _unload_module(self, module_name, requester='modman'):

        if module_name not in self.loaded_modules:
            raise ModuleNotLoadedError('cant unload {}: module not loaded'.format(module_name))

        if requester != self.loaded_modules[module_name].get_loaded_kwargs('loaded_by'):
            if requester != 'modman':
                raise CannotUnloadError('cannot unloaded: forbidden by module manager')

        #do unloading procedure
        self.loaded_modules[module_name].module_unload()

        #remove
        del self.loaded_modules[module_name]

        self.logger.info('module "{}" unloaded by "{}"'.format(module_name, requester))

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

            if kwg == 'call_custom_method':
                if value[0] in self.custom_methods:
                    return self.custom_methods[value[0]](*value[1])

            if kwg == 'attach_custom_hook':
                self.attach_custom_hook(value[0], *value[1])

            if kwg == 'load_module':
                self._load_module(value[0], which_module, **value[1])

            if kwg == 'unload_module':
                self._unload_module(value[0], which_module)

    def _log_module_message(self, module, level, message):

        if level == 'log_info':
            self.logger.info("{}: {}".format(module, message))
        elif level == 'log_warning':
            self.logger.warning("{}: {}".format(module, message))
        elif level == 'log_error':
            self.logger.error("{}: {}".format(module, message))

    def _trigger_hooks(self, hook_dict, hook_name, **kwargs):
        for attached_callback in hook_dict[hook_name]:
            if attached_callback[0](**kwargs):
                if attached_callback[1] == ModuleManagerHookActions.LOAD_MODULE:
                    #load the module!
                    self.logger.debug('some hook returned true, loading module {}'.format(attached_callback[2]))
                    #module must accept same kwargs, this is mandatory with this discovery event
                    self.load_module(attached_callback[2].get_module_desc().arg_name,
                                     **kwargs)
                elif attached_callback[1] == ModuleManagerHookActions.UNLOAD_MODULE:
                    #unload the attached module
                    self.logger.debug('a hook required module {} to be unloaded'.format(attached_callback[2]))
                    self.unload_module(attached_callback[2])

    def trigger_custom_hook(self, hook_name, **kwargs):
        self._trigger_hooks(self.custom_hooks, hook_name, **kwargs)

    def _trigger_manager_hook(self, hook_name, **kwargs):
        self._trigger_hooks(self.attached_hooks, hook_name, **kwargs)
