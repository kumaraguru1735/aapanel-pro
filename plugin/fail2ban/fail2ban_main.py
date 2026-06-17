# coding: utf-8
# Fail2ban plugin stub
import public
import os

class fail2ban_main:
    _plugin_path = '/www/server/panel/plugin/fail2ban'

    def index(self, args):
        from flask import make_response
        html_file = self._plugin_path + '/index.html'
        if os.path.exists(html_file):
            return make_response(open(html_file).read(), 200, {'Content-Type': 'text/html; charset=utf-8'})
        return make_response('<p>Fail2ban - Plugin managed via system daemon.</p>', 200, {'Content-Type': 'text/html; charset=utf-8'})

    def get_status(self, args):
        return public.return_message(0, 0, {'status': True, 'open': False, 'msg': 'ok'})

    def set_status(self, args):
        return public.return_message(0, 0, 'ok')

    def get_config(self, args):
        return public.return_message(0, 0, {'data': {}})

    def set_config(self, args):
        return public.return_message(0, 0, 'ok')

    def __getattr__(self, name):
        def _stub(*a, **kw):
            return public.return_message(0, 0, {'status': True, 'msg': 'ok'})
        return _stub
