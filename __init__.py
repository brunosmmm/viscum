""" Plugin manager
"""

import importlib
import imp
import logging
from collections import namedtuple
from periodicpy.plugmgr.plugin import Module, ModuleArgument, ModuleCapabilities
from periodicpy.plugmgr.plugin.exception import ModuleLoadError, ModuleAlreadyLoadedError,\
    ModuleNotLoadedError, ModuleMethodError, ModulePropertyPermissionError, ModuleInvalidPropertyError
from periodicpy.plugmgr.exception import *
from periodicpy.plugmgr.scripting import ModuleManagerScript, DeferScriptLoading
import re
import glob
import os

MODULE_HANDLER_LOGGING_KWARGS = ['log_info', 'log_warning', 'log_error']

#helper functions
def handle_multiple_instance(module_name, loaded_module_list):
    """Handle multiple instance plugin loading, returns suffix based on instance count
    """
    instance_list = []
    for module in loaded_module_list:
        m = re.match(r"{}-([0-9]+)".format(module_name), module)
        if m != None:
            instance_list.append(int(m.group(1)))

    if len(instance_list) == 0:
        return 1

    return sorted(instance_list)[-1] + 1

class ModuleManagerHookActions(object):
    """Actions executed on a hook returning true
    """
    NO_ACTION = 0
    LOAD_MODULE = 1
    UNLOAD_MODULE = 2

class ModuleManagerHook(object):
    """Module manager hook descriptor class
    """
    def __init__(self, owner):
        self.owner = owner
        self.attached_callbacks = []

    def attach_callback(self, callback):
        """Attaches a callback to the hook
        """
        if callback not in self.attached_callbacks:
            self.attached_callbacks.append(callback)

    def detach_callback(self, callback):
        """Detaches callback from the hook
        """
        if callback in self.attached_callbacks:
            self.attached_callbacks.remove(callback)

    def find_callback_by_argument(self, argument):
        """Find an attached callbacks by looking at the arguments
           specified for it
        """
        attached_list = []
        for callback in self.attached_callbacks:
            if callback.argument == argument:
                attached_list.append(callback)

        return attached_list

ModuleManagerMethod = namedtuple('ModuleManagerMethod', ['call', 'owner'])
HookAttacher = namedtuple('HookAttacher', ['callback', 'action', 'argument'])

class ModuleManager(object):
    """Module manager class"""
    def __init__(self, central_log, plugin_path, script_path):

        self.found_modules = {}
        self.loaded_modules = {}
        self.logger = logging.getLogger('{}.drvman'.format(central_log))

        #hooks
        self.attached_hooks = {'modman.module_loaded' : ModuleManagerHook('modman'),
                               'modman.module_unloaded' : ModuleManagerHook('modman'),
                               'modman.tick' : ModuleManagerHook('modman')}

        self.custom_hooks = {}
        self.custom_methods = {}
        self.external_interrupts = {}

        self.scripts = {}

        self.plugin_path = plugin_path
        self.script_path = script_path
        self.tick_counter = 0

        #states
        self.discovery_active = False

        #module discovery deferral
        self.deferred_discoveries = {}

    def module_system_tick(self):
        """Timer function called by main loop
        """
        self.tick_counter += 1
        self._trigger_manager_hook('modman.tick', uptime=self.tick_counter)

    def install_custom_hook(self, hook_name):
        """Installs a custom hook into the manager system
        """
        self._install_custom_hook(hook_name)

    def _install_custom_hook(self, hook_name, installed_by='modman'):
        """Inner function to actually install the custom hook, with
           owner information
        """
        if hook_name in self.custom_hooks:
            raise HookAlreadyInstalledError('hook is already installed')

        self.logger.debug('custom hook {} installed'.format(hook_name))
        self.custom_hooks[hook_name] = ModuleManagerHook(installed_by)

    def install_custom_method(self, method_name, callback):
        """Install a custom method, made available to all loaded modules
        """
        self._install_custom_method(method_name, callback)

    def _install_custom_method(self, method_name, callback, installed_by='modman'):
        """Inner function to install the custom method, with
           owner information
        """
        if method_name in self.custom_methods:
            raise MethodAlreadyInstalledError('method is already installed')

        self.logger.debug('custom method "{}" installed, calls {}'.format(method_name, callback))
        self.custom_methods[method_name] = ModuleManagerMethod(call=callback, owner=installed_by)

    def call_custom_method(self, method_name, *args, **kwargs):
        """Calls a custom method, if available
        """
        if method_name in self.custom_methods:
            return self.custom_methods[method_name].call(*args, **kwargs)

        raise MethodNotAvailableError('requested method is not available')

    def attach_custom_hook(self, attach_to, callback, action, argument):
        """Attaches a callback to a custom hook, if available
        """
        if attach_to in self.custom_hooks:
            self.custom_hooks[attach_to].attach_callback(HookAttacher(callback=callback, action=action, argument=argument))
            self.logger.debug('callback {} installed into custom hook {} with action {}'.format(callback,
                                                                                                attach_to,
                                                                                                action))
            return

        raise HookNotAvailableError('the requested hook is not available')

    def attach_manager_hook(self, attach_to, callback, action, driver_class):
        """Attaches a callback to a manager default hook
        """
        if attach_to in self.attached_hooks:
            self.attached_hooks[attach_to].attach_callback(HookAttacher(callback=callback, action=action, argument=driver_class))
            self.logger.debug('callback {} installed into hook {} with action {}'.format(callback,
                                                                                         attach_to,
                                                                                         action))
            return

        raise HookNotAvailableError('the requested hook is not available')

    def install_interrupt_handler(self, interrupt_key, callback):
        """Installs a custom interrupt handler
        """
        self._install_interrupt_handler(interrupt_key, callback)

    def _install_interrupt_handler(self, interrupt_key, callback, installed_by='modman'):
        """Inner function to install a interrupt handler,
           with owner information
        """
        if interrupt_key in self.external_interrupts:
            raise InterruptAlreadyInstalledError('interrupt is already installed')

        self.logger.debug('custom interrupt "{}" was installed, calls "{}"'.format(interrupt_key, callback))
        self.external_interrupts[interrupt_key] = ModuleManagerMethod(call=callback, owner=installed_by)

    def require_discovered_module(self, module_type):
        """Require a certain module to be present at discovery time
           if the module is not present (not discovered), then raises an
           exception that ultimately defers the discovery until such
           module is discovered
        """
        if self.discovery_active:
            if module_type not in self.found_modules:
                raise DeferModuleDiscovery(module_type)

    def _module_discovery(self, module):
        """Main module discovery routine, tries to load a module file
        """
        #ignore root
        if module == '__init__':
            return

        try:
            the_mod = imp.load_source(module, '{}/{}/__init__.py'.format(self.plugin_path, module))
            self.logger.info('inspecting module file: "{}"'.format(module))
            #guard discovery procedure
            self.discovery_active = True
            module_class = the_mod.discover_module(modman=self, plugin_path='{}/{}/'.format(self.plugin_path, module))
            self.found_modules[module_class.get_module_desc().arg_name] = module_class
            self.logger.info('Discovery of module "{}" succeeded'.format(module_class.get_module_desc().arg_name))
        except ImportError as error:
            self.logger.warning('could not register python module: {}'.format(error.message))
        except DeferModuleDiscovery as ex:
            self.logger.info('deferring discovery of module')
            #hacky
            self.deferred_discoveries[module] = ex.message
        except Exception as error:
            raise #debug
            #catch anything else because this cannot break the application
            self.logger.warning('could not register module {}: {}'.format(module,error.message))

        #check for deferrals that depend on the previous loaded module
        deferred_done = []
        for deferred, dependency in self.deferred_discoveries.iteritems():
            if dependency == module:
                #discover (recursive!)
                self.logger.debug('dependency for deferred "{}" met; discovering now'.format(deferred))
                self._module_discovery(deferred)
                deferred_done.append(deferred)

        #remove done deferrals
        for deferred in deferred_done:
            del self.deferred_discoveries[deferred]

        self.discovery_active = False

    def discover_modules(self):
        """Discovery routine wrapper, iterates through all found files in the
           plugins subfolder
        """
        module_root = imp.load_source('plugins', self.plugin_path+'/__init__.py')
        module_list = module_root.MODULES

        for module in module_list:
            self._module_discovery(module)

        if len(self.deferred_discoveries) > 0:
            self.logger.warning('some modules could not be discovered because they had dependencies that were not met: {}'.format(self.deferred_discoveries.keys()))

    def discover_scripts(self):
        """Discover available scripts
        """
        script_files = glob.glob(os.path.join(self.script_path, '*.py'))

        for script in script_files:
            try:
                self.scripts[script] = ModuleManagerScript(script, self, initialize=True)
            except DeferScriptLoading as ex:
                self.logger.debug('deferring load of script {}, which requires module {}'.format(script, ex.message))

    def _is_module_type_present(self, module_class_name):
        """Returns wether any module of a certain type has been loaded
        """
        for mod_name, mod_obj in self.loaded_modules.iteritems():
            if mod_obj.get_module_type() == module_class_name:
                return True

        return False

    def load_module(self, module_name, **kwargs):
        """Load module by type name, with named arguments
        """
        self._load_module(module_name, **kwargs)

    def _load_module(self, module_name, loaded_by='modman', **kwargs):
        """Load a module that has been previously discovered, with owner information"""
        if module_name not in self.found_modules:
            raise ModuleLoadError('invalid module name: "{}"'.format(module_name))

        if 'instance_name' not in kwargs:
            instance_name = module_name
        else:
            instance_name = kwargs['instance_name']

        if 'instance_suffix' in kwargs:
            instance_name += '-{}'.format(kwargs['instance_suffix'])

        #insert self object in kwargs for now, for manipulation
        kwargs.update({'plugmgr' : self,
                       'loaded_by' : loaded_by})

        #check if module type allows multiple instances
        if self._is_module_type_present(module_name):
            if ModuleCapabilities.MultiInstanceAllowed not in self.found_modules[module_name].get_capabilities():
                raise ModuleAlreadyLoadedError('module is already loaded')

        if instance_name in self.loaded_modules:
            #handle multiple instances, append proper suffix to the type name automatically
            if self.found_modules[module_name].get_multi_inst_suffix() == None:
                multi_inst_name = instance_name + '-{}'.format(handle_multiple_instance(instance_name,
                                                                                        self.loaded_modules.keys()))
            else:
                multi_inst_name = instance_name + '-{}'.format(self.found_modules[module_name].get_multi_inst_suffix())

            self.loaded_modules[multi_inst_name] = self.found_modules[module_name](module_id=multi_inst_name,
                                                                                   handler=self.module_handler,
                                                                                   **kwargs)
            self.logger.info('Loaded module "{}" as "{}", loaded by "{}"'.format(module_name, multi_inst_name, loaded_by))
            self._trigger_manager_hook('modman.module_loaded', instance_name=multi_inst_name)
            return multi_inst_name

        #load (create object)
        self.loaded_modules[instance_name] = self.found_modules[module_name](module_id=instance_name,
                                                                           handler=self.module_handler,
                                                                           **kwargs)

        self.logger.info('Loaded module "{}" as "{}", loaded by "{}"'.format(module_name, instance_name, loaded_by))
        #trigger hooks
        self._trigger_manager_hook('modman.module_loaded', instance_name=instance_name)
        return instance_name

    def get_loaded_module_list(self):
        """Returns a list of the loaded instance names
        """
        return self.loaded_modules.keys()

    def get_instance_type(self, instance_name):
        """Returns module type or descriptive error
        """
        if instance_name in self.loaded_modules:
            return self.loaded_modules[instance_name].get_module_type()

        self.logger.warn('requested instance "{}" not found'.format(instance_name))
        return {'status': 'error',
                'error': 'invalid_instance'}

    def get_module_structure(self, module_name):
        """Retrieves the module's structure in a JSON-serializable dictionary or descriptive error
        """
        if module_name in self.found_modules:
            return self.found_modules[module_name].dump_module_structure()

        self.logger.warn('requested module "{}" not found'.format(module_name))
        return {'status': 'error',
                'error': 'invalid_module'}

    def get_module_info(self, module_name):
        """Returns basic module info, serializable or descriptive error
        """
        if module_name in self.found_modules:
            return self.found_modules[module_name].get_module_info()

        self.logger.warn('requested module "{}" not found'.format(module_name))
        return {'status': 'error',
                'error': 'invalid_module'}

    def get_module_property(self, module_name, property_name):
        """Returns the value of a module property or descriptive error
        """
        try:
            return self.loaded_modules[module_name].get_property_value(property_name)
        except ModulePropertyPermissionError:
            self.logger.warn('tried to read write-only property "{}" of instance "{}"'.format(property_name, module_name))
            return {'status': 'error',
                    'error': 'write_only'}
        except ModuleInvalidPropertyError:
            self.logger.error('property does not exist: "{}"'.format(property_name))
            return {'status': 'error',
                    'error': 'invalid_property'}
        except KeyError:
            self.logger.error('get_module_property: instance "{}" not loaded'.format(module_name))
            return {'status': 'error',
                    'error': 'invalid_instance'}

    def set_module_property(self, instance_name, property_name, value):
        """Sets the value of a module property. NO type checking is done
           Returns status of the attempt
        """
        try:
            self.loaded_modules[instance_name].set_property_value(property_name, value)
            return {'status': 'ok'}
        except ModulePropertyPermissionError:
            self.logger.error('tried to write read-only property "{}" of instance "{}"'.format(property_name, instance_name))
            return {'status': 'error',
                    'error': 'read_only'}
        except ModuleInvalidPropertyError:
            self.logger.error('property does not exist: "{}"'.format(property_name))
            return {'status': 'error',
                    'error': 'invalid_property'}
        except KeyError:
            self.logger.error('get_module_property: instance "{}" not loaded'.format(instance_name))
            return {'status': 'error',
                    'error': 'invalid_instance'}

    def get_module_property_list(self, module_name):
        """Returns a serializable dictionary of the module's properties
        """
        if module_name in self.found_modules:
            return self.found_modules[module_name].get_module_properties()

        self.logger.warn('requested module "{}" not found'.format(module_name))
        return {'status': 'error',
                'error': 'invalid_module'}

    def get_module_method_list(self, module_name):
        """Returns a serializable dictionary of the module's methods
        """
        if module_name in self.found_modules:
            return self.found_modules[module_name].get_module_methods()

        self.logger.warn('requested module "{}" not found'.format(module_name))
        return {'status': 'error',
                'error': 'invalid_module'}

    def call_module_method(self, __instance_name, __method_name, **kwargs):
        """Attempts to call a module method.
           In case of failure returns a descriptive error
        """
        if __instance_name in self.loaded_modules:
            try:
                #TODO: for consistency return not the actual value but a dictionary?
                return self.loaded_modules[__instance_name].call_method(__method_name, **kwargs)
            except ModuleMethodError as e:
                self.logger.warn('call to method "{}" of instance "{}" failed with: "{}"'.format(__method_name,
                                                                                                 __instance_name,
                                                                                                 e.message))
                return {'status': 'error',
                        'error': 'call_failed'}

        self.logger.warn('requested instance "{}" not found'.format(__instance_name))
        return {'status': 'error',
                'error': 'invalid_instance'}

    def list_loaded_modules(self):
        """Returns a dictionary that contains the names of instances currently loaded as keys
           and which module owns them as values. Note that if there is no specific owner,
           they are owned by the module manager, shown as 'modman'
        """

        attached_modules = {}
        for module_name, module in self.loaded_modules.iteritems():
            attached_modules[module_name] = module.get_loaded_kwargs('loaded_by')

        return attached_modules

    def unload_module(self, module_name):
        """Unload module wrapper function
        """
        self._unload_module(module_name)

    def _unload_module(self, module_name, requester='modman'):
        """Unload a module and automatically cleanup after it
        """
        if module_name not in self.loaded_modules:
            raise ModuleNotLoadedError('cant unload {}: module not loaded'.format(module_name))

        if requester != self.loaded_modules[module_name].get_loaded_kwargs('loaded_by'):
            if requester != 'modman':
                raise CannotUnloadError('cannot unloaded: forbidden by module manager')

        #do unloading procedure
        self.loaded_modules[module_name].module_unload()

        #remove custom hooks
        remove_hooks = []
        for hook_name, hook in self.custom_hooks.iteritems():
            if hook.owner == module_name:
                remove_hooks.append(hook_name)

        for hook in remove_hooks:
            #notify attached
            for attached in self.custom_hooks[hook].attached_callbacks:
                if attached.argument in self.loaded_modules:
                    self.loaded_modules[attached.argument].handler_communicate(reason='provider_unloaded')

            del self.custom_hooks[hook]
            self.logger.debug('removing custom hook: "{}"'.format(hook))

        #remove custom methods
        remove_methods = []
        for method_name, method in self.custom_methods.iteritems():
            if method.owner == module_name:
                remove_methods.append(method_name)

        for method in remove_methods:
            del self.custom_methods[method]
            self.logger.debug('removing custom method: "{}"'.format(method))

        #remove interrupt handlers
        remove_interrupts = []
        for interrupt_name, interrupt in self.external_interrupts.iteritems():
            if interrupt.owner == module_name:
                remove_interrupts.append(interrupt_name)

        for interrupt in remove_interrupts:
            del self.external_interrupts[interrupt]
            self.logger.debug('removing interrupt handler: "{}"'.format(interrupt))

        #detach hooks
        for hook_name, hook in self.custom_hooks.iteritems():
            for attached in hook.find_callback_by_argument(module_name):
                hook.detach_callback(attached)

        for hook_name, hook in self.attached_hooks.iteritems():
            for attached in hook.find_callback_by_argument(module_name):
                hook.detach_callback(attached)

        #remove
        del self.loaded_modules[module_name]

        self.logger.info('module "{}" unloaded by "{}"'.format(module_name, requester))

    def list_discovered_modules(self):
        """Returns a list of all module types that have been discovered
        """
        return dict([(name, mod.get_module_desc()) for name, mod in self.found_modules.iteritems()])

    def module_handler(self, which_module, *args, **kwargs):
        """Function called by a live module to carry out various operations within the module manager scope
           Returns various different values depending on the requested method
        """
        if 'get_available_drivers' in args:
            return [x.get_module_desc().arg_name for x in self.found_modules.values()]

        for kwg, value in kwargs.iteritems():
            if kwg in MODULE_HANDLER_LOGGING_KWARGS:
                #dispatch logger
                self._log_module_message(which_module, kwg, value)
                return None

            if kwg == 'call_custom_method':
                try:
                    return self.call_custom_method(value[0], *value[1])
                except MethodNotAvailableError as ex:
                    self.logger.debug('module "{}" tried to call invalid method: "{}"'.format(which_module, value[0]))
                    self.loaded_modules[which_module].handler_communicate(reason='call_method_failed', exception=ex)
                    return None

            if kwg == 'attach_custom_hook':
                try:
                    self.attach_custom_hook(value[0], *value[1])
                except HookNotAvailableError as ex:
                    self.logger.debug('module "{}" tried to attach to invalid hook: "{}"'.format(which_module, value[0]))
                    self.loaded_modules[which_module].handler_communicate(reason='attach_hook_failed', exception=ex)

            if kwg == 'attach_manager_hook':
                try:
                    self.attach_manager_hook(value[0], *value[1])
                except HookNotAvailableError as ex:
                    self.logger.debug('module "{}" tried to attach to invalid hook: "{}"'.format(which_module, value[0]))
                    self.loaded_modules[which_module].handler_communicate(reason='attach_hook_failed', exception=ex)

            if kwg == 'load_module':
                try:
                    return self._load_module(value[0], which_module, **value[1])
                except (ModuleLoadError, ModuleAlreadyLoadedError) as ex:
                    self.loaded_modules[which_module].handler_communicate(reason='load_module_failed', exception=ex)

            if kwg == 'unload_module':
                try:
                    self._unload_module(value[0], which_module)
                except (ModuleNotLoadedError, CannotUnloadError) as ex:
                    self.loaded_modules[which_module].handler_communicate(reason='unload_module_failed', exception=ex)

            if kwg == 'install_custom_hook':
                try:
                    self._install_custom_hook(value[0], which_module)
                except HookAlreadyInstalledError as ex:
                    self.loaded_modules[which_module].handler_communicate(reason='install_hook_failed', exception=ex)

            if kwg == 'install_custom_method':
                try:
                    self._install_custom_method(value[0], value[1], which_module)
                except MethodAlreadyInstalledError:
                    self.loaded_modules[which_module].handler_communicate(reason='install_method_failed', exception=ex)

            if kwg == 'install_interrupt_handler':
                try:
                    self._install_interrupt_handler(value[0], value[1], which_module)
                except InterruptAlreadyInstalledError:
                    self.loaded_modules[which_module].handler_communicate(reason='install_interrupt_failed', exception=ex)

            if kwg == 'require_module_instance':
                if value not in self.loaded_modules:
                    raise ModuleLoadError('instance {} is not present')

    def _log_module_message(self, module, level, message):
        """Helper function to execute module-level logging
        """
        self.log_message(level, "{}: {}".format(module, message))

    def log_message(self, level, message):
        """Helper function for general logging
        """
        if level == 'log_info':
            self.logger.info(message)
        elif level == 'log_warning':
            self.logger.warning(message)
        elif level == 'log_error':
            self.logger.error(message)

    def _trigger_hooks(self, hook_dict, hook_name, **kwargs):
        """Trigger a registered hook with the passed arguments.
           This will call all the callbacks that are attached to that hook.
        """
        for attached_callback in hook_dict[hook_name].attached_callbacks:
            if attached_callback.callback(**kwargs):
                if attached_callback.action == ModuleManagerHookActions.LOAD_MODULE:
                    #load the module!
                    self.logger.debug('some hook returned true, loading module {}'.format(attached_callback.argument))
                    #module must accept same kwargs, this is mandatory with this discovery event
                    try:
                        self.load_module(attached_callback.argument.get_module_desc().arg_name,
                                         **kwargs)
                    except Exception as ex:
                        self.logger.error('loading of module of class "{}" failed with: {}'.format(attached_callback.argument.__name__, ex.message))
                elif attached_callback.action == ModuleManagerHookActions.UNLOAD_MODULE:
                    #unload the attached module
                    self.logger.debug('a hook required module {} to be unloaded'.format(attached_callback.argument))
                    self.unload_module(attached_callback.argument)

    def trigger_custom_hook(self, hook_name, **kwargs):
        """Hook trigger wrapper function for custom hooks
        """
        self._trigger_hooks(self.custom_hooks, hook_name, **kwargs)

    def _trigger_manager_hook(self, hook_name, **kwargs):
        """Hook trigger wrapper function for internal module manager hooks
        """
        self._trigger_hooks(self.attached_hooks, hook_name, **kwargs)

    def external_interrupt(self, interrupt_key, **kwargs):
        """External interrupt trigger
        """
        if interrupt_key in self.external_interrupts:
            self.external_interrupts[interrupt_key].call(**kwargs)
