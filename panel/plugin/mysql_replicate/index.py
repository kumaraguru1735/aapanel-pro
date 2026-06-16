# coding: utf-8
# mysql_replicate plugin stub
import public

class main:
    def get_replicate_status(self, args):
        return {'status': True, 'running': False, 'data': {}, 'msg': 'ok'}

    def repair_replicate(self, args):
        return public.return_message(0, 0, 'ok')

    def start_replicate(self, args):
        return public.return_message(0, 0, 'ok')

    def stop_replicate(self, args):
        return public.return_message(0, 0, 'ok')

    def get_config(self, args):
        return {'status': True, 'data': {}}

    def set_config(self, args):
        return public.return_message(0, 0, 'ok')
