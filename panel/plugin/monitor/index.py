# coding: utf-8
# monitor (website statistics v2) plugin stub
import public, time

class main:
    def get_site_list(self, args):
        return {'status': True, 'data': []}

    def get_site_traffic(self, args):
        return {'status': True, 'data': {'pv': 0, 'uv': 0, 'ip': 0, 'flow': 0}}

    def new_get_site_traffic(self, args):
        return {'status': True, 'data': {'pv': 0, 'uv': 0, 'ip': 0, 'flow': 0}}

    def get_day_data(self, args):
        return {'status': True, 'data': []}

    def get_status(self, args):
        return {'status': True, 'open': False}

    def set_status(self, args):
        return public.return_message(0, 0, 'ok')

    def get_config(self, args):
        return {'status': True, 'data': {}}
