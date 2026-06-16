# coding: utf-8
# load_balance plugin stub
import public

class main:
    def get_check_upstream(self, args):
        return {'status': True, 'data': [], 'msg': 'ok'}

    def get_upstream_list(self, args):
        return {'status': True, 'data': []}

    def add_upstream(self, args):
        return public.return_message(0, 0, 'ok')

    def del_upstream(self, args):
        return public.return_message(0, 0, 'ok')

    def get_config(self, args):
        return {'status': True, 'data': {}}
