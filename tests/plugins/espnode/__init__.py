from viscum.plugin import Module, ModuleArgument, ModuleCapabilities
from viscum.plugin.prop import ModuleProperty, ModulePropertyPermissions
from viscum.plugin.dtype import ModuleDataTypes
from viscum.exception import HookNotAvailableError
from viscum.hook import ModuleManagerHookActions
import re

ESP_REGEX = re.compile(r'^PESPNode-([a-zA-Z0-9]+)')

class PESPNodeDriver(Module):
    _module_desc = ModuleArgument('pespnode', 'Periodic ESP node driver')
    _capabilities = [ModuleCapabilities.MultiInstanceAllowed]
    _required_kw = [ModuleArgument('address', 'node address'),
                    ModuleArgument('port', 'node port'),
                    ModuleArgument('name', 'node advertised name')]


    def __init__(self, **kwargs):
        super(PESPNodeDriver, self).__init__(**kwargs)

        m = ESP_REGEX.match(kwargs['name'])
        self.node_element = m.group(1)

        self.interrupt_handler(log_info='new ESP node, element is {}'.format(self.node_element))

        #attach node_removed hook
        self.interrupt_handler(attach_custom_hook=['ppagg.node_removed',
                                                   [self._node_removed,
                                                    ModuleManagerHookActions.UNLOAD_MODULE,
                                                    self._registered_id]])

    def module_unload(self):
        pass

    def _node_removed(self, **kwargs):
        #see if we were removed!
        m = ESP_REGEX.match(kwargs['name'])

        if m == None:
            return False

        if self.node_element == m.group(1):
            return True

    @classmethod
    def new_node_detected(cls, **kwargs):

        m = ESP_REGEX.match(kwargs['name'])
        if m == None:
            return False

        return True

def discover_module(**kwargs):
    try:
        kwargs['modman'].attach_custom_hook('ppagg.node_discovered',
                                            PESPNodeDriver.new_node_detected,
                                            ModuleManagerHookActions.LOAD_MODULE,
                                            PESPNodeDriver)
    except HookNotAvailableError:
        raise

    return PESPNodeDriver
