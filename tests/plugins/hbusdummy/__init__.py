from viscum.plugin import (Module,
                           ModuleArgument)
import os.path


class HBUSDummyDriver(Module):
    _module_desc = ModuleArgument('hbusdummy', 'HBUS Dummy device driver')
    _required_kw = [ModuleArgument('uid', 'Device UID')]

    def __init__(self, **kwargs):
        super(HBUSDummyDriver, self).__init__(**kwargs)

        # get device info
        device_info =\
            self.interrupt_handler(call_custom_method=['hbus.get_slave_info',
                                                       [self._loaded_kwargs['uid']]])

        if device_info['status'] != 'ok':
            raise IOError('error getting device information')

        # bus address
        self.hbus_addr = device_info['currentaddress']

        self._automap_properties()

        self.interrupt_handler(log_info='loading dummy driver, '
                               'device uid is {}, addr {}'
                               .format(hex(self._loaded_kwargs['uid']),
                                       self.hbus_addr))

    def _read_object(self, object_index):
        return self.interrupt_handler(call_custom_method=['hbus.read_object_value',
                                                          [self.hbus_addr,
                                                           object_index]])

    def _get_dummyobj1(self):
        return self._read_object(1)

    def _get_dummyobj2(self):
        return self._read_object(2)


def discover_module(**kwargs):

    class HBUSDummyDriverProxy(HBUSDummyDriver):
        _, _properties, _methods =\
            Module.build_module_structure_from_file(os.path.join(kwargs['plugin_path'],
                                                                 'hbusdummy.json'))

    # require hbus
    kwargs['modman'].require_discovered_module('hbus')

    # register hbus dummy driver
    kwargs['modman'].call_custom_method('hbus.register_class_driver',
                                        module_name='hbusdummy',
                                        device_class=0x00010000)

    return HBUSDummyDriverProxy
