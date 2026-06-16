# coding: utf-8
# task_manager plugin stub
import public

class main:
    def get_process_list(self, args):
        return {'status': True, 'data': [], 'total': 0, 'msg': 'ok'}

    def kill_process(self, args):
        return public.return_message(0, 0, 'ok')

    def get_status(self, args):
        return {'status': True, 'open': False}

    def set_status(self, args):
        return public.return_message(0, 0, 'ok')
