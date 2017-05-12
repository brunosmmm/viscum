"""Miscellaneous plugin utilities
"""
import imp
import os.path


def load_plugin_component(plugin_path, module_name):
    """load plugin sub-module
    """
    try:
        imp.load_source(module_name, os.path.join(plugin_path,
                                                  '{}.py'
                                                  .format(module_name)))
    except Exception:
        raise
