import requests
from util.misc import get_full_node_address

NODE_INFO_PATH = 'status/node'
NODE_SERVICES_PATH = 'status/services'
NODE_PLUGINS_PATH = 'status/active_plugins'


class NodeScanError(Exception):
    pass


def retrieve_json_data(node_address, path):

    # simple data retrieval
    r = requests.get(get_full_node_address(node_address)+path)

    if r.ok is False:
        raise NodeScanError('error while connecting to node')

    try:
        return r.json()
    except Exception:
        raise NodeScanError('malformed response from node')


def post_json_data(node_address, path, data):

    headers = {'content-type': 'application/json', 'Accept': 'text/plain'}
    r = requests.post(get_full_node_address(node_address)+path,
                      data=data, headers=headers)

    if r.ok is False:
        raise NodeScanError('error while connecting to node')

    try:
        return r.json()
    except Exception:
        raise NodeScanError('malformed response from node')


def scan_new_node(node_address):
    return retrieve_json_data(node_address, NODE_INFO_PATH)


def scan_node_services(node_address):
    return retrieve_json_data(node_address, NODE_SERVICES_PATH)


def scan_node_modules(node_address):
    return retrieve_json_data(node_address, NODE_PLUGINS_PATH)


def get_module_structure(node_address, module):
    return retrieve_json_data(node_address, 'plugins/{}/structure'
                              .format(module))
