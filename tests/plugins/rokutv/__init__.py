from viscum.plugin import (Module,
                           ModuleArgument,
                           ModuleCapabilities)
from viscum.hook import ModuleManagerHookActions as MMHookAct
import requests
import xmltodict
import re
import os.path

MODULE_VERSION = '0.1'

ROKU_TV_SSDP_REGEX = re.compile(r'uuid:roku:ecp:([0-9A-Za-z]+)')


def module_version():
    return MODULE_VERSION

_ALLOWED_KEY_LIST = ['home', 'rev', 'fwd', 'play',
                     'select', 'left', 'right', 'down', 'up',
                     'back', 'instantreplay', 'info',
                     'backspace', 'search', 'enter', 'volumeup',
                     'volumedown', 'volumemute']

_KEYBOARD_KEY = 'lit_{}'


class RokuTVDriver(Module):
    """RokuTV driver
    """
    _module_desc = ModuleArgument('rokutv', 'Roku TV driver')
    _capabilities = [ModuleCapabilities.MultiInstanceAllowed]
    _required_kw = [ModuleArgument('LOCATION', 'tv address'),
                    ModuleArgument('USN', 'lircd server port')]

    def __init__(self, **kwargs):
        super(RokuTVDriver, self).__init__(**kwargs)

        # attach to ssdp remove hook
        self.interrupt_handler(attach_custom_hook=['ppagg.ssdp_removed',
                                                   [self._ssdp_removed,
                                                    MMHookAct.UNLOAD_MODULE,
                                                    self._registered_id]])

        m = ROKU_TV_SSDP_REGEX.match(kwargs['USN'])
        self.tv_uuid = m.group(1)

        # automap methods
        self._automap_methods()
        # automap properties
        self._automap_properties()

    def _send_remote_key(self, key_name):
        """Send a single key press
        """
        resp = requests.post('{}keypress/{}'
                             .format(self._loaded_kwargs['LOCATION'],
                                     key_name))

    def _start_key_press(self, key_name):
        """Start a continous key press
        """
        resp = requests.post('{}keydown/{}'
                             .format(self._loaded_kwargs['LOCATION'],
                                     key_name))

    def _stop_key_press(self, key_name):
        """Stop a continous key press
        """
        resp = requests.post('{}keyup/{}'
                             .format(self._loaded_kwargs['LOCATION'],
                                     key_name))

    def _list_apps(self):
        """Get list of installed apps
        """
        resp = requests.get('{}query/apps'
                            .format(self._loaded_kwargs['LOCATION']))

        app_list = xmltodict.parse(resp.text)['apps']['app']
        ret_list = {}
        for app in app_list:
            ret_list[app['@id']] = {'description': app['#text'],
                                    'version': app['@version'],
                                    'type': app['@type']}

        return ret_list

    def _launch_app(self, app_id, content_id=None):
        """Launch an installed app
        """
        resp = requests.post('{}launch/{}'
                             .format(self._loaded_kwargs['LOCATION'],
                                     app_id))

    def _query_device_info(self):
        """Get device info
        """
        resp = requests.get('{}query/device_info'
                            .format(self._loaded_kwargs['LOCATION']))

        info = xmltodict.parse(resp.text)

        return info  # for now, TODO parse more

    def _send_text_key(self, char):
        """Send text keypresses
        """
        resp = requests.post('{}keypress/{}'
                             .format(self._loaded_kwargs['LOCATION'],
                                     _KEYBOARD_KEY.format(char)))

    # get icon from an app
    # def _retrieve_app_icon(self, app_id):
    #    resp = requests.get('{}query/icon/{}'
    #                         .format(self._loaded_kwargs['LOCATION'],
    #                                 app_id))

    @classmethod
    def new_ssdp_service(self, **kwargs):
        """SSDP Discovery callback
        """
        m = ROKU_TV_SSDP_REGEX.match(kwargs['USN'])

        if m is not None:
            return True

        return False

    def _ssdp_removed(self, **kwargs):
        """SSDP removal callback
        """
        m = ROKU_TV_SSDP_REGEX.match(kwargs['USN'])

        if m is not None:
            if m.group(1) == self.tv_uuid:
                return True

        return False


def discover_module(**kwargs):
    # load methods and properties from file
    class RokuTVDriverProxy(RokuTVDriver):
        _, _properties, _methods =\
            Module.build_module_structure_from_file(os.path.join(kwargs['plugin_path'],
                                                                 'rokutv.json'))

    # add SSDP discoverer
    kwargs['modman'].call_custom_method('ppagg.add_ssdp_search',
                                        host_addr='239.255.255.250',
                                        host_port=1900,
                                        service_type='roku:ecp')

    # attach to discovery hook
    kwargs['modman'].attach_custom_hook('ppagg.ssdp_discovered',
                                        RokuTVDriver.new_ssdp_service,
                                        MMHookAct.LOAD_MODULE,
                                        RokuTVDriverProxy)

    return RokuTVDriverProxy
