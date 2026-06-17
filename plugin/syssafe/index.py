# coding: utf-8
# syssafe plugin stub — system hardening
import public

class main:
    def get_safe_status(self, args):
        return {'status': True, 'open': False, 'list': [], 'msg': 'ok'}

    def set_open(self, args):
        return public.return_message(0, 0, 'ok')

    def get_config(self, args):
        return {'status': True, 'data': {'open': False, 'list': []}}

    def set_config(self, args):
        return public.return_message(0, 0, 'ok')

    def get_status(self, args):
        return {'status': True, 'open': False, 'list': []}
