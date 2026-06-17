# coding: utf-8
# tamper_proof (enterprise tamper protection) plugin stub
import public

class main:
    def get_status(self, args):
        return {'status': True, 'open': False}

    def set_status(self, args):
        return public.return_message(0, 0, 'ok')

    def get_site_list(self, args):
        return {'status': True, 'data': []}

    def add_site(self, args):
        return public.return_message(0, 0, 'ok')

    def del_site(self, args):
        return public.return_message(0, 0, 'ok')

    def get_log(self, args):
        return {'status': True, 'data': [], 'total': 0}

    def get_config(self, args):
        return {'status': True, 'data': {}}

    def set_config(self, args):
        return public.return_message(0, 0, 'ok')

    def check_tamper(self, args):
        return {'status': True, 'data': [], 'msg': 'ok'}

    def restore_file(self, args):
        return public.return_message(0, 0, 'ok')

    def get_protect_list(self, args):
        return {'status': True, 'data': []}
