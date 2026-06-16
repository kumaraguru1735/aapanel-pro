# coding: utf-8
# fail2ban plugin stub
import public

class main:
    def get_status(self, args):
        return {'status': True, 'open': False, 'ban_count': 0, 'jail_list': [], 'msg': 'ok'}

    def get_fail2ban_status(self, args):
        return False

    def set_fail2ban_status(self, args):
        return public.return_message(0, 0, 'ok')

    def set_anti(self, args):
        return public.return_message(0, 0, 'ok')

    def ban_ip_release(self, args):
        return public.return_message(0, 0, 'ok')

    def get_config(self, args):
        return {'status': True, 'data': {}}

    def set_config(self, args):
        return public.return_message(0, 0, 'ok')

    def get_ban_list(self, args):
        return {'status': True, 'data': [], 'total': 0}
