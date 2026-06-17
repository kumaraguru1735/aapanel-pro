# coding: utf-8
# nodejs plugin stub
import os, public

class main:
    def get_default_env(self, args):
        # try to find node in common locations
        for p in ['/usr/bin/node', '/usr/local/bin/node', '/root/.nvm/versions/node']:
            if os.path.exists(p):
                return p
        return None

    def get_version_list(self, args):
        return {'status': True, 'data': []}

    def get_current_version(self, args):
        return {'status': True, 'version': ''}

    def install_version(self, args):
        return public.return_message(0, 0, 'ok')
