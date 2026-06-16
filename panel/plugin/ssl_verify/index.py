# coding: utf-8
# ssl_verify plugin stub
import public

class main:
    def get_status(self, args):
        return {'status': True, 'open': False}

    def set_status(self, args):
        return public.return_message(0, 0, 'ok')

    def get_site_list(self, args):
        return {'status': True, 'data': []}

    def verify_ssl(self, args):
        return {'status': True, 'msg': 'ok'}

    def get_cert_info(self, args):
        return {'status': True, 'data': {}}

    def renew_cert(self, args):
        return {'status': True, 'msg': 'ok'}

    def get_config(self, args):
        return {'status': True, 'data': {}}

    def set_config(self, args):
        return public.return_message(0, 0, 'ok')
