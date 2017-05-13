from viscum.plugin import (Module,
                           ModuleArgument,
                           ModuleCapabilities)
from viscum.hook import ModuleManagerHookActions as MMHookAct
#import requests
#import xmltodict
import socket
import re
import os.path

MODULE_VERSION = '0.1'

BDP150_SSDP_REGEX = re.compile(r'uuid:([0-9A-Za-z\-]+)::urn:pioneer-co-jp:device:PioControlServer:1')


def module_version():
    return MODULE_VERSION

_ALLOWED_KEY_LIST = {'KEY_PREVIOUS': 'A181AF3E',
                     'KEY_NEXT': 'A181AF3D',
                     'KEY_REWIND': 'AF181AFEA',
                     'KEY_FASTFORWARD': 'AF181AFE9',
                     'KEY_PLAY': 'A181AF39',
                     'KEY_ENTER': 'A181AFEF',
                     'KEY_LEFT': 'A187FFFF',
                     'KEY_RIGHT': 'A186FFFF',
                     'KEY_DOWN': 'A185FFFF',
                     'KEY_UP': 'A184FFFF',
                     'KEY_RETURN': 'A181AFF4',
                     'KEY_1': 'A181AFA1',
                     'KEY_2': 'A181AFA2',
                     'KEY_3': 'A181AFA3',
                     'KEY_4': 'A181AFA4',
                     'KEY_5': 'A181AFA5',
                     'KEY_6': 'A181AFA6',
                     'KEY_7': 'A181AFA7',
                     'KEY_8': 'A181AFA8',
                     'KEY_9': 'A181AFA9',
                     'KEY_0': 'A181AFA0',
                     'KEY_EJECTCLOSECD': 'A181AFB6',
                     'KEY_AUDIO': 'A181AFBE',
                     'KEY_SUBTITLE': 'A181AF36',
                     'KEY_INFO': 'A181AFE3',
                     'KEY_A': 'A181AF60',
                     'KEY_B': 'A181AF61',
                     'KEY_C': 'A181AF62',
                     'KEY_D': 'A181AF63',
                     'KEY_HOME': 'A181AFB0',
                     'KEY_TOOLS': 'A181AFB4',
                     'KEY_STOP': 'A181AF38',
                     'KEY_EXIT': 'A181AF20',
                     'KEY_POWER': 'A181AFBC'}


class BDP150Driver(Module):
    """BDP150 driver
    """
    _module_desc = ModuleArgument('bdp150', 'BDP-150 driver')
    _capabilities = [ModuleCapabilities.MultiInstanceAllowed]
    _required_kw = [ModuleArgument('LOCATION', 'address'),
                    ModuleArgument('USN', 'USN')]

    def __init__(self, **kwargs):
        super(BDP150Driver, self).__init__(**kwargs)

        # attach to ssdp remove hook
        self.interrupt_handler(attach_custom_hook=['ppagg.ssdp_removed',
                                                   [self._ssdp_removed,
                                                    MMHookAct.UNLOAD_MODULE,
                                                    self._registered_id]])

        m = BDP150_SSDP_REGEX.match(kwargs['USN'])
        self.bdp_uuid = m.group(1)

        m = re.match(r'http://([a-zA-Z0-9\.\-]+):.*', kwargs['LOCATION'])
        self.address = m.group(1)

        # automap methods
        self._automap_methods()
        # automap properties
        self._automap_properties()

    def _bdp_communicate(self, to_send, receive=True):
        """Communicate with the player"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        sock.connect((self.address,
                      8102))
        sock.sendall('{}\r\n'.format(to_send))
        if receive:
            resp = sock.recv(1000).strip()
        else:
            resp = None
        sock.close()
        return resp

    def _send_remote_key(self, key_name):
        """Send a single key press
        """

        if key_name not in _ALLOWED_KEY_LIST:
            self.log_error('Invalid key name: {}'.format(key_name))
            return

        self._bdp_communicate('/{}/RU'.format(_ALLOWED_KEY_LIST[key_name]))

    def _get_power_state(self):
        """Get current Power state"""
        resp = self._bdp_communicate('?P')

        if resp == 'E04':
            return False
        else:
            return True

    def _set_power_state(self, state):
        """Set current power state
        """

        if state:
            self._bdp_communicate('PN', False)
        else:
            self._bdp_communicate('PF', False)

    def _get_tray(self):
        resp = self._bdp_communicate('?P')

        if resp == 'P00':
            return 'open'
        else:
            return 'closed'

    def _set_tray(self, state):
        if state == 'open':
            self._bdp_communicate('OP', False)
        elif state == 'closed':
            self._bdp_communicate('CO', False)

    @classmethod
    def new_ssdp_service(self, **kwargs):
        """SSDP Discovery callback
        """
        m = BDP150_SSDP_REGEX.match(kwargs['USN'])
        #print kwargs['USN']

        if m is not None:
            return True

        return False

    def _ssdp_removed(self, **kwargs):
        """SSDP removal callback
        """
        m = BDP150_SSDP_REGEX.match(kwargs['USN'])

        if m is not None:
            if m.group(1) == self.bdp_uuid:
                return True

        return False


def discover_module(**kwargs):
    # load methods and properties from file
    class BDP150DriverProxy(BDP150Driver):
        _, _properties, _methods =\
            Module.build_module_structure_from_file(os.path.join(kwargs['plugin_path'],
                                                                 'bdp150.json'))

    # add SSDP discoverer
    kwargs['modman'].call_custom_method('ppagg.add_ssdp_search',
                                        host_addr='239.255.255.250',
                                        host_port=1900,
                                        service_type='urn:pioneer-co-jp:device:PioControlServer:1')

    # attach to discovery hook
    kwargs['modman'].attach_custom_hook('ppagg.ssdp_discovered',
                                        BDP150Driver.new_ssdp_service,
                                        MMHookAct.LOAD_MODULE,
                                        BDP150DriverProxy)

    return BDP150DriverProxy
