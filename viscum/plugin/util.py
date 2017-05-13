"""Miscellaneous plugin utilities."""

import imp
import os.path


def load_plugin_component(plugin_path, module_name):
    """Load plugin sub-module.

    Args
    ----
    plugin_path: str
       Location of plugin
    module_name: str
       Module (plugin) name
    """
    try:
        imp.load_source(module_name, os.path.join(plugin_path,
                                                  '{}.py'
                                                  .format(module_name)))
    except Exception:
        raise
