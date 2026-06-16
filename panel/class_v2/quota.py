# coding: utf-8
# quota module stub for module_run() calls
import public

class main:
    def get_quota_mysql(self, args):
        return {'status': True, 'data': []}

    def get_quota_list(self, args):
        return {'status': True, 'data': []}

    def set_quota(self, args):
        return public.return_message(0, 0, 'ok')

    def del_quota(self, args):
        return public.return_message(0, 0, 'ok')

    def get_disk_quota(self, args):
        return {'status': True, 'data': []}

    def set_disk_quota(self, args):
        return public.return_message(0, 0, 'ok')

    def get_mysql_quota(self, args):
        return {'status': True, 'data': []}

    def set_mysql_quota(self, args):
        return public.return_message(0, 0, 'ok')
