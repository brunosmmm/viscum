"""Viscum: a Plugin manager."""

import imp
import logging
from collections import namedtuple
from viscum.plugin import ModuleCapabilities
from viscum.plugin.exception import (ModuleLoadError,
                                     ModuleAlreadyLoadedError,
                                     ModuleNotLoadedError,
                                     ModuleMethodError,
                                     ModulePropertyPermissionError,
                                     ModuleInvalidPropertyError)
from viscum.exception import (InterruptAlreadyInstalledError,
                              MethodNotAvailableError,
                              HookNotAvailableError,
                              CannotUnloadError,
                              HookAlreadyInstalledError,
                              MethodAlreadyInstalledError,
                              DeferModuleDiscovery)
from viscum.hook import (ModuleManagerHook,
                         ModuleManagerHookActions as MMHookAct)
from viscum.scripting import (ModuleManagerScript,
                              DeferScriptLoading,
                              CancelScriptLoading)
import re
import glob
import os

MODULE_HANDLER_LOGGING_KWARGS = ['log_info', 'log_warning', 'log_error']


# helper functions
def handle_multiple_instance(module_name, loaded_module_list):
    """Handle multiple instance plugin loading.

    Args
    ----
    module_name: str
       Module type
    loaded_module_list: list
       list of currently loaded modules

    returns suffix based on instance count
    """
    instance_list = []
    for module in loaded_module_list:
        m = re.match(r"{}-([0-9]+)".format(module_name), module)
        if m is not None:
            instance_list.append(int(m.group(1)))

    if len(instance_list) == 0:
        return 1

    return sorted(instance_list)[-1] + 1


ModuleManagerMethod = namedtuple('ModuleManagerMethod', ['call', 'owner'])
HookAttacher = namedtuple('HookAttacher', ['callback', 'action', 'argument'])


class ModuleManager(object):
    """Module manager class."""

    def __init__(self, central_log, plugin_path, script_path):
        """Initialize.

        Args
        ----
        central_log: str
            Logger name
        plugin_path: str
            Location where plugins are stored
        script_path:
            Location where scripts are stored
        """
        self.found_modules = {}
        self.loaded_modules = {}
        self.logger = logging.getLogger('{}.drvman'.format(central_log))

        # hooks
        self.attached_hooks = {'modman.module_loaded':
                               ModuleManagerHook('modman'),
                               'modman.module_unloaded':
                               ModuleManagerHook('modman'),
                               'modman.tick':
                               ModuleManagerHook('modman')}

        self.custom_hooks = {}
        self.custom_methods = {}
        self.external_interrupts = {}

        self.scripts = {}

        self.plugin_path = plugin_path
        self.script_path = script_path
        self.tick_counter = 0

        # states
        self.discovery_active = False

        # module discovery deferral
        self.deferred_discoveries = {}
        self.deferred_scripts = {}

    def module_system_tick(self):
        """Timer function called by main loop."""
        self.tick_counter += 1
        self._trigger_manager_hook('modman.tick', uptime=self.tick_counter)

    def install_custom_hook(self, hook_name):
        """Install a custom hook into the manager system.

        Args
        ----
        hook_name: str
            Hook name
        """
        self._install_custom_hook(hook_name)

    def _install_custom_hook(self, hook_name, installed_by='modman'):
        """Inner function to actually install the custom hook.

        Args
        ----
        hook_name: str
           Hook name
        installed_by: str
           Module instance name, owner of callback
        """
        if hook_name in self.custom_hooks:
            raise HookAlreadyInstalledError('hook is already installed')

        self.logger.debug('custom hook {} installed'.format(hook_name))
        self.custom_hooks[hook_name] = ModuleManagerHook(installed_by)

    def install_custom_method(self, method_name, callback):
        """Install a custom method, made available to all loaded modules.

        Args
        ----
        method_name: str
           Method Name
        callback: function
           Callback function
        """
        self._install_custom_method(method_name, callback)

    def _install_custom_method(self, method_name,
                               callback, installer='modman'):
        """Inner function to install the custom method.

        Args
        ----
        method_name: str
            Method name
        callback: function
            Callback function
        intaller: str
            Module instance name, owner of callback
        """
        if method_name in self.custom_methods:
            raise MethodAlreadyInstalledError('method is already installed')

        self.logger.debug('custom method "{}" installed, calls {}'
                          .format(method_name, callback))
        self.custom_methods[method_name] = ModuleManagerMethod(call=callback,
                                                               owner=installer)

    def call_custom_method(self, method_name, *args, **kwargs):
        """Call a custom method, if available.

        Args
        ----
        method_name: str
            Method name
        args: list
            Positional arguments to be passed to method
        kwargs: dict
            Keyword arguments to be passed to method
        """
        if method_name in self.custom_methods:
            return self.custom_methods[method_name].call(*args, **kwargs)

        raise MethodNotAvailableError('requested method is not available')

    def attach_custom_hook(self, attach_to, callback, action, argument):
        """Attach a callback to a custom hook, if available.

        Args
        ----
        attach_to: str
            Hook name
        callback: function
            Callback function called on hook triggered
        action: MMHookAct
            Action to be performed on trigger event
        argument: list, dict
            Arguments passed to callback
        """
        if attach_to in self.custom_hooks:
            self.custom_hooks[attach_to].attach_callback(
                HookAttacher(callback=callback,
                             action=action,
                             argument=argument))
            self.logger.debug('callback {} installed into '
                              'custom hook {} with action {}'
                              .format(callback,
                                      attach_to,
                                      action))
            return

        raise HookNotAvailableError('the requested hook is not available')

    def attach_manager_hook(self, attach_to, callback, action, driver_class):
        """Attach a callback to a manager default hook.

        Args
        ----
        attach_to: str
           Hook name
        callback: function
           Callback function called on hook triggered
        action: MMHookAct
           Action to be performed on trigger event
        driver_class: class
           Plugin class as argument
        """
        if attach_to in self.attached_hooks:
            self.attached_hooks[attach_to].attach_callback(
                HookAttacher(callback=callback,
                             action=action,
                             argument=driver_class))
            self.logger.debug('callback {} installed into hook '
                              '{} with action {}'
                              .format(callback,
                                      attach_to,
                                      action))
            return

        raise HookNotAvailableError('the requested hook is not available')

    def install_interrupt_handler(self, interrupt_key, callback):
        """Install a custom interrupt handler.

        Args
        ----
        interrupt_key: str
            Interrupt name
        callback: function
            Interrupt callback
        """
        self._install_interrupt_handler(interrupt_key, callback)

    def _install_interrupt_handler(self, interrupt_key,
                                   callback, installer='modman'):
        """Inner function to install a interrupt handler.

        Args
        ----
        interrupt_key: str
            Interrupt name
        callback: function
            Interrupt callback
        installer: str
            Module or instance name that installed this interrupt
        """
        if interrupt_key in self.external_interrupts:
            raise InterruptAlreadyInstalledError('interrupt already installed')

        self.logger.debug('custom interrupt "{}" was installed, calls "{}"'
                          .format(interrupt_key,
                                  callback))
        self.external_interrupts[interrupt_key] =\
            ModuleManagerMethod(call=callback,
                                owner=installer)

    def require_discovered_module(self, module_type):
        """Require a certain module to be present at discovery time.

        if the module is not present (not discovered), then raises an
        exception that ultimately defers the discovery until such
        module is discovered
        Args
        ----
        module_type: str
            Type of the required module
        """
        if self.discovery_active:
            if module_type not in self.found_modules:
                raise DeferModuleDiscovery(module_type)

    def insert_module(self, module_class):
        """Manually insert a module class as a discovered plugin.

        Args
        ----
        module_class: class
            Class of the module
        """
        self.found_modules[module_class.get_module_desc().arg_name] =\
            module_class
        self.logger.info('Manually '
                         'inserting module "{}"'
                         .format(module_class.get_module_desc().arg_name))

    def _module_discovery(self, module):
        """Discover all modules.

        Tries to load a module file
        Args
        ----
        module: str
           Module name (Actual python module)
        """
        # ignore root
        if module == '__init__':
            return

        # success flag
        discovery_succeeded = False

        try:
            the_mod = imp.load_source(module,
                                      os.path.join(self.plugin_path,
                                                   module,
                                                   '__init__.py'))
            self.logger.info('inspecting module file: "{}"'.format(module))
            # guard discovery procedure
            self.discovery_active = True
            plugin_path = os.path.join(self.plugin_path,
                                       module)
            module_class = the_mod.discover_module(modman=self,
                                                   plugin_path=plugin_path)
            module_type = module_class.get_module_desc().arg_name
            self.found_modules[module_type] = module_class
            self.logger.info('Discovery of module "{}" succeeded'
                             .format(module_class.get_module_desc().arg_name))
            discovery_succeeded = True
        except ImportError as error:
            self.logger.warning('could not register python module "{}": {}'
                                .format(module,
                                        error))
        except DeferModuleDiscovery as ex:
            self.logger.info('deferring discovery of module')
            # hacky
            self.deferred_discoveries[module] = ex.args[0]
        except Exception as error:
            # raise  # debug
            # catch anything else because this cannot break the application
            self.logger.warning('could not register module {}: {}'
                                .format(module, error))

        # check for deferrals that depend on the previous loaded module
        deferred_done = []
        for deferred, dependency in self.deferred_discoveries.items():
            if dependency == module and discovery_succeeded:
                # discover (recursive!)
                self.logger.debug('dependency for deferred '
                                  '"{}" met; discovering now'
                                  .format(deferred))
                self._module_discovery(deferred)
                deferred_done.append(deferred)

        # remove done deferrals
        for deferred in deferred_done:
            del self.deferred_discoveries[deferred]

        self.discovery_active = False

    def discover_modules(self):
        """Discovery routine wrapper.

        Iterates through all found files in the plugins subfolder
        """
        module_root = imp.load_source('plugins', os.path.join(self.plugin_path,
                                                              '__init__.py'))
        module_list = module_root.MODULES

        for module in module_list:
            self._module_discovery(module)

        if len(self.deferred_discoveries) > 0:
            self.logger.warning('some modules could not be discovered because'
                                ' they had dependencies that were not met: {}'
                                .format(
                                    list(self.deferred_discoveries.keys())))

    def _discover_script(self, script):
        """Discovery process of a single script.

        Args
        ----
        script: str
            script file path
        """
        try:
            self.scripts[script] = ModuleManagerScript(script,
                                                       self,
                                                       initialize=True)
        except DeferScriptLoading as ex:
            self.logger.debug('deferring load of script {}, '
                              'which requires module {} to be active'
                              .format(script, str(ex)))
            # put on deferred list
            if ex.message['type'] not in self.deferred_scripts:
                self.deferred_scripts[ex.message['type']] =\
                    {script: {'req_inst': ex.message['inst']}}
            else:
                self.deferred_scripts[ex.message['type']].update(
                    {script: {'req_inst': ex.message['inst']}})
        except CancelScriptLoading as ex:
            self.logger.info('loading of script {} was canceled'
                             ' by the script with: {}'
                             .format(script, ex))
        except Exception as ex:
            self.logger.warning('failed to load script {} with: {}'
                                .format(script, ex))

    def discover_scripts(self):
        """Discover available scripts."""
        script_files = glob.glob(os.path.join(self.script_path, '*.py'))

        for script in script_files:
            self._discover_script(script)

    def _is_module_type_present(self, module_class_name):
        """Return whether any module of a certain type has been loaded.

        Args
        ----
        module_class_name: string
            Module type
        """
        for mod_name, mod_obj in self.loaded_modules.items():
            if mod_obj.get_module_type() == module_class_name:
                return True

        return False

    def load_module(self, module_name, **kwargs):
        """Load module by type name, with named arguments.

        Args
        ----
        module_name: str
            Plugin name
        kwargs: dict
            Arguments passed to plugin
        """
        self.logger.info('Trying to load module '
                         'of type "{}"'.format(module_name))
        return self._load_module(module_name, **kwargs)

    def _load_module(self, module_name, loaded_by='modman', **kwargs):
        """Load a module that has been previously discovered.

        Args
        ----
        module_name: str
            Plugin type
        loaded_by: str
            Instance that requested this to be loaded
        kwargs: dict
            Arguments passed to plugin
        """
        if module_name not in self.found_modules:
            raise ModuleLoadError('invalid module name: "{}"'
                                  .format(module_name))

        if 'instance_name' not in kwargs:
            instance_name = module_name
        else:
            instance_name = kwargs['instance_name']

        if 'instance_suffix' in kwargs:
            instance_name += '-{}'.format(kwargs['instance_suffix'])

        # insert self object in kwargs for now, for manipulation
        kwargs.update({'plugmgr': self,
                       'loaded_by': loaded_by})

        # check if module type allows multiple instances
        if self._is_module_type_present(module_name):
            if ModuleCapabilities.MultiInstanceAllowed not in\
               self.found_modules[module_name].get_capabilities():
                raise ModuleAlreadyLoadedError('module is already loaded')

        if instance_name in self.loaded_modules:
            # handle multiple instances, append proper
            # suffix to the type name automatically
            if self.found_modules[module_name].get_multi_inst_suffix() is None:
                loaded_module_list = self.loaded_modules.keys()
                multi_inst_name = '{}-{}'.format(instance_name,
                                                 handle_multiple_instance(
                                                     instance_name,
                                                     loaded_module_list))
            else:
                # get multi instance suffix
                mi_s = self.found_modules[module_name].get_multi_inst_suffix()
                multi_inst_name = '{}-{}'.format(instance_name,
                                                 mi_s)

            # instantiate plugin
            module_class = self.found_modules[module_name]
            module_inst = module_class(module_id=multi_inst_name,
                                       handler=self.module_handler,
                                       **kwargs)
            self.loaded_modules[multi_inst_name] = module_inst
            self.logger.info('Loaded module "{}" as "{}", loaded by "{}"'
                             .format(module_name, multi_inst_name, loaded_by))
            self._trigger_manager_hook('modman.module_loaded',
                                       instance_name=multi_inst_name)
            return multi_inst_name

        # load (create object)
        mod_inst = self.found_modules[module_name](module_id=instance_name,
                                                   handler=self.module_handler,
                                                   **kwargs)
        self.loaded_modules[instance_name] = mod_inst

        self.logger.info('Loaded module "{}" as "{}", loaded by "{}"'
                         .format(module_name, instance_name, loaded_by))
        # trigger hooks
        self._trigger_manager_hook('modman.module_loaded',
                                   instance_name=instance_name)

        # look for scripts that have been deferred from loading
        for mod_name, script_list in self.deferred_scripts.items():
            for script_path, attrs in script_list.items():
                if mod_name == module_name:
                    # check if specific instance is needed
                    if attrs['req_inst'] != '':
                        if instance_name == '{}-{}'.format(mod_name,
                                                           attrs['req_inst']):
                            # requirements met, load script
                            self._discover_script(script_path)
                        elif instance_name == attrs['req_inst']:
                            # not multi instance
                            self._discover_script(script_path)

        return instance_name

    def get_loaded_module_list(self):
        """Return a list of the loaded instance names."""
        return list(self.loaded_modules.keys())

    def get_instance_list_by_type(self, module_type):
        """Return a list of module instances (loaded) of requested type.

        Args
        ----
        module_type: str
            Plugin type
        """
        instances = []
        for inst_name, mod in self.loaded_modules.items():
            if mod.get_module_type() == module_type:
                instances.append(inst_name)

        return instances

    def get_instance_type(self, instance_name):
        """Return module type or descriptive error.

        Args
        ----
        instance_name: str
            Plugin instance name
        """
        if instance_name in self.loaded_modules:
            return self.loaded_modules[instance_name].get_module_type()

        self.logger.warn('requested instance "{}" not found'
                         .format(instance_name))
        return {'status': 'error',
                'error': 'invalid_instance'}

    def get_module_capabilities(self, module_name):
        """Return module capabilities.

        Args
        ----
        module_name: str
           Plugin type
        """
        if module_name in self.found_modules:
            return self.found_modules[module_name].get_capabilities()

    def get_module_structure(self, module_name):
        """Retrieve the module's structure in a JSON-serializable dictionary.

        Or descriptive error
        Args
        ----
        module_name: str
            Plugin type
        """
        if module_name in self.found_modules:
            return self.found_modules[module_name].dump_module_structure()

        self.logger.warn('requested module "{}" not found'.format(module_name))
        return {'status': 'error',
                'error': 'invalid_module'}

    def get_module_info(self, module_name):
        """Return basic module info, serializable or descriptive error.

        Args
        ____
        module_name: str
            Plugin type
        """
        if module_name in self.found_modules:
            return self.found_modules[module_name].get_module_info()

        self.logger.warn('requested module "{}" not found'.format(module_name))
        return {'status': 'error',
                'error': 'invalid_module'}

    def get_module_property(self, module_name, property_name):
        """Return the value of a module property or descriptive error.

        Args
        ----
        module_name: str
           Instance name
        property_name:
           Name of the property requested
        """
        try:
            the_module = self.loaded_modules[module_name]
            return the_module.get_property_value(property_name)
        except ModulePropertyPermissionError:
            self.logger.warn('tried to read write-only property '
                             '"{}" of instance "{}"'
                             .format(property_name, module_name))
            return {'status': 'error',
                    'error': 'write_only'}
        except ModuleInvalidPropertyError:
            self.logger.error('property does not exist: "{}"'
                              .format(property_name))
            return {'status': 'error',
                    'error': 'invalid_property'}
        except KeyError:
            if module_name not in self.loaded_modules:
                self.logger.error('get_module_property: '
                                  'instance "{}" not loaded'
                                  .format(module_name))
            else:
                self.logger.error('get_module_property: unknown error')
            return {'status': 'error',
                    'error': 'invalid_instance'}

    def set_module_property(self, instance_name, property_name, value):
        """Set the value of a module property.

        NO type checking is done
        Returns status of the attempt
        Args
        ----
        instance_name: str
            Instance name
        property_name: str
            Name of requested property
        value: object
            Some value to be written
        """
        try:
            the_instance = self.loaded_modules[instance_name]
            the_instance.set_property_value(property_name,
                                            value)
            return {'status': 'ok'}
        except ModulePropertyPermissionError:
            self.logger.error('tried to write read-only property '
                              '"{}" of instance "{}"'
                              .format(property_name, instance_name))
            return {'status': 'error',
                    'error': 'read_only'}
        except ModuleInvalidPropertyError:
            self.logger.error('property does not exist: "{}"'
                              .format(property_name))
            return {'status': 'error',
                    'error': 'invalid_property'}
        except KeyError:
            self.logger.error('get_module_property: instance "{}" not loaded'
                              .format(instance_name))
            return {'status': 'error',
                    'error': 'invalid_instance'}

    def get_module_property_list(self, module_name):
        """Return a serializable dictionary of the module's properties.

        Args
        ----
        module_name:
           Plugin type
        """
        if module_name in self.found_modules:
            return self.found_modules[module_name].get_module_properties()

        self.logger.warn('requested module "{}" not found'.format(module_name))
        return {'status': 'error',
                'error': 'invalid_module'}

    def get_module_method_list(self, module_name):
        """Return a serializable dictionary of the module's methods.

        Args
        ----
        module_name:
           Plugin type
        """
        if module_name in self.found_modules:
            return self.found_modules[module_name].get_module_methods()

        self.logger.warn('requested module "{}" not found'.format(module_name))
        return {'status': 'error',
                'error': 'invalid_module'}

    def call_module_method(self, __instance_name, __method_name, **kwargs):
        """Attempt calling a module method.

        In case of failure returns a descriptive error
        Args
        ----
        __instance_name: str
            Name of instance
        __method_name: str
            Name of method
        kwargs: dict
            Keyword arguments passed to method
        """
        if __instance_name in self.loaded_modules:
            try:
                # TODO: for consistency return not
                # the actual value but a dictionary?
                the_instance = self.loaded_modules[__instance_name]
                return the_instance.call_method(__method_name,
                                                **kwargs)
            except ModuleMethodError as e:
                self.logger.warn('call to method "{}" of instance '
                                 '"{}" failed with: "{}"'
                                 .format(__method_name,
                                         __instance_name,
                                         str(e)))
                return {'status': 'error',
                        'error': 'call_failed'}

        self.logger.warn('requested instance "{}" not found'
                         .format(__instance_name))
        return {'status': 'error',
                'error': 'invalid_instance'}

    def list_loaded_modules(self):
        """Return a dictionary that contains instances currently loaded.

        Instances currently loaded as keys
        and which module owns them as values.
        Note that if there is no specific owner,
        they are owned by the module manager, shown as 'modman'
        """
        attached_modules = {}
        for module_name, module in self.loaded_modules.items():
            attached_modules[module_name] =\
                module.get_loaded_kwargs('loaded_by')

        return attached_modules

    def unload_module(self, module_name):
        """Unload module wrapper function.

        Args
        ----
        module_name: str
            Instance name
        """
        self._unload_module(module_name)

    def _unload_module(self, module_name, requester='modman'):
        """Unload a module and automatically cleanup after it.

        Args
        ----
        module_name: str
            Instance name
        requester: str
            Name of instance which requested the unloading procedure
        """
        if module_name not in self.loaded_modules:
            raise ModuleNotLoadedError('cant unload {}: module not loaded'
                                       .format(module_name))

        the_module = self.loaded_modules[module_name]
        if requester != the_module.get_loaded_kwargs('loaded_by'):
            if requester != 'modman':
                raise CannotUnloadError('cannot unloaded: forbidden'
                                        ' by module manager')

        # do unloading procedure
        the_module.module_unload()

        # remove custom hooks
        remove_hooks = []
        for hook_name, hook in self.custom_hooks.items():
            if hook.owner == module_name:
                remove_hooks.append(hook_name)

        for hook in remove_hooks:
            # notify attached
            for attached in self.custom_hooks[hook].attached_callbacks:
                if attached.argument in self.loaded_modules:
                    att_arg = self.loaded_modules[attached.argument]
                    att_arg.handler_communicate(reason='provider_unloaded')

            del self.custom_hooks[hook]
            self.logger.debug('removing custom hook: "{}"'.format(hook))

        # remove custom methods
        remove_methods = []
        for method_name, method in self.custom_methods.items():
            if method.owner == module_name:
                remove_methods.append(method_name)

        for method in remove_methods:
            del self.custom_methods[method]
            self.logger.debug('removing custom method: "{}"'.format(method))

        # remove interrupt handlers
        remove_interrupts = []
        for interrupt_name, interrupt in self.external_interrupts.items():
            if interrupt.owner == module_name:
                remove_interrupts.append(interrupt_name)

        for interrupt in remove_interrupts:
            del self.external_interrupts[interrupt]
            self.logger.debug('removing interrupt handler: "{}"'
                              .format(interrupt))

        # detach hooks
        for hook_name, hook in self.custom_hooks.items():
            for attached in hook.find_callback_by_argument(module_name):
                hook.detach_callback(attached)

        for hook_name, hook in self.attached_hooks.items():
            for attached in hook.find_callback_by_argument(module_name):
                hook.detach_callback(attached)

        # remove
        del self.loaded_modules[module_name]

        self.logger.info('module "{}" unloaded by "{}"'
                         .format(module_name, requester))

    def list_discovered_modules(self):
        """Return a list of all module types that have been discovered."""
        return dict([(name, mod.get_module_desc())
                     for name, mod in self.found_modules.items()])

    def module_handler(self, which_module, *args, **kwargs):
        """Carry out various operations.

        Operations within the module manager scope, called by a live module
        Returns various different values depending on the requested method
        Args
        ----
        which_module: Module
            The plugin object calling this function
        args: list
            Argument list
        kwargs: dict
            Keyword arguments
        """
        if 'get_available_drivers' in args:
            return [x.get_module_desc().arg_name
                    for x in list(self.found_modules.values())]

        for kwg, value in kwargs.items():
            if kwg in MODULE_HANDLER_LOGGING_KWARGS:
                # dispatch logger
                self._log_module_message(which_module, kwg, value)
                return None

            if kwg == 'call_custom_method':

                # parse value:
                if isinstance(value, (list, tuple)):
                    first_argument = value[0]
                    second_argument = value[1]
                elif isinstance(value, dict):
                    first_argument = value['method']
                    second_argument = value['args']
                try:
                    return self.call_custom_method(first_argument,
                                                   *second_argument)
                except MethodNotAvailableError as ex:
                    self.logger.error('module "{}" tried to call '
                                      'invalid method: "{}"'
                                      .format(which_module, first_argument))
                    the_module = self.loaded_modules[which_module]
                    the_module.handler_communicate(
                        reason='call_method_failed',
                        exception=ex)
                    return None

            if kwg == 'attach_custom_hook':
                if isinstance(value, (list, tuple)):
                    first_argument = value[0]
                    second_argument = value[1]
                elif isinstance(value, dict):
                    first_argument = value['hook']
                    second_argument = value['args']
                try:
                    self.attach_custom_hook(first_argument,
                                            *second_argument)
                except HookNotAvailableError as ex:
                    self.logger.error('module "{}" tried to attach '
                                      'to invalid hook: "{}"'
                                      .format(which_module, first_argument))
                    the_module = self.loaded_modules[which_module]
                    the_module.handler_communicate(
                        reason='attach_hook_failed',
                        exception=ex)

            if kwg == 'attach_manager_hook':
                if isinstance(value, (list, tuple)):
                    first_argument = value[0]
                    second_argument = value[1]
                elif isinstance(value, dict):
                    first_argument = value['hook']
                    second_argument = value['args']
                try:
                    self.attach_manager_hook(first_argument,
                                             *second_argument)
                except HookNotAvailableError as ex:
                    self.logger.error('module "{}" tried to attach '
                                      'to invalid hook: "{}"'
                                      .format(which_module, first_argument))
                    the_module = self.loaded_modules[which_module]
                    the_module.handler_communicate(
                        reason='attach_hook_failed',
                        exception=ex)

            if kwg == 'load_module':
                if isinstance(value, (list, tuple)):
                    first_argument = value[0]
                    second_argument = value[1]
                elif isinstance(value, dict):
                    first_argument = value['method']
                    second_argument = value['args']
                try:
                    return self._load_module(first_argument,
                                             which_module,
                                             **second_argument)
                except (ModuleLoadError, ModuleAlreadyLoadedError) as ex:
                    the_module = self.loaded_modules[which_module]
                    the_module.handler_communicate(
                        reason='load_module_failed',
                        exception=ex)

            if kwg == 'unload_module':
                try:
                    self._unload_module(value,
                                        which_module)
                except (ModuleNotLoadedError, CannotUnloadError) as ex:
                    the_module = self.loaded_modules[which_module]
                    the_module.handler_communicate(
                        reason='unload_module_failed',
                        exception=ex)

            if kwg == 'install_custom_hook':
                try:
                    self._install_custom_hook(value,
                                              which_module)
                except HookAlreadyInstalledError as ex:
                    the_module = self.loaded_modules[which_module]
                    the_module.handler_communicate(
                        reason='install_hook_failed',
                        exception=ex)

            if kwg == 'install_custom_method':
                if isinstance(value, (list, tuple)):
                    first_argument = value[0]
                    second_argument = value[1]
                elif isinstance(value, dict):
                    first_argument = value['method']
                    second_argument = value['callback']
                try:
                    self._install_custom_method(first_argument,
                                                second_argument,
                                                which_module)
                except MethodAlreadyInstalledError as ex:
                    the_module = self.loaded_modules[which_module]
                    the_module.handler_communicate(
                        reason='install_method_failed',
                        exception=ex)

            if kwg == 'install_interrupt_handler':
                if isinstance(value, (list, tuple)):
                    first_argument = value[0]
                    second_argument = value[1]
                elif isinstance(value, dict):
                    first_argument = value['interrupt']
                    second_argument = value['callback']
                try:
                    self._install_interrupt_handler(first_argument,
                                                    second_argument,
                                                    which_module)
                except InterruptAlreadyInstalledError as ex:
                    the_module = self.loaded_modules[which_module]
                    the_module.handler_communicate(
                        reason='install_interrupt_failed',
                        exception=ex)

            if kwg == 'require_module_instance':
                if value not in self.loaded_modules:
                    raise ModuleLoadError('instance {} '
                                          'is not present'.format(value))

    def _log_module_message(self, module, level, message):
        """Perform plugin-level logging.

        Args
        ----
        module: str
            Instance name
        level: str
            Log level
        message: str
            The message to be logged
        """
        self.log_message(level, "{}: {}".format(module, message))

    def log_message(self, level, message):
        """Perform general logging.

        Args
        ----
        level: str
           Log level
        message: str
           The message to be logged
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
        Args
        ----
        hook_dict: dict
           Name-indexed dictionary of registered hooks
        hook_name: str
           Name of the hook to be triggered
        kwargs: dict
           Hook arguments
        """
        for attached_callback in hook_dict[hook_name].attached_callbacks:
            try:
                if attached_callback.callback(**kwargs):
                    if attached_callback.action == MMHookAct.LOAD_MODULE:
                        # load the module!
                        self.logger.debug('some hook returned true, '
                                          'loading module {}'
                                          .format(attached_callback.argument))
                        # module must accept same kwargs, this is mandatory
                        # with this discovery event
                        try:
                            cb_arg = attached_callback.argument
                            module_name = cb_arg.get_module_desc().arg_name
                            self.load_module(module_name,
                                             **kwargs)
                        except Exception as ex:
                            self.logger.error('loading of module of class '
                                              '"{}" failed with: {}'
                                              .format(cb_arg.__name__,
                                                      str(ex)))
                    elif attached_callback.action == MMHookAct.UNLOAD_MODULE:
                        # unload the attached module
                        self.logger.debug('a hook required module '
                                          '{} to be unloaded'
                                          .format(attached_callback.argument))
                        self.unload_module(attached_callback.argument)
            except Exception as ex:
                self.logger.error('failed to call function '
                                  '{} attached to "{}" with: {}'
                                  .format(attached_callback,
                                          hook_name,
                                          str(ex)))

    def trigger_custom_hook(self, hook_name, **kwargs):
        """Trigger an installed hook.

        Args
        ----
        hook_name: str
           Hook name
        kwargs: dict
           Keyword arguments
        """
        self._trigger_hooks(self.custom_hooks, hook_name, **kwargs)

    def _trigger_manager_hook(self, hook_name, **kwargs):
        """Trigger an internal manager hook.

        Args
        ----
        hook_name: str
           Hook name
        kwargs: dict
           Keyword arguments
        """
        self._trigger_hooks(self.attached_hooks, hook_name, **kwargs)

    def external_interrupt(self, interrupt_key, **kwargs):
        """External interrupt trigger.

        Args
        ----
        interrupt_key: str
            Interrupt name
        kwargs: dict
            Keyword arguments
        """
        if interrupt_key in self.external_interrupts:
            self.external_interrupts[interrupt_key].call(**kwargs)
