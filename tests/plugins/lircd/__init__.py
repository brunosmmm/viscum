from viscum.plugin import (Module,
                           ModuleArgument,
                           ModuleCapabilities)
from periodicpy.irtools.lirc import LircClient
import os.path

_MODULE_VERSION = '0.1'
_MODULE_DESCRIPTOR = 'lircd.json'


def module_version():
    """Get module version
    """
    return _MODULE_VERSION


class LircdDriver(Module):
    """lircd client driver class
    """
    _module_desc = ModuleArgument('lircd', 'lircd client driver')
    _capabilities = [ModuleCapabilities.MultiInstanceAllowed]
    _required_kw = [ModuleArgument('server_address', 'lircd server address'),
                    ModuleArgument('server_port', 'lircd server port')]

    def __init__(self, **kwargs):
        super(LircdDriver, self).__init__(**kwargs)

        # create lirc client instance
        self.lirc_handler = LircClient(self._loaded_kwargs['server_address'],
                                       self._loaded_kwargs['server_port'])

        # automap methods
        self._automap_methods()
        # automap properties
        self._automap_properties()

    def _get_avail_remotes(self):
        """Return available remotes at the location"""
        return self.lirc_handler.get_remote_list()

    def _get_remote_actions(self, remote_name):
        """Returns available keys for a remote
        """
        return self.lirc_handler.get_remote_key_list(remote_name)

    def _send_remote_key(self, remote_name, key_name, repeat_count=0):
        """Sends a key press
        """
        self.lirc_handler.send_key_once(remote_name, key_name, repeat_count)

    def _start_key_press(self, remote_name, key_name):
        """Starts a continous key press
        """
        self.lirc_handler.start_send_key(remote_name, key_name)

    def _stop_key_press(self, remote_name, key_name):
        """Stops a continuous key press
        """
        self.lirc_handler.stop_send_key(remote_name, key_name)


def discover_module(**kwargs):
    # load methods and properties from file
    class LircdDriverProxy(LircdDriver):
        _, _properties, _methods =\
            Module.build_module_structure_from_file(os.path.join(kwargs['plugin_path'],
                                                                 'lircd.json'))

    return LircdDriverProxy
