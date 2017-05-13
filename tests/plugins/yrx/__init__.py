from viscum.plugin import (Module,
                           ModuleArgument,
                           ModuleCapabilities)
from viscum.exception import HookNotAvailableError
from viscum.hook import ModuleManagerHookActions as MMHookAct
import re
import rxv
import os.path

YAMAHARX_REGEX = re.compile(r'^RX-A1020 ([0-9]+)')

_ACTIVE_RECEIVER_LIST = []


class YRXNodeDriverLoadError(Exception):
    """Driver load error exception
    """
    pass


class YRXNodeDriver(Module):
    """Yamaha receiver driver
    """
    _module_desc = ModuleArgument('yrx', 'Yamaha RX receiver driver')
    _capabilities = [ModuleCapabilities.MultiInstanceAllowed]
    _required_kw = [ModuleArgument('address', 'node address'),
                    ModuleArgument('port', 'node port'),
                    ModuleArgument('name', 'node advertised name')]

    def __init__(self, **kwargs):
        super(YRXNodeDriver, self).__init__(**kwargs)

        m = YAMAHARX_REGEX.match(kwargs['name'])
        self.identifier = m.group(1)

        if self.identifier in _ACTIVE_RECEIVER_LIST:
            raise YRXNodeDriverLoadError('receiver with id "{}" is already '
                                         'active, not loading'
                                         .format(self.identifier))

        self.interrupt_handler(log_info='new RX-A1020 receiver with id: {}'
                               .format(self.identifier))

        # attach node_removed hook
        self.interrupt_handler(attach_custom_hook=['ppagg.node_removed',
                                                   [self._node_removed,
                                                    MMHookAct.UNLOAD_MODULE,
                                                    self._registered_id]])

        self.rx = rxv.RXV('http://{}:{}/YamahaRemoteControl/ctrl'
                          .format(kwargs['address'],
                                  kwargs['port']), 'RX-A1020')

        self._automap_properties()
        self._automap_methods()

        _ACTIVE_RECEIVER_LIST.append(self.identifier)

    def module_unload(self):
        pass

    def _node_removed(self, **kwargs):
        """mDNS removal callback
        """
        m = YAMAHARX_REGEX.match(kwargs['name'])

        if m is None:
            return False

        if self.identifier == m.group(1):
            _ACTIVE_RECEIVER_LIST.remove(m.group(1))
            return True

    @classmethod
    def new_node_detected(cls, **kwargs):
        """mDNS discovery callback
        """
        m = YAMAHARX_REGEX.match(kwargs['name'])
        if m is None:
            return False

        return True

    def _send_remote_key(self, key_name):

        if key_name == 'KEY_VOLUME_UP':
            self._increment_volume()
        elif key_name == 'KEY_VOLUME_DOWN':
            self._decrement_volume()
        elif key_name == 'KEY_MUTE':
            self.rx.mute = not self.rx.mute

    def _increment_volume(self):
        volume = float(self._get_volume())
        volume += 0.5
        self._set_volume(volume)

    def _decrement_volume(self):
        volume = float(self._get_volume())
        volume -= 0.5
        self._set_volume(volume)

    def _get_volume(self):
        """Get main zone volume
        """
        return self.rx.volume

    def _set_volume(self, value):
        """Set main zone volume
        """
        try:
            self.rx.volume = value
        except Exception:
            self.interrupt_handler(log_warning='Invalid volume value '
                                   'received: "{}"'
                                   .format(value))

    def _get_volume2(self):
        """Get Zone2 volume
        """
        return self.rx.volume2

    def _set_volume2(self, value):
        """Set Zone2 volume
        """
        try:
            self.rx.volume2 = value
        except Exception:
            self.interrupt_handler(log_warning='Invalid volume value '
                                   'received: "{}"'
                                   .format(value))
            return False

    def _get_main_on(self):
        """Get main zone state
        """
        return self.rx.main_on

    def _get_zone_on(self):
        """Get Zone2 state
        """
        return self.rx.zone_on

    def _set_main_on(self, state):
        """Set main zone state
        """
        self.rx.main_on = state

    def _set_zone_on(self, state):
        """Set Zone2 state
        """
        self.rx.zone_on = state

    def _get_zone_input(self):
        """Get current input for zone 2
        """
        return self.rx.zone_input

    def _set_zone_input(self, input_name):
        """Set zone2 input
        """
        if input_name not in self.rx.inputs():
            self.interrupt_handler(log_error='Invalid input: "{}"'
                                   .format(input_name))
            return False

        self.rx.zone_input = input_name

    def _set_main_input(self, input_name):
        """Set main zone input
        """
        if input_name not in self.rx.inputs():
            self.interrupt_handler(log_error='Invalid input: "{}"'
                                   .format(input_name))
            return False

        self.rx.main_input = input_name

    def _get_main_input(self):
        """Get current input for main zone
        """
        return self.rx.main_input


def discover_module(**kwargs):
    class YRXNodeDriverProxy(YRXNodeDriver):
        _, _properties, _methods =\
            Module.build_module_structure_from_file(os.path.join(kwargs['plugin_path'],
                                                                 'yrx.json'))

    try:
        kwargs['modman'].attach_custom_hook('ppagg.node_discovered',
                                            YRXNodeDriver.new_node_detected,
                                            MMHookAct.LOAD_MODULE,
                                            YRXNodeDriver)
    except HookNotAvailableError:
        raise

    return YRXNodeDriverProxy
