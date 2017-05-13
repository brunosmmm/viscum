"""Test cases."""


from viscum import ModuleManager
from viscum.exception import MethodNotAvailableError, HookNotAvailableError
from viscum.plugin import (Module, ModuleArgument)
from viscum.plugin.prop import ModuleProperty, ModulePropertyPermissions
from viscum.plugin.method import ModuleMethod, ModuleMethodArgument
from viscum.plugin.exception import (ModulePropertyPermissionError,
                                     ModuleInvalidPropertyError,
                                     ModuleLoadError, ModuleMethodError)
from viscum.plugin.util import load_plugin_component
from viscum.scripting import ModuleManagerScript, ModuleProxy
from viscum.scripting.exception import DeferScriptLoading, CancelScriptLoading
import os


class TestError(Exception):
    """Error that stops tests."""

    pass


class TestModuleOne(Module):
    """A sample test module."""

    _module_desc = ModuleArgument('module_one', 'module one')

    def __init__(self, *args, **kwargs):
        super(TestModuleOne, self).__init__(*args, **kwargs)

        kwargs['handler'](self, require_module_instance='module_two')

        # install a bunch of things using the handler
        kwargs['handler'](
            self, install_custom_method=('mod_one.method', self.method))

        kwargs['handler'](
            self,
            install_interrupt_handler=('mod_one.interrupt', self.int_handler))

        kwargs['handler'](self, install_custom_hook='mod_one.hook')

        kwargs['handler'](
            self, attach_manager_hook=('modman.tick', (self.tick, None, None)))

    def method(self, *args, **kwargs):
        self.log_info('method() was called with: {}, {}'.format(args, kwargs))

    def int_handler(self, *args, **kwargs):
        self.log_info('interrupt() was called')

    def tick(self, *args, **kwargs):
        self.log_info('tick() was called!')


class TestModuleTwo(Module):
    """Another test module."""

    _module_desc = ModuleArgument('module_two', 'module two')
    _properties = {
        'property1':
        ModuleProperty('A property'),
        'property2':
        ModuleProperty('Another property', ModulePropertyPermissions.READ),
        'property3':
        ModuleProperty('A third property', ModulePropertyPermissions.WRITE)
    }
    _methods = {'method1': ModuleMethod('A method')}

    def _get_property1(self):
        return None

    def _set_property1(self, value):
        pass

    def _get_property2(self):
        return None

    def _set_property3(self, value):
        pass

    def _method1(self):
        pass

    def __init__(self, *args, **kwargs):

        super(TestModuleTwo, self).__init__(*args, **kwargs)

        self._automap_properties()
        self._automap_methods()

    def handler_communicate(self, **kwargs):

        if 'reason' in kwargs:
            if kwargs['reason'] == 'call_method_failed':
                raise kwargs['exception']


def test_module():

    modman = ModuleManager(
        central_log='test', plugin_path=None, script_path=None)

    class TestModule(Module):
        _required_kw = [ModuleArgument('required_kw1', 'A required kwarg')]
        _optional_kw = [ModuleArgument('optional_kw1', 'An optional kwarg')]
        _module_desc = ModuleArgument('test_mod', 'A test module')
        _properties = {'property1': ModuleProperty('A property')}
        _methods = {'method1': ModuleMethod('A method')}

        def _get_property1(self):
            return None

        def _set_property1(self, value):
            pass

        def _method1(self):
            pass

        def __init__(self, *args, **kwargs):

            super(TestModule, self).__init__(*args, **kwargs)

            self._automap_properties()
            self._automap_methods()

    # insert module class
    modman.insert_module(TestModule)

    # load module through manager because it doesn't make a lot of sense to
    # instantiate directly
    try:
        # intended to fail
        instance_name = modman.load_module('test_mod', optional_kw1=None)
        raise TestError('error')
    except ModuleLoadError:
        pass

    instance_name = modman.load_module(
        'test_mod', required_kw1='sample', optional_kw1=None)

    # not advisable in production
    mc = modman.loaded_modules[instance_name]

    mc.log_info('msg')
    mc.log_warning('msg')
    mc.log_error('msg')

    try:
        # intended to fail
        mc.get_property_value('some_property')
        raise TestError
    except ModuleInvalidPropertyError:
        pass
    try:
        # intended to fail
        mc.set_property_value('some_property', 'some_value')
        raise TestError
    except ModuleInvalidPropertyError:
        pass

    p = mc.get_property_value('property1')
    mc.set_property_value('property1', 'some_value')

    kw = mc.get_loaded_kwargs('optional_kw1')

    try:
        # intended to fail
        mc.call_method('nonexisting_method', some='argument')
        raise TestError
    except ModuleMethodError:
        pass

    try:
        # must fail, called with wrong kwargs
        mc.call_method('method1', some='argument')
        raise TestError
    except ModuleMethodError:
        pass

    # not intended to fail now
    ret = mc.call_method('method1')

    the_properties = TestModule.get_module_properties()
    the_methods = TestModule.get_module_methods()
    the_structure = TestModule.dump_module_structure()

    # build from JSON
    mod = Module.build_module_structure_from_file('tests/module.json')

    # other classmethods
    cap = TestModule.get_capabilities()
    desc = TestModule.get_module_desc()
    req_kw = TestModule.get_required_kwargs()
    opt_kw = TestModule.get_optional_kwargs()
    t = TestModule.get_module_type()
    info = TestModule.get_module_info()
    suffix = TestModule.get_multi_inst_suffix()

    # unload module
    modman.unload_module(instance_name)


def test_method():

    method = ModuleMethod(
        'a description',
        method_args=None,
        method_return=None,
        method_call=None,
        other_argument=None)
    method_argument = ModuleMethodArgument(
        'argument description',
        argument_required=False,
        data_type=None,
        other_argument=None)

    method.add_arguments({'some_argument': method_argument})


def test_module_manager():
    def mymethod(**kwargs):
        pass

    def myhook_callback(**kwargs):
        pass

    def myinterrupt_callback(**kwargs):
        pass

    modman = ModuleManager(
        central_log='test',
        plugin_path=os.path.join('tests', 'plugins'),
        script_path=None)

    modman.install_custom_hook('prefix.somehook')
    modman.install_custom_method('prefix.mymethod', mymethod)

    # must fail
    try:
        modman.call_custom_method('some.nonexistent_method')
        raise TestError
    except MethodNotAvailableError:
        pass

    # must not fail
    modman.call_custom_method('prefix.mymethod', some='argument')

    # must fail
    try:
        modman.attach_custom_hook('some.nonexistent_hook', None, None, None)
        raise TestError
    except HookNotAvailableError:
        pass

    # must not fail
    modman.attach_custom_hook('prefix.somehook', myhook_callback, None, None)

    # must fail
    try:
        modman.attach_manager_hook('modman.nonexistent_hook', myhook_callback,
                                   None, None)
        raise TestError
    except HookNotAvailableError:
        pass

    # must not fail
    modman.attach_manager_hook('modman.tick', myhook_callback, None, None)

    modman.install_interrupt_handler('some_interrupt', myinterrupt_callback)

    modman.insert_module(TestModuleOne)

    # try to load, will fail
    try:
        instance_one = modman.load_module('module_one')
        raise TestError
    except ModuleLoadError:
        pass

    # load second one
    modman.insert_module(TestModuleTwo)
    instance_two = modman.load_module('module_two')

    # now load first one
    instance_one = modman.load_module('module_one')

    modman.module_system_tick()

    # discover
    modman.discover_modules()

    ml = modman.get_loaded_module_list()
    il = modman.get_instance_list_by_type('module_one')
    i_type = modman.get_instance_type(instance_one)
    cap = modman.get_module_capabilities('module_one')
    struct = modman.get_module_structure('module_one')
    info = modman.get_module_info('module_one')

    # succeed
    val = modman.get_module_property(instance_two, 'property1')

    # fail
    val = modman.get_module_property('nonexisting_instance', 'property')
    val = modman.get_module_property(instance_two, 'property_nonexistent')
    val = modman.get_module_property(instance_two, 'property3')

    # succeed
    modman.set_module_property(instance_two, 'property1', 0)

    # fail
    modman.set_module_property('nonexisting_instance', 'property', 0)
    modman.set_module_property(instance_two, 'property_nonexistent', 0)
    modman.set_module_property(instance_two, 'property2', 0)

    plist = modman.get_module_property_list(instance_two)
    mlist = modman.get_module_method_list(instance_two)

    # call module method

    # succeed
    modman.call_module_method(instance_two, 'method1')

    # fail
    modman.call_module_method(instance_two, 'nonexisting_method')
    modman.call_module_method(instance_two, 'method1', wrong='kwarg')
    modman.call_module_method('nonexistent_instance', 'method')

    modlist = modman.list_loaded_modules()
    discovered = modman.list_discovered_modules()
    modman.log_message('log_info', 'test')
    modman.log_message('log_warning', 'a warning')

    # trigger custom hook
    modman.attach_custom_hook('mod_one.hook', myhook_callback, None, None)
    modman.trigger_custom_hook('prefix.somehook')

    mod_two = modman.loaded_modules[instance_two]

    try:
        ret = mod_two.interrupt_handler(call_custom_method=(
            'nonexisting.method', []))
        raise TestError
    except MethodNotAvailableError:
        pass

    ret = mod_two.interrupt_handler(call_custom_method={
        'method': 'mod_one.method',
        'args': ['one', 'two']
    })

    #external interrupt
    modman.external_interrupt('mod_one.interrupt', some='argument')


def test_scripting_proxy():

    modman = ModuleManager(
        central_log='test',
        plugin_path=os.path.join('tests', 'plugins'),
        script_path=os.path.join('tests', 'scripts'))

    modman.insert_module(TestModuleOne)
    modman.insert_module(TestModuleTwo)

    instance_two = modman.load_module('module_two')
    instance_one = modman.load_module('module_one')

    prox = ModuleProxy('module_two', modman)
    insts = prox.get_available_instances()
    repr(insts)
    prox_inst = prox.get_instance(instance_two)

    # get method from module
    mod_two_method = prox_inst.method1

    # try to get inexistent module
    try:
        mod_two_inexistent = prox_inst.nonexisting_method
        raise TestError
    except AttributeError:
        pass

    # cause deferring
    try:
        inst = prox.get_instance('someinstance')
        raise TestError
    except DeferScriptLoading:
        pass


def test_scripting_modman():

    modman = ModuleManager(
        central_log='test',
        plugin_path=os.path.join('tests', 'plugins'),
        script_path=os.path.join('tests', 'scripts'))

    modman.discover_modules()
    # loaded scripts perform some testing of the scripting engine
    modman.discover_scripts()
    modman.insert_module(TestModuleOne)
    modman.insert_module(TestModuleTwo)

    instance_two = modman.load_module('module_two')
    instance_one = modman.load_module('module_one')


def test_scripting_main():
    modman = ModuleManager(
        central_log='test',
        plugin_path=os.path.join('tests', 'plugins'),
        script_path=os.path.join('tests', 'scripts'))

    modman.discover_modules()
    modman.insert_module(TestModuleOne)
    modman.insert_module(TestModuleTwo)

    path = os.path.join('tests', 'scripts', 'hello.py')
    hello = ModuleManagerScript(path, modman, initialize=True)

    path = os.path.join('tests', 'scripts', 'cancel.py')
    try:
        cancel = ModuleManagerScript(path, modman, initialize=True)
        raise TestError
    except CancelScriptLoading:
        pass

    path = os.path.join('tests', 'scripts', 'require.py')
    modman.load_module('module_two')
    # defer loading
    try:
        req = ModuleManagerScript(path, modman, initialize=True)
        raise TestError
    except DeferScriptLoading:
        pass

    # load the module
    modman.load_module('module_one')

    path = os.path.join('tests', 'scripts', 'hooks.py')
    hooks = ModuleManagerScript(path, modman, initialize=True)

    #raise TestError


def test_misc():
    try:
        load_plugin_component(
            os.path.join('tests', 'plugins', 'ppnode'), 'node')
    except:
        pass
