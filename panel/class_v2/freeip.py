# coding: utf-8
# freeip module stub for module_run() calls
import public

class main:
    def get_ip_area(self, args):
        ip = getattr(args, 'ip', '') if hasattr(args, 'ip') else (args.get('ip', '') if isinstance(args, dict) else '')
        return {'status': True, 'area': 'Unknown', 'ip': ip}

    def get_location(self, args):
        return {'status': True, 'data': {'country': '', 'province': '', 'city': '', 'isp': ''}}
