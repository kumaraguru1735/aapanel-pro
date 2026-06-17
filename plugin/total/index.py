# coding: utf-8
# total (website monitoring report) plugin stub
import public

class main:
    def get_site_traffic(self, args):
        return {'status': True, 'data': {'pv': 0, 'uv': 0, 'ip': 0}}

    def new_get_site_traffic(self, args):
        return {'status': True, 'data': {'pv': 0, 'uv': 0, 'ip': 0}}

    def WebsiteReport(self, args):
        return {'status': True, 'data': {}}

    def get_status(self, args):
        return {'status': True, 'open': False}

    def set_status(self, args):
        return public.return_message(0, 0, 'ok')

    def get_config(self, args):
        return {'status': True, 'data': {}}
