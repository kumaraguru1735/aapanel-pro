# coding: utf-8
# btwaf_httpd (apache WAF) plugin stub — mirrors btwaf
import public

class main:
    def get_status(self, args):
        return {'status': True, 'open': False, 'msg': 'ok'}

    def set_status(self, args):
        return public.return_message(0, 0, 'ok')

    def site_waf_config(self, args):
        return {'status': True, 'open': False, 'config': {}}

    def get_config(self, args):
        return {'status': True, 'data': {}}

    def set_config(self, args):
        return public.return_message(0, 0, 'ok')

    def get_rule_list(self, args):
        return {'status': True, 'data': []}

    def get_block_list(self, args):
        return {'status': True, 'data': [], 'total': 0}

    def get_site_config(self, args):
        return {'status': True, 'data': {'open': False}}
