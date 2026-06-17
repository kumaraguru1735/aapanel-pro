# coding: utf-8
# rsync (data sync) plugin stub
import public

class main:
    def get_status(self, args):
        return {'status': True, 'open': False}

    def set_status(self, args):
        return public.return_message(0, 0, 'ok')

    def get_task_list(self, args):
        return {'status': True, 'data': [], 'total': 0}

    def add_task(self, args):
        return public.return_message(0, 0, 'ok')

    def del_task(self, args):
        return public.return_message(0, 0, 'ok')

    def run_task(self, args):
        return {'status': True, 'msg': 'ok'}

    def get_log(self, args):
        return {'status': True, 'data': []}

    def get_config(self, args):
        return {'status': True, 'data': {}}

    def set_config(self, args):
        return public.return_message(0, 0, 'ok')

    def get_remote_list(self, args):
        return {'status': True, 'data': []}

    def add_remote(self, args):
        return public.return_message(0, 0, 'ok')

    def del_remote(self, args):
        return public.return_message(0, 0, 'ok')
