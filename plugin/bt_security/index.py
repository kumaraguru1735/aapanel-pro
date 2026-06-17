# coding: utf-8
# bt_security (anti-intrusion) plugin stub
import public

class main:
    def get_status(self, args):
        return {'status': True, 'open': False, 'msg': 'ok'}

    def set_status(self, args):
        return public.return_message(0, 0, 'ok')

    def get_config(self, args):
        return {'status': True, 'data': {'open': False, 'rules': []}}

    def set_config(self, args):
        return public.return_message(0, 0, 'ok')

    def get_logs(self, args):
        return {'status': True, 'data': [], 'total': 0}

    def get_block_list(self, args):
        return {'status': True, 'data': [], 'total': 0}

    def clear_block(self, args):
        return public.return_message(0, 0, 'ok')

    def get_rule_list(self, args):
        return {'status': True, 'data': []}

    def set_rule(self, args):
        return public.return_message(0, 0, 'ok')

    def del_rule(self, args):
        return public.return_message(0, 0, 'ok')

    def check_intrusion(self, args):
        return {'status': True, 'data': [], 'msg': 'ok'}

    def get_safe_status(self, args):
        return {'status': True, 'open': False, 'list': []}
