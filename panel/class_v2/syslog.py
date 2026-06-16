# coding: utf-8
# syslog module stub for module_run() calls
import public

class main:
    def get_ssh_error(self, args):
        return {'status': True, 'data': [], 'total': 0}

    def get_log(self, args):
        return {'status': True, 'data': [], 'total': 0}

    def get_login_log(self, args):
        return {'status': True, 'data': [], 'total': 0}

    def clear_log(self, args):
        return public.return_message(0, 0, 'ok')

    def get_syslog(self, args):
        return {'status': True, 'data': []}
