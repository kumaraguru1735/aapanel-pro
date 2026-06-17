# coding: utf-8
# Jump Server plugin stub
import public

class main:
    def get_status(self, args):
        return public.return_message(0, 0, {'status': True, 'msg': 'ok'})

    def set_status(self, args):
        return public.return_message(0, 0, 'ok')
