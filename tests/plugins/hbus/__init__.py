from viscum.plugin import (Module,
                           ModuleArgument)
from viscum.exception import (HookNotAvailableError,
                              MethodNotAvailableError)
from viscum.hook import ModuleManagerHookActions as MMHookAct
import pyjsonrpc
import os


class HBUSDriverLoadError(Exception):
    pass

_HBUS_CLASS_DRIVER_MAP = {}
_HBUS_LOADED_DRIVER_MAP = {}
_MODULE_DESCRIPTOR = 'hbus.json'


def _hbus_register_class_driver(module_name, device_class):
    _HBUS_CLASS_DRIVER_MAP[int(device_class) & 0xFFFF0000] = module_name


class HBUSDriver(Module):
    _module_desc = ModuleArgument('hbus', 'HBUS Server bridge')
    _required_kw = [ModuleArgument('address', 'node address'),
                    ModuleArgument('port', 'node port')]

    def __init__(self, **kwargs):
        super(HBUSDriver, self).__init__(**kwargs)

        self.interrupt_handler(log_info='HBUS Server detected')

        # attach node_removed hook
        self.interrupt_handler(attach_custom_hook=['ppagg.node_removed',
                                                   [self._node_removed,
                                                    MMHookAct.UNLOAD_MODULE,
                                                    self._registered_id]])

        # install custom methods (redundant but useful)
        self.interrupt_handler(install_custom_method=['hbus.get_active_busses',
                                                      self._get_active_busses])
        self.interrupt_handler(install_custom_method=['hbus.get_active_slaves',
                                                      self._get_active_slaves])
        self.interrupt_handler(install_custom_method=['hbus.get_slave_info',
                                                      self._slave_info])
        self.interrupt_handler(install_custom_method=['hbus.get_slave_object_list',
                                                      self._list_slave_objects])
        self.interrupt_handler(install_custom_method=['hbus.read_object_value',
                                                      self._read_object_value])
        self.interrupt_handler(install_custom_method=['hbus.write_object_value',
                                                      self._write_object_value])

        # rpc client
        self.cli = pyjsonrpc.HttpClient('http://{}:{}'
                                        .format(kwargs['address'],
                                                kwargs['port']))

        # misc
        self._known_devices = set()
        self._last_poll = 0

        self._automap_properties()
        self._automap_methods()

        # attach to tick
        self.interrupt_handler(attach_manager_hook=['modman.tick',
                                                    [self._modman_tick,
                                                     MMHookAct.NO_ACTION,
                                                     self._registered_id]])

        # poll immediately
        self._poll_server()

    def module_unload(self):
        # unload modules which were loaded by this instance
        for uid in _HBUS_LOADED_DRIVER_MAP:
            self.interrupt_handler(unload_module=[_HBUS_LOADED_DRIVER_MAP[uid]])

    def _node_removed(self, **kwargs):
        # see if we were removed
        if kwargs['kind'] == '_hbusrpc._tcp':
            return True

    # some properties
    def _get_active_busses(self):
        return self.cli.activebusses()

    def _get_active_slaves(self):
        return self.cli.activeslavelist()

    # methods
    def _slave_info(self, slave_uid):
        return self.cli.slaveinformation(slave_uid)

    def _list_slave_objects(self, slave_uid):
        return self.cli.slaveobjectlist(slave_uid)

    def _read_object_value(self, slave_address, object_index):
        # blocking call

        # initiate read
        status = self.cli.readobject(slave_address, object_index)
        if status['status'] == 'error':
            # failed!
            self.interrupt_handler(log_error='failed to read object {}:{}: {}'
                                   .format(slave_address,
                                           object_index,
                                           status['error']))
            return None

        # wait
        while True:
            status = self.cli.readfinished()
            if status['status'] == 'ok':
                try:
                    if status['value']:
                        break
                except KeyError:
                    self.interrupt_handler(log_error='failed to read '
                                           'object {}:{}: {}'
                                           .format(slave_address,
                                                   object_index,
                                                   status['error']))
                    return None

        # get data
        data = self.cli.retrievelastdata()
        try:
            return data['value']
        except KeyError:
            self.interrupt_handler(log_error='failed to read object {}:{}: {}'
                                   .format(slave_address,
                                           object_index,
                                           status['error']))
            return None

    def _write_object_value(self, slave_address, object_index, object_value):
        return self.cli.writeobject(slave_address, object_index, object_value)

    # server polling
    def _modman_tick(self, uptime):

        # only poll every minute or so
        if self._last_poll < 60:
            self._last_poll += 1
        else:
            self._last_poll = 0
            self._poll_server()

    def _poll_server(self):
        try:
            active_devices = set(self._get_active_slaves()['list'])
        except KeyError:
            self.interrupt_handler(log_error='error while polling server!')
            return

        if self._known_devices != active_devices:
            # do stuff!
            for uid in self._known_devices:
                if uid not in active_devices:
                    # remove!
                    self.interrupt_handler(unload_module=_HBUS_LOADED_DRIVER_MAP[uid])
                    del _HBUS_LOADED_DRIVER_MAP[uid]

            for uid in active_devices:
                try:
                    int_uid = int(uid)
                except TypeError:
                    self.interrupt_handler(log_warning='got invalid '
                                           'device UID')
                    continue
                class_uid = int_uid & 0xFFFF0000
                if uid not in self._known_devices:
                    # add!
                    if class_uid in _HBUS_CLASS_DRIVER_MAP:
                        # load module if it exists
                        self.interrupt_handler(log_info='driver for class '
                                               'device {} found: {}, loading'
                                               .format(hex(class_uid >> 16),
                                                       _HBUS_CLASS_DRIVER_MAP[class_uid]))
                        instance_name = self.interrupt_handler(load_module=[_HBUS_CLASS_DRIVER_MAP[class_uid],
                                                                            {'uid': uid}])
                        _HBUS_LOADED_DRIVER_MAP[uid] = instance_name
                    else:
                        self.interrupt_handler(log_info='driver for device '
                                               'class {} not found'
                                               .format(hex(class_uid >> 16)))

            #update
            self._known_devices = active_devices

    @classmethod
    def new_node_detected(cls, **kwargs):

        if kwargs['kind'] != '_hbusrpc._tcp':
            return False

        return True


def discover_module(**kwargs):
    class HBUSDriverProxy(HBUSDriver):
        _, _properties, _methods =\
            Module.build_module_structure_from_file(os.path.join(kwargs['plugin_path'],
                                                                 _MODULE_DESCRIPTOR))

    service_inserted = False
    try:
        service_inserted =\
            kwargs['modman'].call_custom_method('ppagg.add_mdns_kind',
                                                '_hbusrpc._tcp')

    except MethodNotAvailableError:
        raise

    if service_inserted is False:
        raise Exception('could not insert service type')

    try:
        kwargs['modman'].attach_custom_hook('ppagg.node_discovered',
                                            HBUSDriver.new_node_detected,
                                            MMHookAct.LOAD_MODULE,
                                            HBUSDriverProxy)
    except HookNotAvailableError:
        raise

    # install some methods unrelated to the actual
    # class (in the global scope of this file)
    kwargs['modman'].install_custom_method('hbus.register_class_driver',
                                           _hbus_register_class_driver)

    return HBUSDriverProxy
