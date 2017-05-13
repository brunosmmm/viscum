from viscum.plugin import (Module,
                           ModuleArgument,
                           ModuleCapabilities)
from viscum.exception import HookNotAvailableError
from viscum.hook import ModuleManagerHookActions as MMHookAct
from viscum.plugin.util import load_plugin_component
import re
import os.path

PERIODIC_PI_NODE_REGEX = re.compile(r'^PeriodicPi node \[([a-zA-Z]+)\]')


class PPNodeDriverLoadError(Exception):
    pass


class PPNodeDriver(Module):
    """PeriodicPi node driver:
       Basically just a proxy that discovers node-side
       services and plugins and loads appropriate drivers
       if available
    """
    _module_desc = ModuleArgument('ppnode', 'PeriodicPi node driver')
    _capabilities = [ModuleCapabilities.MultiInstanceAllowed]
    _required_kw = [ModuleArgument('address', 'node address'),
                    ModuleArgument('port', 'node port'),
                    ModuleArgument('name', 'node advertised name')]

    def __init__(self, **kwargs):
        super(PPNodeDriver, self).__init__(**kwargs)

        m = PERIODIC_PI_NODE_REGEX.match(kwargs['name'])

        # check if node is already registered
        if m.group(1) in\
           self.interrupt_handler(call_custom_method=['ppagg.get_nodes', []]):
            raise PPNodeDriverLoadError('node is already active, '
                                        'not loading another module')

        # to get rid of syntax errors
        from node import PeriodicPiNode
        self.node = PeriodicPiNode(m.group(1),
                                   [kwargs['address'],
                                    kwargs['port']])
        self.node.register_basic_information()

        # get available drivers
        driver_list = self.interrupt_handler('get_available_drivers')
        self.node.register_services(driver_list, self.interrupt_handler)

        # get plugin information, build structures
        self.node.register_node_plugins()

        # connect properties, methods
        self._automap_properties()
        self._automap_methods()

        # attach to custom aggregator hooks
        self.interrupt_handler(attach_custom_hook=['ppagg.node_removed',
                                                   [self._node_removed,
                                                    MMHookAct.UNLOAD_MODULE,
                                                    self._registered_id]])

        self.interrupt_handler(attach_custom_hook=['ppagg.agg_started',
                                                   [self._agg_started,
                                                    MMHookAct.NO_ACTION,
                                                    None]])

        self.interrupt_handler(attach_custom_hook=['ppagg.agg_stopped',
                                                   [self._agg_stopped,
                                                    MMHookAct.NO_ACTION,
                                                    None]])

        # install external interrupt handler
        self.interrupt_handler(install_interrupt_handler=['{}pp.inthandler'
                                                          .format(m.group(1)),
                                                          self._node_interrupt_handler])

        # add to active
        self.interrupt_handler(call_custom_method=['ppagg.add_node',
                                                   [m.group(1),
                                                    [self.node]]])

        # done
        self.interrupt_handler(log_info='new Periodic Pi node: {}'
                               .format(m.group(1)))

    def _get_node_element(self):
        """Returns periodic table element
           assigned as node id
        """
        return self.node.get_node_element()

    def _get_node_plugins(self):
        """Gets available plugins at node side
        """
        return self.node.get_node_plugins()

    def _call_plugin_method(self, instance_name,
                            method_name, method_args=None):
        """Calls a plugin's method
        """
        return self.node.call_plugin_method(instance_name,
                                            method_name,
                                            method_args)

    def _inspect_plugin(self, instance_name):
        """Gets the structure of a plugin
        """
        return self.node.get_node_plugin_structure(instance_name)

    def _node_removed(self, **kwargs):
        """mDNS removal callback
        """
        m = PERIODIC_PI_NODE_REGEX.match(kwargs['name'])

        if m is None:
            return False

        if m.group(1) == self._get_node_element():
            # got removed
            self.node.unregister_services(self.interrupt_handler)
            self.interrupt_handler(call_custom_method=['ppagg.del_node',
                                                       [self._get_node_element()]])
            return True

        return False

    def _node_interrupt_handler(self, **kwargs):
        """Service an interrupt from the node
        """
        pass  # for now

    def _agg_started(self, **kwargs):
        """Server start callback
        """
        self.node.agg_startup(**kwargs)

    def _agg_stopped(self):
        """Server stop callback
        """
        self.node.agg_shutdown()

    def handler_communicate(self, **kwargs):
        """Module manager communication handler
        """
        self.node.handler_int(**kwargs)

    @classmethod
    def new_node_detected(cls, **kwargs):
        """mDNS discovery callback
        """
        m = PERIODIC_PI_NODE_REGEX.match(kwargs['name'])
        if m is None:
            return False

        return True


def discover_module(**kwargs):
    class PPNodeDriverProxy(PPNodeDriver):
        _, _properties, _methods =\
            Module.build_module_structure_from_file(os.path.join(kwargs['plugin_path'],
                                                                 'ppnode.json'))
    try:
        kwargs['modman'].attach_custom_hook('ppagg.node_discovered',
                                            PPNodeDriver.new_node_detected,
                                            MMHookAct.LOAD_MODULE,
                                            PPNodeDriver)

        # TODO: find a better way to do this
        load_plugin_component(kwargs['plugin_path'],
                              'scan')
        load_plugin_component(kwargs['plugin_path'],
                              'node')
    except HookNotAvailableError:
        raise

    return PPNodeDriverProxy
