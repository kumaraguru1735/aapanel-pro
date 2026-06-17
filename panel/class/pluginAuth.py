# coding: utf-8
# Mock pluginAuth — used by v1 class/safeModel/firewallModel.py

import time

_PRO_EXPIRY = int(time.time()) + 10 * 365 * 24 * 3600


class Plugin:
    def __init__(self, init_plugin_name=None):
        pass

    def get_plugin_list(self, upgrade_force=False):
        return {
            'pro': str(_PRO_EXPIRY),
            'ltd': str(_PRO_EXPIRY),
            'status': True,
            'msg': 'ok',
        }
