# coding: utf-8
# firewall module stub for module_run() calls
import public

class main:
    def check_firewall_rule(self, args):
        return {'status': True, 'data': []}

    def create_rules(self, args):
        return public.return_message(0, 0, 'ok')

    def remove_rules(self, args):
        return public.return_message(0, 0, 'ok')

    def get_status(self, args):
        return {'status': True, 'open': False}

    def set_status(self, args):
        return public.return_message(0, 0, 'ok')

    def get_rules(self, args):
        return {'status': True, 'data': []}

    def add_rule(self, args):
        return public.return_message(0, 0, 'ok')

    def del_rule(self, args):
        return public.return_message(0, 0, 'ok')

    def get_accept_ips(self, args):
        return {'status': True, 'data': []}

    def add_accept_ip(self, args):
        return public.return_message(0, 0, 'ok')

    def del_accept_ip(self, args):
        return public.return_message(0, 0, 'ok')

    def get_drop_ips(self, args):
        return {'status': True, 'data': []}

    def add_drop_ip(self, args):
        return public.return_message(0, 0, 'ok')

    def del_drop_ip(self, args):
        return public.return_message(0, 0, 'ok')

    def get_port_list(self, args):
        return {'status': True, 'data': []}

    def set_port(self, args):
        return public.return_message(0, 0, 'ok')

    def del_port(self, args):
        return public.return_message(0, 0, 'ok')
