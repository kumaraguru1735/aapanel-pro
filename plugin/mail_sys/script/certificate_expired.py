#!/usr/bin/python
# coding: utf-8
# -----------------------------
# 定时检测 邮局证书过期告警
# -----------------------------


import subprocess
import time
import datetime
import os,sys, time, re
os.chdir('/www/server/panel')
sys.path.insert(0,'./')
sys.path.insert(1,'class/')
sys.path.insert(2,'BTPanel/')
sys.path.insert(3,'/www/server/panel/plugin/mail_sys')
import public
import public.PluginLoader as plugin_loader

class CertExpiry:
    def __init__(self, ):
        ...

    def check_remaining_time(self, ):
        """
        查看证书剩余有效期
        :param
        :return:  data
        """

        # main = plugin_loader.get_module('{}/plugin/mail_sys/mail_sys_main.py'.format(public.get_panel_path()))
        # mail_sys_main = main.mail_sys_main
        # try:
        #     domain_list = mail_sys_main().get_domain_name(None)
        # except:
        #     public.print_log(public.get_error_info())
        #     print(public.get_error_info())
        #     # domain_list = []
        #     return []

        try:
            from plugin.mail_sys.mail_sys_main import mail_sys_main
            domain_list = mail_sys_main().get_domain_name(None)
        except Exception as e:
            public.print_log(public.get_error_info())
            return []

        data = []
        for domain in domain_list:
            # 查看ssl状态  未开启跳过
            path = '/www/server/panel/plugin/mail_sys/cert/{}/fullchain.pem'.format(domain)
            ssl_conf = public.readFile('/etc/postfix/vmail_ssl.map')
            if not os.path.exists(path):
                continue
            if not ssl_conf or domain not in ssl_conf:
                continue

            # ssl详情
            ssl_info = mail_sys_main().get_ssl_info(domain)
            endtime = ssl_info.get('endtime', None)
            if endtime and endtime <= 10:
                ssl = {
                    "domain": domain,
                    "endtime": endtime,     # 剩余有效期
                    # "notAfter": notAfter,   # 结束时间
                    # "notBefore": notBefore,  # 开始时间
                }

                data.append(ssl)
        return data

    def automatic_renewal(self, service_name: str):
        """
        自动续签 -- 后续更新
        :param service_name: 服务名称
        """
        ...





    def run(self):
        """
        查看证书是否需要告警
        """
        # 查看是否开启了告警
        bulk = plugin_loader.get_module('{}/plugin/mail_sys/mail_send_bulk.py'.format(public.get_panel_path()))
        SendMailBulk = bulk.SendMailBulk


        alarm = False
        args = public.dict_obj()
        args.keyword = 'mail_server_certificate_expired'
        try:
            send_task = SendMailBulk().get_alarm_send(args)
        except:
            public.print_log(public.get_error_info())
            print(public.get_error_info())
            send_task = False
        if send_task and send_task.get('status', False):
            alarm = True

        if alarm:
            # 开启告警  检查ssl信息
            ssl_data = self.check_remaining_time()

            if len(ssl_data) > 0:
                info = ''
                for i in ssl_data:
                    endtime = i['endtime']
                    domain = i['domain']
                    # notAfter = i['notAfter']
                    # notBefore = i['notBefore']


                    if endtime > 0:
                        info += f'<br /> [{domain}] Expires in {endtime} days <br />  '
                    else:
                        info += f'<br /> [{domain}] Expires  <br />  '

                # 已过期
                # body = [f">Send content:Your Mail Service certificate expired.",  f">Results for {info}."]

                # 即将过期
                body = [f">Send content:Your mail service certificate is about to expire.",  f">Results for: {info}"]

                # 推送告警信息
                args1 = public.dict_obj()
                args1.keyword = 'mail_server_certificate_expired'
                args1.body = body
                try:
                    SendMailBulk().send_mail_data(args1)
                    # print('发送')
                except:
                    public.print_log(public.get_error_info())
                    print(public.get_error_info())



if __name__ == '__main__':
    monitor = CertExpiry()
    monitor.run()


