from viscum.plugin import (Module,
                           ModuleArgument,
                           ModuleCapabilities)
from viscum.hook import ModuleManagerHookActions as MMHookAct
from mpd import MPDClient, CommandError
import socket
import os.path


class MPDClientDriverLoadError(Exception):
    """Driver load error exception
    """
    pass


class MPDClientDriver(Module):
    """MPD Client driver
    """
    _module_desc = ModuleArgument('mpd', 'MPD client-driver')
    _capabilities = [ModuleCapabilities.MultiInstanceAllowed]
    _required_kw = [ModuleArgument('address', 'server address'),
                    ModuleArgument('port', 'server port')]
    _optional_kw = [ModuleArgument('password', 'server password')]

    def __init__(self, **kwargs):
        super(MPDClientDriver, self).__init__(**kwargs)

        self.cli = MPDClient()

        # try to connect
        try:
            self.cli.connect(host=kwargs['address'],
                             port=kwargs['port'])
        except socket.error:
            raise MPDClientDriverLoadError('could not connect to server')

        if 'password' in kwargs:
            try:
                self.cli.password(kwargs['password'])
            except CommandError:
                raise MPDClientDriverLoadError('error while trying '
                                               'to input password')

        # disconnect
        self.cli.disconnect()

        # attach callbacks
        self.interrupt_handler(attach_manager_hook=['modman.tick',
                                                    [self._periodic_call,
                                                     MMHookAct.NO_ACTION,
                                                     self._registered_id]])

        self._automap_properties()
        self._automap_methods()

    def connect_mpd(fn):
        """Decorator function
           Connects to server, executes function and disconnects
        """
        def inner(self, *args, **kwargs):
            self._connect()
            ret = fn(self, *args, **kwargs)
            self.cli.disconnect()
            return ret
        return inner

    def catchsocketerror(fn):
        """Decorator
           Catches socket errors and logs them
        """
        def inner(self, *args, **kwargs):
            try:
                return fn(self, *args, **kwargs)
            except socket.error:
                self.interrupt_handler(log_error='could not connect '
                                       'to MPD server')

            return None

        return inner

    def _periodic_call(self, **kwargs):
        """Attached to module manager tick, send idle command?
        """
        pass

    @catchsocketerror
    def _get_random(self):
        """Returns random state
        """
        if self._read_status_key('random') == '0':
            return False
        else:
            return True

    @connect_mpd
    def _set_random(self, state):
        """Set random state
        """
        if state:
            self.cli.random(1)
        else:
            self.cli.random(0)

    @catchsocketerror
    def _get_repeat(self):
        """Returns repeat state
        """

        if self._read_status_key('repeat') == '0':
            return False
        else:
            return True

    @connect_mpd
    def _set_repeat(self, state):
        """Set repeat state
        """
        if state:
            self.cli.repeat(1)
        else:
            self.cli.repeat(0)

    @catchsocketerror
    def _get_single(self):
        """Returns single state
        """
        if self._read_status_key('single') == '0':
            return False
        else:
            return True

    @connect_mpd
    def _set_single(self, state):
        """Set single state
        """
        if state:
            self.cli.single(1)
        else:
            self.cli.single(0)

    @catchsocketerror
    def _get_volume(self):
        """Returns volume
        """
        return self._read_status_key('volume')

    @connect_mpd
    def _set_volume(self, value):
        """Set volume
        """
        self.cli.volume(value)

    @catchsocketerror
    def _get_state(self):
        """Get current state
        """
        return self._read_status_key('state')

    @connect_mpd
    def _next(self):
        """Next song
        """
        self.cli.next()

    @connect_mpd
    def _previous(self):
        """Previous song
        """
        self.cli.previous()

    @connect_mpd
    def _stop(self):
        """Stop playback
        """
        self.cli.stop()

    @connect_mpd
    def _pause(self, resume):
        """Pause / resume
        """
        if resume:
            self.cli.pause(1)
        else:
            self.cli.pause(0)

    def _connect(self):
        """Connect to MPD server
        """
        self.cli.connect(host=self._loaded_kwargs['address'],
                         port=self._loaded_kwargs['port'])

    def _read_status_key(self, key_name):
        """Get some status
        """
        try:
            self._connect()
            ret = self.cli.status()[key_name]
        finally:
            self.cli.disconnect()

        return ret


def discover_module(**kwargs):
    class MPDClientDriverProxy(MPDClientDriver):
        _, _properties, _methods =\
            Module.build_module_structure_from_file(os.path.join(kwargs['plugin_path'],
                                                                 'mpd.json'))

    return MPDClientDriverProxy
