#!/usr/bin/python
# coding: utf-8
# +-------------------------------------------------------------------
# | aaPanel
# +-------------------------------------------------------------------
# | Copyright (c) 2015-2099 aaPanel(www.aapanel.com) All rights reserved.
# +-------------------------------------------------------------------
# | Author: wzjie <wzj@aapanel.com>
# | Author: zhwen <zhw@aapanel.com>
# +-------------------------------------------------------------------

# +--------------------------------------------------------------------
# |   宝塔邮局
# +--------------------------------------------------------------------

import binascii, base64, re, json, os, sys, time, shutil, socket, io, math
from genericpath import isfile
from datetime import datetime, timedelta, timezone
import requests
import psutil
import pytz


try:
    from BTPanel import cache
except:
    import cachelib

    cache = cachelib.SimpleCache()
import traceback

if sys.version_info[0] == 3:
    from importlib import reload

if sys.version_info[0] == 2:
    reload(sys)
    sys.setdefaultencoding('utf-8')

sys.path.append('/www/server/panel')

sys.path.append("class/")

import public
import mail_server_init as msi

try:
    import dns.resolver  # type: ignore
except:
    if os.path.exists('/www/server/panel/pyenv'):
        public.ExecShell('/www/server/panel/pyenv/bin/pip install dnspython')
    else:
        public.ExecShell('pip install dnspython')
    import dns.resolver

import smtplib
import email.utils
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.encoders import encode_base64
from email.utils import COMMASPACE, formatdate, formataddr, make_msgid
from email.header import Header
import public.PluginLoader as plugin_loader
bulk = plugin_loader.get_module('{}/plugin/mail_sys/mail_send_bulk.py'.format(public.get_panel_path()))


try:
    import jwt
except:
    public.ExecShell('btpip install pyjwt')
    import jwt
from public.validate import Param
from email.header import decode_header
# from mail_send_bulk import SendMailBulk
import threading

from webmail_roundcube import Roundcube_main
roundcube_main = Roundcube_main()

class SendMail:
    '''
    发件类
    '''
    __setupPath = '/www/server/panel/plugin/mail_sys'
    _session_conf = __setupPath + '/session.json'
    def __init__(self, username, password, server, port=25, usettls=False):
        self._session = self._get_session()
        self.mailUser = username
        self.mailPassword = password
        self.smtpServer = server
        self.smtpPort = port
        self.mailServer = smtplib.SMTP(self.smtpServer, self.smtpPort)
        if usettls:
            self.mailServer.starttls()
        self.mailServer.ehlo()
        self.mailServer.login(self.mailUser, self.mailPassword)
        self.msg = MIMEMultipart()
        self.mailbox_list = [
            'gmail.com',
            'googlemail.com',
            'hotmail.com',
            'outlook.com',
            'yahoo.com',
            'protonmail.com',
            'zoho.com',
            'icloud.com',
        ]
        # 添加发送频率控制相关属性
        self.send_limit_path = self.__setupPath + "/data/send_limit.txt"
        self._send_counter = 0
        self._last_reset_time = time.time()
        self._send_limit = 500 if not os.path.exists(self.send_limit_path) else int(public.readFile(self.send_limit_path))
        self._rate_limit_lock = threading.Lock()


    def _check_rate_limit(self):
        """
        检查发送频率限制
        @return: (bool, int) - (是否可以发送, 需要等待的秒数)
        """
        with self._rate_limit_lock:
            current_time = time.time()
            # 是否重置计数器（每分钟重置）
            if current_time - self._last_reset_time >= 60:
                self._send_counter = 0
                self._last_reset_time = current_time

            # 计算剩余时间
            remaining_time = 60 - (current_time - self._last_reset_time)

            if self._send_counter >= self._send_limit:
                wait_time = max(0, int(remaining_time))
                # public.print_log(f'[限速] 当前已发送: {self._send_counter}/{self._send_limit}, 需等待: {wait_time}秒')
                return False, wait_time

            self._send_counter += 1
            # public.print_log(f'[发送] 计数: {self._send_counter}/{self._send_limit}, 本分钟剩余: {int(remaining_time)}秒')
            return True, 0
    def __del__(self):
        self.mailServer.close()

    # 更新到初始的无内容无主题状态
    def update_init(self, name):
        self.msg = MIMEMultipart()
        sender = formataddr((name, self.mailUser))
        self.msg['From'] = sender
        self.msg['Date'] = formatdate(localtime=True)

    def nwe_msg(self, msgid):
        msg= MIMEMultipart()
        msg['Subject'] = self.msg['Subject']
        msg['From'] = self.msg['From']
        msg['Date'] = self.msg['Date']
        msg['Message-ID'] = msgid

        msg.set_payload(self.msg.get_payload())

        return msg
    def _get_session(self):
        session = public.readFile(self._session_conf)
        if session:
            session = json.loads(session)
        else:
            session = {}
        return session
    def setMailInfo(self, name, subject, text, attachmentFilePaths):

        self.msg['Subject'] = subject
        sender = formataddr((name, self.mailUser))
        self.msg['From'] = sender
        self.msg['Date'] = formatdate(localtime=True)

        self.msg.attach(MIMEText(text, 'html', _charset="utf-8"))
        for attachmentFilePath in attachmentFilePaths:
            self.msg.attach(self.addAttachmentFromFile(attachmentFilePath))
    def setMailInfo_one(self, name):
        sender = formataddr((name, self.mailUser))
        self.msg['From'] = sender
        self.msg['Date'] = formatdate(localtime=True)


    # 用于有退订内容时循环发送 每次重新传如邮件内容
    def setMailInfo_two(self,subject,text, attachmentFilePaths):
        # self.msg = MIMEMultipart()
        self.msg['Subject'] = subject
        self.msg.attach(MIMEText(text, 'html', _charset="utf-8"))
        for attachmentFilePath in attachmentFilePaths:
            self.msg.attach(self.addAttachmentFromFile(attachmentFilePath))


    # 添加附件从网络数据流
    def addAttachment(self, filename, filedata):
        part = MIMEBase('application', "octet-stream")
        part.set_payload(filedata)
        encode_base64(part)
        part.add_header('Content-Disposition', 'attachment; filename="%s"' % str(Header(filename, 'utf8')))
        self.msg.attach(part)

    # 添加附件从本地文件路径
    def addAttachmentFromFile(self, attachmentFilePath):
        part = MIMEBase('application', "octet-stream")
        part.set_payload(open(attachmentFilePath, "rb").read())
        encode_base64(part)
        part.add_header('Content-Disposition', 'attachment; filename="%s"' % str(Header(attachmentFilePath, 'utf8')))
        return part

    # 统计发送 收件人
    def count_receiveUsers(self, receiveUsers):

        data = {
            'gmail': 0,
            'outlook': 0,
            'yahoo.com': 0,
            'icloud.com': 0,
            'other': 0,
        }

        for i in receiveUsers:
            _, domain = i.lower().split('@')
            domain_key = domain if domain in self.mailbox_list else 'other'

            if domain_key in ['gmail.com', 'googlemail.com']:
                domain_key = 'gmail'
            if domain_key in ['hotmail.com', 'outlook.com']:
                domain_key = 'outlook'
            # 累计数量  收件人不属于指定域名 不限制发送数量
            if domain_key != 'other':
                data[domain_key] += 1

        # 获取已有的
        count_sent = '/www/server/panel/plugin/mail_sys/count_sent_domain.json'
        if not os.path.exists(count_sent):
            data_d = {
                'gmail': 0,
                'outlook': 0,
                'yahoo.com': 0,
                'icloud.com': 0,
                'other': 0,
            }
        else:
            try:
                data_d = public.readFile(count_sent)
                data_d = json.loads(data_d)
                # 如果有 data_d 将data_d['outher'] 改为data_d['other']
                if 'outher' in data_d:
                    data_d['other'] = data_d.pop('outher')
            except:

                data_d = {
                    'gmail': 0,
                    'outlook': 0,
                    'yahoo.com': 0,
                    'icloud.com': 0,
                    'other': 0,
                }

        result = {}
        # 累计
        for key in data.keys():
            result[key] = data[key] + data_d[key]
        # 更新文件
        public.writeFile(count_sent, json.dumps(result))

        is_ok = True
        # 判断额度  单个发送
        for key, value in result.items():
            if key == 'other':
                continue

            if value > 5000:

                is_ok = False

        return is_ok

    # 查看单个收件人是否在限额内
    def count_receiveUsers_one(self, receiveUsers):


        data = {
            'gmail': 0,
            'outlook': 0,
            'yahoo.com': 0,
            'icloud.com': 0,
            'other': 0,
        }
        receiveUser = receiveUsers[0]
        _, domain = receiveUser.lower().split('@')
        domain_key = domain if domain in self.mailbox_list else 'other'

        if domain_key in ['gmail.com', 'googlemail.com']:
            domain_key = 'gmail'
        if domain_key in ['hotmail.com', 'outlook.com']:
            domain_key = 'outlook'

        # 累计数量  收件人不属于指定域名 不限制发送数量
        if domain_key != 'other':
            data[domain_key] += 1


        # 获取已有的
        count_sent = '/www/server/panel/plugin/mail_sys/count_sent_domain.json'
        if not os.path.exists(count_sent):
            data_d = {
                'gmail': 0,
                'outlook': 0,
                'yahoo.com': 0,
                'icloud.com': 0,
                'other': 0,
            }
        else:
            try:
                data_d = public.readFile(count_sent)
                data_d = json.loads(data_d)
                # 如果有 data_d 将data_d['outher'] 改为data_d['other']
                if 'outher' in data_d:
                    data_d['other'] = data_d.pop('outher')
            except:

                data_d = {
                    'gmail': 0,
                    'outlook': 0,
                    'yahoo.com': 0,
                    'icloud.com': 0,
                    'other': 0,
                }

        result = {}
        # 累计
        for key in data.keys():
            result[key] = data[key] + data_d[key]
        # # 更新文件
        # public.writeFile(count_sent, json.dumps(result))

        is_ok = True
        # 判断额度  单个发送
        for key, value in result.items():
            if key == 'other':
                continue
            # 超过限额发送失败 不用更新数量
            if value > 5000:

                is_ok = False
                return is_ok
        # 未超过限额 更新文件
        public.writeFile(count_sent, json.dumps(result))
        return is_ok

    def sendMail(self, receiveUsers, domain, is_record, msgid=None):
        # 检查发送频率限制 todo
        can_send, wait_time = self._check_rate_limit()
        if not can_send:
            return public.returnMsg(False, wait_time)

                
        t1 = time.time()
        if not msgid:
            msgid = make_msgid()
        msg = self.nwe_msg(msgid)
        msg['To'] = COMMASPACE.join(receiveUsers)
        try:
            try:
                result = self.mailServer.sendmail(
                    self.mailUser,
                    receiveUsers,
                    msg.as_string()
                )
            except Exception as e:
                public.print_log(public.get_error_info())
                return False

            t3 = time.time()
            # public.print_log(f'0001 发送{receiveUsers} --{t3 - t1}s --{result}')

            # 记录
            if is_record:
                # 保存邮件到发件箱
                local_part, domain = self.mailUser.split('@')
                dir_path = '/www/vmail/{0}/{1}/.Sent/cur'.format(domain, local_part)
                if not os.path.isdir(dir_path):
                    os.makedirs(dir_path)
                file_name = public.GetRandomString(36)
                if file_name in [item.split(':')[0] for item in os.listdir(dir_path)]:
                    file_name = public.GetRandomString(54)
                public.writeFile(os.path.join(dir_path, file_name), msg.as_string())
                self.set_owner_and_group(os.path.join(dir_path, file_name), 'vmail', 'mail')


            # 不删除收件人 收件人会在邮件里一直累加
            del self.msg['To']
            del msg['To']
            del msg['Message-ID']
            return public.returnMsg(True, public.lang('Email sent successfully'))
        except:
            public.print_log(public.get_error_info())
            return public.returnMsg(False, public.lang('Failed to send mail, error reason[{0}]',str(e)))

    # def sendMail11(self, receiveUsers, domain, is_record, msgid=None): # todo xyz
    #     """
    #     发送邮件
    #     @param receiveUsers: 收件人列表
    #     @param domain: 域名
    #     @param is_record: 是否记录
    #     @param msgid: 消息ID
    #     @return: 发送结果
    #     """
    #     # 检查发送频率限制
    #     can_send, wait_time = self._check_rate_limit()
    #     if not can_send:
    #         return public.returnMsg(False, wait_time)
    #
    #     try:
    #         # 准备邮件
    #         if not msgid:
    #             msgid = make_msgid()
    #         msg = self.nwe_msg(msgid)
    #         msg['To'] = COMMASPACE.join(receiveUsers)
    #
    #         # 发送邮件
    #         try:
    #             result = self.mailServer.sendmail(
    #                 self.mailUser,
    #                 receiveUsers,
    #                 msg.as_string()
    #             )
    #         except:
    #             public.print_log(public.get_error_info())
    #             return False
    #
    #         # 记录发送的邮件
    #         if is_record:
    #             self._save_sent_mail(msg)
    #
    #         # 清理收件人信息
    #         del self.msg['To']
    #         del msg['To']
    #         del msg['Message-ID']
    #
    #         return public.returnMsg(True, '发送成功')
    #
    #     except Exception as e:
    #         public.print_log(f'发送失败: {str(e)}')
    #         return public.returnMsg(False, str(e))
        
    # def _save_sent_mail(self, msg): # todo xyz
    #     """保存邮件到发件箱"""
    #     try:
    #         local_part, domain = self.mailUser.split('@')
    #         dir_path = f'/www/vmail/{domain}/{local_part}/.Sent/cur'
    #         if not os.path.isdir(dir_path):
    #             os.makedirs(dir_path)
    #
    #         file_name = public.GetRandomString(36)
    #         if file_name in [item.split(':')[0] for item in os.listdir(dir_path)]:
    #             file_name = public.GetRandomString(54)
    #
    #         mail_path = os.path.join(dir_path, file_name)
    #         public.writeFile(mail_path, msg.as_string())
    #         self.set_owner_and_group(mail_path, 'vmail', 'mail')
    #     except:
    #         public.print_log(public.get_error_info())



    def parse_queue_id(self, receiveUsers):
        # receiveUsers = [receiveUsers]
        try:
            # 获取邮件队列信息
            output, err = public.ExecShell('mailq')

            pattern = re.compile(
                r'(?P<queue_id>\S+)\*?\s+\d+\s+\w{3}\s\w{3}\s+\d+\s+\d+:\d+:\d+\s+\S+\s*[\s\S]*?\n\s+' + re.escape(
                    receiveUsers[0]))
            # 搜索匹配的队列ID
            match = pattern.search(output)

            if match:
                # 提取匹配到的队列ID并去掉星号
                queue_id = match.group('queue_id').rstrip('*')

                return queue_id
            else:

                return None

        except Exception as e:
            public.print_log(public.get_error_info())
            return None


    def set_owner_and_group(self,path, user, group):
        '''
        检测目录所有者和组 并更改
        :param path: 目录或文件   user: 用户, group: 组
        :return:
        '''
        import os
        import pwd
        import grp
        try:
            # 获取当前文件或目录的所有者和组
            stat_info = os.stat(path)
            current_uid = stat_info.st_uid
            current_gid = stat_info.st_gid

            # 检查当前所有者和组是否为 vmail:mail
            vmail_uid = pwd.getpwnam(user).pw_uid
            mail_gid = grp.getgrnam(group).gr_gid
            if current_uid == vmail_uid and current_gid == mail_gid:
                return
            # 设置文件或目录的所有者和组
            os.chown(path, vmail_uid, mail_gid)
            # print(f"Ownership of {path} changed to {user}:{group}.")
        # except FileNotFoundError:
        #     print(f"Directory or file {path} not found.")
        # except Exception as e:
        #     print(f"Error occurred: {e}")
        except:
            pass

    def _get_pubilc_ip(self):

        try:
            # url = 'http://pv.sohu.com/cityjson?ie=utf-8'
            url = 'https://ifconfig.me/ip'
            opener = requests.get(url)
            m_str = opener.text
            ip_address = re.search(r'\d+.\d+.\d+.\d+', m_str).group(0)
            c_ip = public.check_ip(ip_address)
            if not c_ip:
                a, e = public.ExecShell("curl ifconfig.me")
                return a
            return ip_address
        except:
            filename = '/www/server/panel/data/iplist.txt'
            ip_address = public.readFile(filename).strip()
            if public.check_ip(ip_address):
                return ip_address
            else:
                return None

    def _get_all_ip(self):
        # import psutil
        public_ip = self._get_pubilc_ip()
        net_info = psutil.net_if_addrs()
        addr = []
        for i in net_info.values():
            addr.append(i[0].address)
        locataddr = public.readFile('/www/server/panel/data/iplist.txt')
        if not locataddr:
            locataddr = ""
        ip_address = locataddr.strip()
        if ip_address not in addr:
            addr.append(ip_address)
        if public_ip not in addr:
            addr.append(public_ip)
        return addr


    def _ipv6_to_ptr(self, ipv6_address):

        parts = ipv6_address.split(':')
        normalized_parts = [part.zfill(4) for part in parts]
        # 去掉冒号
        normalized_address = ''.join(normalized_parts)
        # 反转字符串
        reversed_address = normalized_address[::-1]
        # 加上点号
        ptr_address_parts = list(reversed_address)
        ptr_address = '.'.join(ptr_address_parts)
        ptr_address += '.ip6.arpa'
        # public.print_log("ptr_address  ^--{}".format(ptr_address))

        return ptr_address


class mail_sys_main:
    __setupPath = '/www/server/panel/plugin/mail_sys'
    _session_conf = __setupPath + '/session.json'
    _forward_conf = __setupPath + '/forward.json'
    _save_conf = __setupPath + '/save_day.json'
    postfix_main_cf = "/etc/postfix/main.cf"
    # 收件人黑名单
    postfix_recipient_blacklist = '/etc/postfix/blacklist'
    _check_time = 86400
    _check_time2 = 60
    # 退订用到的 域名/ip 端口
    unsubscribe_path = __setupPath + "/setinfo.json"
    # 全局每分钟发送频率限制
    send_limit_path = __setupPath + "/data/send_limit.txt"

    

    def __init__(self):
        # 数据库文件与名称
        self.db_files = {
            'postfixadmin': '/www/vmail/postfixadmin.db',
            'postfixmaillog': '/www/vmail/postfixmaillog.db',
            'mail_unsubscribe': '/www/vmail/mail_unsubscribe.db',
            'abnormal_recipient': '/www/vmail/abnormal_recipient.db',
            'auto_reply': '/www/vmail/auto_reply.db'
        }
        # self.sys_v = system.system().GetSystemVersion().replace(' ', '').lower()
        self.sys_v = public.get_linux_distribution().lower()
        self._session = self._get_session()
        self.in_bulk_path = '/www/server/panel/data/mail/in_bulk'
        self.blacklist_tips = '/www/server/panel/plugin/mail_sys/data/blacklist_tips'
        self.blacklist_alarm_switch = '/www/server/panel/plugin/mail_sys/data/blacklist_alarm_switch'
        self.abnormal_mail_check_switch = '/www/server/panel/plugin/mail_sys/data/abnormal_mail_check_switch'
        self.auto_reply_path = '/www/server/panel/data/mail/auto_reply'
        if not os.path.exists(self.in_bulk_path):
            os.makedirs(self.in_bulk_path)
        if not os.path.exists(self.auto_reply_path):
            os.makedirs(self.auto_reply_path)
        if not os.path.exists("{}/content".format(self.in_bulk_path)):
            os.mkdir("{}/content".format(self.in_bulk_path))

        # self.back_log_path = '/www/server/panel/data/mail/back_log'
        # if not os.path.exists(self.back_log_path):
        #     os.mkdir(self.back_log_path)

        # 检查域名表字段是否完整  日志表创建
        self.check_domain_column()

        # # 检查pflogsumm安装
        # self.is_pflogsumm = self.is_pflogsumm_installed()

        # 处理冗余的cron任务
        self.remove_old_cron()
        self.repair_broken_master_cf_simple()

        # self.task_cut_maillog()

        # # 初始化增加黑名单文件
        # if not os.path.exists(self.postfix_recipient_blacklist):
        #     public.writeFile(self.postfix_recipient_blacklist, '')
        #     # 生成db文件
        #     shell_str = 'postmap /etc/postfix/blacklist'
        #     public.ExecShell(shell_str)

        # 删除配置项(黑名单为空时)
        # self.check_black()

        self.maillog_path = '/var/log/maillog'
        if "ubuntu" in public.get_linux_distribution().lower():
            self.maillog_path = '/var/log/mail.log'

        # 给群发任务错误详情表增加唯一索引和时间字段
        self.update_task_count_table()
        # ---------------优化退订逻辑---------------
        # 黑名单列表同步到退订数据库  新安装的跳过
        self._sync_blacklist_to_unsubscribe_db()

        # Dovecot 新增配额插件 使邮箱配额生效
        self.check_dovecot_quota()


    # 旧task_count表 迁移数据 增加索引约束
    def update_task_count_table(self):
        path = '/www/server/panel/data/update_mail_task_count_table.pl'
        if os.path.exists(path):
            return

        if not os.path.exists('/www/vmail/postfixadmin.db'):
            public.writeFile(path, '')
            return

        # 旧数据数量
        with self.M("task_count") as obj:
            total = obj.count()

        if not total:  # 无数据跳过
            public.writeFile(path, '')
            return

        try:

            # 1. Create a new table with the unique constraint
            create_table_sql = '''
            CREATE TABLE IF NOT EXISTS `task_count_new` (
              `id` INTEGER PRIMARY KEY AUTOINCREMENT,
              `task_id` INTEGER NOT NULL,
              `recipient` varchar(320) NOT NULL,
              `delay` varchar(320) NOT NULL,
              `delays` varchar(320) NOT NULL,
              `dsn` varchar(320) NOT NULL,
              `relay` text NOT NULL,
              `domain` varchar(320) NOT NULL,
              `status` varchar(255) NOT NULL,
              `err_info` text NOT NULL,
              `created` INTEGER NOT NULL DEFAULT 0,
              UNIQUE (`task_id`, `recipient`)  -- 联合唯一约束
            );
            '''

            rename_table_sql1 = '''
            ALTER TABLE `task_count` RENAME TO `task_count_bak`;
            '''
            # 4. Rename the new table to the old table's name
            rename_table_sql2 = '''
            ALTER TABLE `task_count_new` RENAME TO `task_count`;
            '''

            # 创建新表
            with self.M("") as obj:
                obj.execute(create_table_sql)

            # 查旧数据
            with self.M("task_count") as obj:
                alldata = obj.field('task_id,recipient,delay,delays,dsn,relay,domain,status,err_info').select()

            # 复制到新表
            with public.S("task_count_new","/www/vmail/postfixadmin.db") as obj:
                aa = obj.insert_all(alldata, option='IGNORE')
                # public.print_log("更新数据表 task_count --{}".format(aa))
            # 改名
            with self.M("") as obj:
                # task_count 改名 task_count_bak
                obj.execute(rename_table_sql1)
                # task_count_new 改名 task_count
                obj.execute(rename_table_sql2)


           # error: You can only execute one statement at a time
            public.writeFile(path, '')
        except:
            public.print_log(public.get_error_info())



    def check_black(self):
        try:
            with open(self.postfix_recipient_blacklist, 'r') as file:
                emails = file.read().splitlines()
        except Exception as e:
            emails = []

        if not emails:
            # 黑名单为空 关闭
            st = self.recipient_blacklist_open(False)
            if st:
                public.ExecShell('systemctl reload postfix')


    def login_roundcube(self, args):
        '''
        一键登录 roundcube webmail
        :param args: rc_user账号  rc_pass密码
        :return: url
        '''
        if not hasattr(args, 'rc_user') or args.get('rc_user/s', "") == "":
            return public.returnMsg(False, public.lang('Parameter rc_user error'))
        if not hasattr(args, 'rc_pass') or args.get('rc_pass/s', "") == "":
            return public.returnMsg(False, public.lang('Parameter rc_pass error'))

        rc_user = args.rc_user
        rc_pass = args.rc_pass

        # 检查账户是否存在
        with self.M("mailbox") as obj:
            un = obj.where('username=?', rc_user).count()
        if un <= 0:
            return public.returnMsg(False, public.lang('User does not exist'))

        # data = self.M('mailbox').where('username=?', mail_from).field('password_encode,full_name').find()
        # password = self._decode(data['password_encode'])
        # 获取部署信息
        info = roundcube_main.get_roundcube_status()
        if not info['status']:
            return public.returnMsg(False, public.lang('Please install roundcube first'))

        site_name = info['site_name']
        token = public.GetRandomString(16)
        # 生成文件
        login_name = public.GetRandomString(5) + '.php'
        roundcube_path = '/www/wwwroot/' + site_name + '/'
        file = roundcube_path+login_name
        # 读取文件 并替换指定字符
        tmp_file = "/www/server/panel/plugin/mail_sys/roundcube_autologin.php"
        if not os.path.exists(tmp_file):
            return public.returnMsg(False, public.lang('Missing necessary documents'))
        data_info = public.readFile(tmp_file)
        # 替换关键词
        data_info = data_info.replace('__WEBMAIL_ROUNDCUBE_RANDOM_TOKEN__', token)
        data_info = data_info.replace('__WEBMAIL_ROUNDCUBE_USERNAME__', rc_user)
        data_info = data_info.replace('__WEBMAIL_ROUNDCUBE_PASSWORD__', rc_pass)
        data_info = data_info.replace('__WEBMAIL_ROUNDCUBE_LOGINPHP_PATH__', file)
        # 重新写入
        public.writeFile(file, data_info)
        url = "{}/{}?_aap_token={}".format(site_name,login_name, token)
        return url


    def check_dovecot_quota(self):
        """
        检查并更新Dovecot的配额配置
        为所有邮箱增加配额 maildirsize文件
        """
        # 判断同步标记
        path = '/www/server/panel/data/dovecot_quota_sync.pl'
        if os.path.exists(path):
            return

        if not os.path.exists('/www/vmail'):
            return
        # 检查dovecot是否安装
        if not os.path.exists('/etc/dovecot/dovecot.conf'):
            return

        # 重命名旧配置  /etc/dovecot/conf.d/20-pop3.conf    /etc/dovecot/conf.d/90-quota.conf
        if os.path.exists('/etc/dovecot/conf.d/20-pop3.conf'):
            os.rename('/etc/dovecot/conf.d/20-pop3.conf', '/etc/dovecot/conf.d/20-pop3.conf.old')
        if os.path.exists('/etc/dovecot/conf.d/90-quota.conf'):
            os.rename('/etc/dovecot/conf.d/90-quota.conf', '/etc/dovecot/conf.d/90-quota.conf.old')

        download_url = public.OfficialDownloadBase()
        logfile = '/tmp/mail_init.log'
        # 使用新配置替换旧配置
        download_conf_shell = '''
wget "{download_conf_url}/mail_sys/dovecot/dovecot-sql.conf.ext" -O /etc/dovecot/dovecot-sql.conf.ext -T 10 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/dovecot/90-quota.conf" -O /etc/dovecot/90-quota.conf -T 10 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/dovecot/20-lmtp.conf" -O /etc/dovecot/conf.d/20-lmtp.conf -T 10 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/dovecot/20-imap.conf" -O /etc/dovecot/conf.d/20-imap.conf -T 10 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/dovecot/20-pop3.conf" -O /etc/dovecot/conf.d/20-pop3.conf -T 10 >> {logfile} 2>&1
        '''.format(download_conf_url=download_url, logfile=logfile)
        public.ExecShell(download_conf_shell)

        # 下载失败 跳过本次同步
        if not os.path.exists('/etc/dovecot/conf.d/20-pop3.conf'):
            public.WriteLog('Mail Server', 'Dovecot configuration, download failed')

            # 使用旧配置
            if os.path.exists('/etc/dovecot/conf.d/20-pop3.conf.old'):
                os.rename('/etc/dovecot/conf.d/20-pop3.conf.old', '/etc/dovecot/conf.d/20-pop3.conf')
            if os.path.exists('/etc/dovecot/conf.d/90-quota.conf.old'):
                os.rename('/etc/dovecot/conf.d/90-quota.conf.old', '/etc/dovecot/conf.d/90-quota.conf')
            return

        # 检查/etc/dovecot/dovecot.conf 是否有mail_plugins = quota
        dovecot_conf_path = '/etc/dovecot/dovecot.conf'
        dovecot_conf = public.readFile(dovecot_conf_path)
        try:
            if dovecot_conf:
                # 检查是否有mail_plugins行
                if re.search(r'^\s*mail_plugins\s*=', dovecot_conf, re.MULTILINE):
                    # 如果有mail_plugins行但不包含quota，添加quota
                    if not re.search(r'^\s*mail_plugins\s*=.*quota', dovecot_conf, re.MULTILINE):
                        dovecot_conf = re.sub(r'(^\s*mail_plugins\s*=.*)', r'\1 quota', dovecot_conf,
                                              flags=re.MULTILINE)
                        public.writeFile(dovecot_conf_path, dovecot_conf)
                        public.WriteLog('Mail Server', 'Dovecot configuration, add the quota plugin to the mail_plugins')
                else:
                    # 如果没有mail_plugins行，在include行之前添加
                    include_pattern = r'(!include|!include_try)'
                    include_match = re.search(include_pattern, dovecot_conf, re.MULTILINE)

                    if include_match:
                        # 在第一个include行之前添加mail_plugins
                        insert_position = include_match.start()
                        new_conf = dovecot_conf[:insert_position] + "\nmail_plugins = quota\n\n" + dovecot_conf[
                                                                                                   insert_position:]
                        public.writeFile(dovecot_conf_path, new_conf)
                    else:
                        # 如果没有找到include行，添加到文件第一行
                        new_conf = "mail_plugins = quota\n\n" + dovecot_conf
                        public.writeFile(dovecot_conf_path, new_conf)

                    public.WriteLog('Mail Server', 'Dovecot configuration, add: mail_plugins = quota')

        except:
            public.print_log(public.get_error_info())
                    
        public.ExecShell('systemctl reload dovecot')
        # 所有邮箱增加配额maildirsize文件
        self.add_quota_maildirsize()

        # 标记同步完成
        public.writeFile(path, '')
        return

    def add_quota_maildirsize(self):
        """
        为所有邮箱增加配额maildirsize文件
        """
        with public.S('mailbox', '/www/vmail/postfixadmin.db') as obj_mailbox:
        # 获取全部邮箱
            mailbox_all = obj_mailbox.field('quota,local_part,domain,username,quota_active').select()
        if mailbox_all:
            for mailbox in mailbox_all:
                quota = mailbox['quota']
                local_part = mailbox['local_part']
                domain = mailbox['domain']
                username = mailbox['username']
                quota_active = mailbox['quota_active']
                # 在虚拟用户家目录创建对应邮箱的目录
                user_path = f'/www/vmail/{domain}/{local_part}'
                maildirsize_path = user_path + '/maildirsize'
                if quota_active:
                    maildirsize_content = f"{int(quota)}S\n0 0\n"
                else:
                    maildirsize_content = f"0S\n0 0\n"

                public.writeFile(maildirsize_path, maildirsize_content)
                # 设置文件权限  chown -R vmail:mail
                public.set_own(maildirsize_path, 'vmail', 'mail')
                # 重算配额    
                stdout, stderr = public.ExecShell(f'doveadm quota recalc -u {username}')
                # public.print_log(f'重算配额 {stdout} {stderr}')

        return True


    # 获取全部域名
    def get_domain_name(self, args):
        with self.M("domain") as obj, self.M("domain_user") as obj1:
            # 获取全部域名
            data_list = obj.order('created desc').field("domain").select()
            if not data_list:
                return []
            data_list = [i['domain'] for i in data_list]
            # 获取子面板域名
            domain_user_list = obj1.field('domain').select()
            user_domain_list = [item['domain'] for item in domain_user_list]
            # 隐藏子面板域名
            data_list = [domain for domain in data_list if domain not in user_domain_list]
        
        return data_list

    def get_domain_name_account(self,):
        """获取子面板域名"""
        with self.M("domain_user") as obj1:
            # 获取子面板域名
            domain_user_list = obj1.field('domain').select()
            user_domain_list = [i['domain'] for i in domain_user_list]

        return user_domain_list


    def get_domainip(self, args):
        '''
        查询域名和ip 用于安装 webmail
        :param args:
        :return:
        '''
        with self.M("domain") as obj:
            data_list = obj.field('domain,a_record').select()
        # data_list = self.M('domain').field('domain,a_record').select()
        public.print_log(data_list)
        all_list = []
        # 获取域名指向的ip
        for i in data_list:
            ip = self._session['{}:A'.format(i['a_record'])]['value']
            all_list.append(ip)
            all_list.append(i['domain'])
        domainip = list(set(all_list))
        return domainip

    #
    def _pflogsumm_data_treating(self, output, timezone=None):

        '''
         分析命令执行后的数据
        :param args: output  命令返回内容
        :param args: timezone 时区 默认为系统时区  为'utc'时 使用0时区 提交数据需要
        :return:  data  list
        '''

        
        
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk()._pflogsumm_data_treating(output, timezone)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return []


    # 判断安装 并安装
    def is_pflogsumm_installed(self):
        if os.path.exists('/usr/sbin/pflogsumm'):
            return True
        else:
            return False

    # 获取pflogsumm统计
    # pflogsumm /var/log/mail.log > mail_report.txt
    # pflogsumm -d yesterday /var/log/mail.log > mail_report.txt
    # pflogsumm -d today /var/log/mail.log > mail_report.txt
    def get_today_count(self, args):  # 增加历史记录  昨日 每天统计昨天的数据到数据库
        if not self.is_pflogsumm:
            errinfo = ""
            if not os.path.exists('/usr/sbin/pflogsumm'):
                if self.sys_v == 'centos7':
                    errinfo = 'yum install postfix-pflogsumm -y'
                elif self.sys_v == 'centos8':
                    errinfo = 'yum install postfix-pflogsumm -y'
                elif self.sys_v == 'ubuntu':
                    errinfo = 'apt install pflogsumm -y'

            return public.returnMsg(False, public.lang('Run [{}] to install pflogsumm first',errinfo))

        else:
            self.is_pflogsumm = True



        # 取缓存
        cache_key = 'mail_sys:get_today_count'
        cache = public.cache_get(cache_key)

        if cache:
            return cache

        output, err = public.ExecShell(
            f'pflogsumm -d today --verbose-msg-detail --zero-fill --iso-date-time --rej-add-from {self.maillog_path}')
        data = self._pflogsumm_data_treating(output)

        public.cache_set(cache_key, data, 30)
        # 更新昨日数据到数据库
        public.run_thread(self.get_yesterday_count)

        # 检查定时任务创建
        # self.task_cut_maillog()
        return data


    def get_monthly_quota_statistics(self, args):
        # 获取本月发件数与补充包信息 隐藏
        data = {
            "sent": 0,  # 当月发送
            "free_quota": 0,  # 当月额度
            "pack_use": 0,  # 补充包已使用
            "pack_total": 0,  # 补充包总额度
            "packages": [],  # 补充包
            "available": 0,  # 补充包可用
        }
        return data
        # try:
        #     
        #     
        #     SendMailBulk = bulk.SendMailBulk
        #
        #     m_sent= SendMailBulk()._get_month_senduse()
        #     pack= SendMailBulk()._get_user_pack_quota()
        #     free_quota= SendMailBulk()._get_user_free_quota()
        #
        #     data = {
        #         "sent": m_sent,  # 当月发送
        #         "free_quota": free_quota,  # 当月额度
        #         "pack_use": pack['used'],  # 补充包已使用
        #         "pack_total": pack['total'],  # 补充包总额度
        #         "packages": pack['packages'],
        #         "available": pack['available'],
        #     }
        # except:
        #     public.print_log(public.get_error_info())
        #
        # return data


    # 获取昨天的邮件统计 计入数据库并提交
    def get_yesterday_count(self):

        
        
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().get_yesterday_count()
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}



    # 获取本月发件数
    def get_month_senduse(self):
        # 接口缓存15s
        dnum = self.get_data_month_count(None)
        pnum = self.get_pflogsumm_month_count(None)
        # todo 获取提交数据 每天获取一次 缓存
        cnum = 0
        senduse = dnum if dnum >= pnum else pnum
        # 统计到本月发件小于线上  有问题
        if senduse < cnum:

            return cnum
        else:
            return senduse

    # 数据库 获取本月发件数
    def get_data_month_count(self, args):
        '''
         数据库 获取本月发件数
        :param args: int
        :return:
        '''

        
        
        SendMailBulk = bulk.SendMailBulk
        try:

            return SendMailBulk().get_data_month_count(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}

    # 命令 获取本月发件数
    def get_pflogsumm_month_count(self, args):
        '''
         命令 获取本月发件数
        :param args: int
        :return:
        '''

        
        
        SendMailBulk = bulk.SendMailBulk
        try:

            return SendMailBulk().get_pflogsumm_month_count(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}

    # 获取历史数据 -- 首页发件统计  传参  时间戳范围    一个详细列表 一个统计 暂未对接
    def get_data_month_list(self, args):
        # 		"received": 0,  //接收
        # 		"delivered": 0,  //发送
        # 		"forwarded": 0,  // 转发
        # 		"deferred": 5,   //延迟
        # 		"bounced": 3,   // 退回
        # 		"rejected": 0,  // 拒绝

        # 取缓存
        # cache_key = 'mail_sys:get_data_month_list'
        # cache = public.cache_get(cache_key)
        #
        # if cache:
        #     return cache


        # # 获取当前时间戳
        # timestamp_now = int(time.time())
        # strat = timestamp_now-86400*7
        # end = timestamp_now

        strat = int(args.strat)
        end = int(args.end)

        try:
            # 发送+退回+拒绝
            total_fields = "sum(received) as received, sum(delivered) as delivered, sum(deferred) as deferred, sum(bounced) as bounced, sum(rejected) as rejected, sum(delivered+bounced+rejected) as sentall"
            with self.M("log_analysis") as obj:
                query = obj.field(total_fields).where('time between ? and ?', (strat, end)).find()
                query2 = obj.where('time between ? and ?', (strat, end)).order('time desc').select()


            # sentall = query['sentall']

            # public.cache_set(cache_key, sentall, 15)
            data = {
                "hourly_stats": query2,
                "stats_dict": query,
            }
            return data
        except:
            public.print_log(public.get_error_info())

    def get_postconf(self):
        if os.path.exists("/usr/sbin/postconf"):
            return "/usr/sbin/postconf"
        elif os.path.exists("/sbin/postconf"):
            return "/sbin/postconf"
        else:
            return "postconf"

    def check_mail_sys(self, args):
        if os.path.exists('/etc/postfix/sqlite_virtual_domains_maps.cf'):
            # public.ExecShell('{} -e "message_size_limit = 102400000"'.format(self.get_postconf()))
            # 修改postfix mydestination配置项
            result = public.readFile(self.postfix_main_cf)
            if not result:
                return public.returnMsg(False, public.lang("No postfix configuration file found"))
            result = re.search(r"\n*mydestination\s*=(.+)", result)
            if not result:
                return public.returnMsg(False, public.lang("The postfix configuration file did not find the mydestination parameter"))
            result = result.group(1)
            if 'localhost' in result or '$myhostname' in result or '$mydomain' in result:
                public.ExecShell('{} -e "mydestination =" && systemctl restart postfix'.format(self.get_postconf()))
            # 修改dovecot配置
            dovecot_conf = public.readFile("/etc/dovecot/dovecot.conf")
            if not dovecot_conf or not re.search(r"\n*protocol\s*imap", dovecot_conf):
                return public.returnMsg(False, public.lang('Failed to configure dovecot'))
            # 修复之前版本未安装opendkim的问题
            # if not (os.path.exists("/usr/sbin/opendkim") and os.path.exists("/etc/opendkim.conf") and os.path.exists("/etc/opendkim")):
            #     if not self.setup_opendkim():
            #         return public.returnMsg(False, 'Failed to configure opendkim 1')

            return public.returnMsg(True, public.lang('MAIL SERVER EXIST'))
        else:
            return public.returnMsg(False, public.lang('NOT INSTALL MAIL SERVER'))

    def check_mail_env(self, args):
        return msi.mail_server_init().check_env()

    def change_to_rspamd(self, args):
        msi.change_to_rspamd().main()
        return public.returnMsg(True, public.lang("Setup successfully"))

    def install_rspamd(self, args):
        a, e = public.ExecShell("bash {}/install.sh rspamd".format(self.__setupPath))
        return public.returnMsg(True, public.lang("Install successfully"))

    # 安装并配置postfix, dovecot
    def setup_mail_sys(self, args):
        '''
        安装邮局系统主函数
        :param args:
        :return:
        '''
        res = msi.mail_server_init().setup_mail_sys(args)
        # 关闭黑名单
        self.check_black()
        # 安装时添加cut_maillog任务
        # self.task_cut_maillog()
        return res

    # 检测多个 SMTP 服务器的 25 端口是否可用
    def _check_smtp_port(self):
        import telnetlib

        host_list = ['mx1.qq.com', 'mx2.qq.com', 'mx3.qq.com', 'smtp.gmail.com']
        for host in host_list:
            try:
                tn = telnetlib.Telnet(host, 25, timeout=5)
                if tn: return True
            except:
                continue
        return False

    # 获取公网ip
    def _get_pubilc_ip(self):

        try:
            # url = 'http://pv.sohu.com/cityjson?ie=utf-8'
            url = 'https://ifconfig.me/ip'
            opener = requests.get(url)
            m_str = opener.text
            ip_address = re.search(r'\d+.\d+.\d+.\d+', m_str).group(0)
            c_ip = public.check_ip(ip_address)
            if not c_ip:
                a, e = public.ExecShell("curl ifconfig.me")
                return a
            return ip_address
        except:
            filename = '/www/server/panel/data/iplist.txt'
            ip_address = public.readFile(filename).strip()
            if public.check_ip(ip_address):
                return ip_address
            else:
                return None

    def _check_a(self, hostname):
        '''
        检测主机名是否有A记录
        :param hostname:
        :return:
        '''
        ipaddress = self._get_all_ip()
        if not ipaddress: return False
        key = '{0}:{1}'.format(hostname, 'A')
        now = int(time.time())
        value = ""
        error_ip = ""
        try:
            if key in self._session and self._session[key]["status"] != 0:
                v_time = now - int(self._session[key]["v_time"])
                if v_time < self._check_time:
                    value = self._session[key]["value"]
            if not value:
                # result = model.resolver.query(hostname, 'A')
                resolver = dns.resolver.Resolver()
                resolver.timeout = 1
                resolver.lifetime = 2
                try:
                    result = resolver.query(hostname, 'A')
                except:
                    result = resolver.resolve(hostname, 'A')
                for i in result.response.answer:
                    for j in i.items:
                        error_ip = j
                        if str(j).strip() in ipaddress:
                            value = str(j).strip()
            if value:
                self._session[key] = {
                    "status": 1,
                    "v_time": now,
                    "value": value
                }
                return True
            if str(type(error_ip)).find("dns.rdtypes.IN.A") != -1:
                self._session[key] = {
                    "status": 0,
                    "v_time": now,
                    "value": error_ip.to_text()
                }
            else:
                self._session[key] = {
                    "status": 0,
                    "v_time": now,
                    "value": error_ip
                }
            return False
        except:
            # public.print_log(public.get_error_info())
            self._session[key] = {"status": 0, "v_time": now, "value": value}
            return False

    def repair_postfix(self, args=None):
        if self.sys_v == 'centos7':
            msi.mail_server_init().install_postfix_on_centos7()
        elif self.sys_v == 'centos8':
            msi.mail_server_init().install_postfix_on_centos8()
        elif self.sys_v == 'ubuntu':
            msi.mail_server_init().install_postfix_on_ubuntu()
        return msi.mail_server_init().conf_postfix()

    def repair_dovecot(self, args=None):
        status = False
        if os.path.exists('/etc/dovecot/conf.d/10-ssl.conf'):
            if os.path.exists('/tmp/10-ssl.conf_aap_bak'):
                os.remove('/tmp/10-ssl.conf_aap_bak')
            shutil.move('/etc/dovecot/conf.d/10-ssl.conf', '/tmp/10-ssl.conf_aap_bak')
        if self.sys_v == 'centos7':
            if msi.mail_server_init().install_dovecot_on_centos7():
                status = True
        elif self.sys_v == 'centos8':
            msi.mail_server_init().install_postfix_on_centos8()
            status = True
        elif self.sys_v == 'ubuntu':
            msi.mail_server_init().install_dovecot_on_ubuntu()
            status = True
        if os.path.exists('/tmp/10-ssl.conf_aap_bak') and os.path.exists('/etc/dovecot/conf.d'):
            if os.path.exists("/etc/dovecot/conf.d/10-ssl.conf"):
                os.remove('/etc/dovecot/conf.d/10-ssl.conf')
            shutil.move('/tmp/10-ssl.conf_aap_bak', '/etc/dovecot/conf.d/10-ssl.conf')
        return public.returnMsg(status, "Repair {}!".format("Successfully" if status else "Fail"))

    # 修复服务配置文件不全的问题
    def repair_service_conf(self, args=None):
        service_name = args.service
        if service_name.lower() not in ['postfix', 'dovecot', 'rspamd']:
            return public.returnMsg(False, public.lang('Service name not exist'))
        if service_name == 'postfix':
            self.repair_postfix()
        elif service_name == 'dovecot':
            self.repair_dovecot()
        elif service_name == 'rspamd':
            msi.mail_server_init().setup_rspamd()
        return public.returnMsg(True, public.lang('Repair Complete'))

    # 获取服务状态
    def get_service_status(self, args=None):
        data = {}
        data['change_rspamd'] = True if "smtpd_milters = inet:127.0.0.1:11332" not in public.readFile(
            "/etc/postfix/main.cf") else False
        data['postfix'] = public.process_exists('master', '/usr/libexec/postfix/master')
        data['dovecot'] = public.process_exists('dovecot', '/usr/sbin/dovecot')
        data['rspamd'] = public.process_exists('rspamd', '/usr/bin/rspamd')
        data['opendkim'] = public.process_exists('opendkim', '/usr/sbin/opendkim')
        if "ubuntu" in self.sys_v:
            data['postfix'] = public.process_exists('master', '/usr/lib/postfix/sbin/master')

        # if "amazon" in self.sys_v:  # /usr/sbin/postfix  /usr/libexec/postfix/master
        if not data['postfix']:
            data['postfix'] = public.process_exists('master', '/usr/sbin/postfix') or public.process_exists('master', '/usr/lib/postfix/sbin/master') or public.process_exists('master', '/usr/libexec/postfix/master')

        data['recipient_blacklist'] = self._recipient_blacklist_status()
        data['alarm_black_switch'] = self._get_alarm_black_switch()
        data['abnormal_mail_check_switch'] = self._get_abnormal_mail_check_switch()
        # data['send_limit_minute'] = 150 if not os.path.exists(self.send_limit_path) else int(public.readFile(self.send_limit_path))  # todo xyz
        return data

    def get_mail_log(self, args):
        path = '/var/log/maillog'
        if "ubuntu" in self.sys_v:
            path = '/var/log/mail.log'
        if not os.path.exists(path): return {'log': 'Log file does not exist'}
        text = public.GetNumLines(path, 500)
        return {'log': text}
    # postfixadmin.db 初始默认数据库
    def M(self, table_name):
        import db
        sql = db.Sql()
        sql._Sql__DB_FILE = '/www/vmail/postfixadmin.db'
        sql._Sql__encrypt_keys = []
        return sql.table(table_name)
    # 合并重复代码块
    def MD(self, table_name, db_key):
        if db_key not in self.db_files:
            raise ValueError(f"Unknown database key: {db_key}")
        import db
        sql = db.Sql()
        sql._Sql__DB_FILE = self.db_files[db_key]
        sql._Sql__encrypt_keys = []
        return sql.table(table_name)



    def flush_domain_record(self, args):
        '''
        手动刷新域名记录
        domain all/specify.com
        :param args:
        :return:
        '''
        if args.domain == 'all':
            data_list = self.M('domain').order('created desc').field('domain,a_record,created,active').select()
            # cache_key_template = "{}_checkBlacklist"
            for item in data_list:
                # 兼容子面板
                if "domain_list" in args and item['domain'] not in args.domain_list:
                    # domain_list = args.domain_list.split(',')
                        continue
                try:
                    if os.path.exists("/usr/bin/rspamd"):
                        self.set_rspamd_dkim_key(item['domain'])
                    if os.path.exists("/usr/sbin/opendkim"):
                        self._gen_dkim_key(item['domain'])

                    # 清空当前域名的黑名单检测记录
                    # cache_key = cache_key_template.format(item['domain'])
                    # cache.delete(cache_key)
                except:
                    return public.returnMsg(False, public.lang('Please check if the rspamd service is running'))
                self._gevent_jobs(item['domain'], item['a_record'])
        else:
            try:
                if os.path.exists("/usr/bin/rspamd"):
                    self.set_rspamd_dkim_key(args.domain)
                if os.path.exists("/usr/sbin/opendkim"):
                    self._gen_dkim_key(args.domain)
            except:
                return public.returnMsg(False, public.lang('Please check if the rspamd service is running'))
            try:
                self._gevent_jobs(args.domain, None)  # 不需要验证A记录
            except:
                public.print_log('error:{}'.format(str(public.get_error_info())))
        try:
            public.writeFile(self._session_conf, json.dumps(self._session))
            return public.returnMsg(True, public.lang('Flush successfully'))

        except:
            # public.print_log('error:{}'.format(str(public.get_error_info())))
            return public.returnMsg(False, public.lang('Flush successfully'))

    def get_record_in_cache(self, item):
        try:
            item['mx_status'] = self._session['{0}:{1}'.format(item['domain'], 'MX')]["status"]
            item['spf_status'] = self._session['{0}:{1}'.format(item['domain'], 'TXT')]["status"]
            item['dkim_status'] = self._session['{0}:{1}'.format("default._domainkey." + item['domain'], 'TXT')][
                "status"]
            item['dmarc_status'] = self._session['{0}:{1}'.format("_dmarc." + item['domain'], 'TXT')]["status"]
            item['a_status'] = self._session['{0}:{1}'.format(item['a_record'], 'A')]["status"]
            if self._session['{0}:{1}'.format(item['domain'], 'PTR')]:
                item['ptr_status'] = self._session['{0}:{1}'.format(item['domain'], 'PTR')]["status"]
        except:
            self._gevent_jobs(item['domain'], item['a_record'])
            self.get_record_in_cache(item)
        return item

    def get_domains(self, args):
        '''
        域名查询接口
        :param args:
        :return:
        '''
        p = int(args.p) if 'p' in args else 1
        rows = int(args.size) if 'size' in args else 10
        callback = args.callback if 'callback' in args else ''
        account_id =int(args.account_id) if 'account_id' in args else 0  # 兼容子面板

        count = self.M('domain').count()
        # 0 退出
        if count == 0:
            return public.returnMsg(True, {'data': [], 'page': "<div><span class='Pcurrent'>1</span><span class='Pcount'>Total 0</span></div>"})

        # 获取分页数据
        page_data = public.get_page(count, p=p, rows=rows, callback=callback)

        data_list = self.M('domain').order('created desc').limit(page_data['shift'] + ',' + page_data['row']).select()

        if isinstance(data_list, str):
            return public.returnMsg(False, data_list)
        if not account_id:
            # 隐藏子面板域名
            domain_user_list = self.M('domain_user').field('domain').select()
            user_domain_list = [item['domain'] for item in domain_user_list]
            data_list = [item for item in data_list if item['domain'] not in user_domain_list]

        # 获取域名专属ip
        config = self._get_domainIP_conf()
        domain_ip = {}
        # 获取域名专属ip
        for domain, details in config.items():
            protocol = details['protocol']
            ip_address = details['ip']
        
            if domain not in domain_ip:
                domain_ip[domain] = {'ipv4': [], 'ipv6': []}
        
            if protocol == 'ipv4':
                domain_ip[domain]['ipv4'].append(ip_address)
            elif protocol == 'ipv6':
                domain_ip[domain]['ipv6'].append(ip_address)



        blcheck_count = f'/www/server/panel/plugin/mail_sys/data/blcheck.json'  # 统计各个域名黑名单情况

        if os.path.exists(blcheck_count):
            blcheck_ = public.readFile(blcheck_count)
            try:
                blcheck_ = json.loads(blcheck_)
            except:
                pass
        else:
            blcheck_ = {}

        # 获取roundcube配置
        roundcube_config = roundcube_main._get_roundcube_config()

        data_new =[]
        for item in data_list:
            # 兼容子面板
            if account_id>0 and self.M('domain_user').where('domain=? and account_id=?', (item['domain'], account_id)).count()==0:
                continue
            try:
                if os.path.exists("/usr/bin/rspamd"):
                    self.set_rspamd_dkim_key(item['domain'])
                if os.path.exists("/usr/sbin/opendkim"):
                    self._gen_dkim_key(item['domain'])
            except:
                public.print_log(public.get_error_info())
                return public.returnMsg(False, public.lang('Please check if the rspamd service is running'))
            if not os.path.exists(self._session_conf):
                self._gevent_jobs(item['domain'], item['a_record'])
                item = self.get_record_in_cache(item)
            else:
                item = self.get_record_in_cache(item)
            item['dkim_value'] = self._get_dkim_value(item['domain'])
            item['dmarc_value'] = 'v=DMARC1;p=quarantine;rua=mailto:admin@{0}'.format(item['domain'])
            item['mx_record'] = item['a_record']
            item['ssl_status'] = self._get_multiple_certificate_domain_status(item['domain'])
            item['catch_all'] = self._get_catchall_status(item['domain'])
            item['ssl_info'] = self.get_ssl_info(item['domain'])

            # CatchALL
            item['email'] = self._get_domain_forward(item['domain'])
            if domain_ip:
                # 发件ip
                item['ip_address'] = domain_ip[item['a_record']] if domain_ip.get(item['a_record'], None) else {"ipv4": [],"ipv6": []}
            else:
                item['ip_address'] = {"ipv4": [],"ipv6": []}

            # 新增域名黑名单检查
            item['domain_check_log'] = f"/www/server/panel/plugin/mail_sys/data/{item['a_record']}_blcheck.txt"
            item['domain_black_count'] = blcheck_.get(item['a_record'], {})
            # 新增roundcube配置
            item['roundcube_config'] = roundcube_config.get(item['domain'], False)
            # 增 证书hash 证书管理用
            item['ssl_hash'] = self.get_domain_ssl_hash(item['domain'])

            data_new.append(item)


        public.writeFile(self._session_conf, json.dumps(self._session))
        # 返回数据到前端
        return public.returnMsg(True, {'data': data_new, 'page': page_data['page']})

    def get_domain_ssl_hash(self, domain):
        """ 获取域名对应的证书hash信息"""
        try:
            from ssl_domainModelV2.model import DnsDomainSSL
            from ssl_domainModelV2.service import DomainValid
            for ssl in DnsDomainSSL.objects.all():
                if DomainValid.match_ssl_dns(domain, ssl, False):
                    return ssl.hash
            return ''
        except:
            public.print_log(public.get_error_info())
            return ''

    def _get_domain_forward(self, domain):
        address = '@' + domain.strip()
        result = self.M('alias').where('domain=? AND address=?', (domain, address)).getField('goto')
        if not result:
            return ''
        return result

    def _gevent_jobs(self, domain, a_record):
        from gevent import monkey
        monkey.patch_all()
        import gevent
        gevent.joinall([
            gevent.spawn(self._check_mx, domain),
            gevent.spawn(self._check_spf, domain),
            gevent.spawn(self._check_dkim, domain),
            gevent.spawn(self._check_dmarc, domain),
            gevent.spawn(self._check_a, a_record),
            # 新增ptr检查
            gevent.spawn(self._check_ptr, domain),
        ])
        return True

    def _build_dkim_sign_content(self, domain, dkim_path):
        dkim_signing_conf = """#{domain}_DKIM_BEGIN
  {domain} {{
    selectors [
     {{
       path: "{dkim_path}/default.private";
       selector: "default"
     }}
   ]
 }}
#{domain}_DKIM_END
""".format(domain=domain, dkim_path=dkim_path)
        return dkim_signing_conf

    def _dkim_sign(self, domain, dkim_sign_content):
        res = self.check_domain_in_rspamd_dkim_conf(domain)
        if not res:
            return False
        sign_domain = '#BT_DOMAIN_DKIM_BEGIN{}#BT_DOMAIN_DKIM_END'.format(
            res['sign_domain'].group(1) + dkim_sign_content)
        sign_conf = re.sub(res['rep'], sign_domain, res['sign_conf'])
        public.writeFile(res['sign_path'], sign_conf)
        return True

    def check_domain_in_rspamd_dkim_conf(self, domain):
        sign_path = '/etc/rspamd/local.d/dkim_signing.conf'
        sign_conf = public.readFile(sign_path)
        if not sign_conf:
            public.writeFile(sign_conf, "#BT_DOMAIN_DKIM_BEGIN\n#BT_DOMAIN_DKIM_END")
            sign_conf = """
domain {
#BT_DOMAIN_DKIM_BEGIN
#BT_DOMAIN_DKIM_END
}
            """
        rep = '#BT_DOMAIN_DKIM_BEGIN((.|\n)+)#BT_DOMAIN_DKIM_END'
        sign_domain = re.search(rep, sign_conf)
        if not sign_domain:
            return False
        if domain in sign_domain.group(1):
            return False
        return {"rep": rep, "sign_domain": sign_domain, 'sign_conf': sign_conf, 'sign_path': sign_path}

    def set_rspamd_dkim_key(self, domain):
        dkim_path = '/www/server/dkim/{}'.format(domain)
        if not dkim_path:
            os.makedirs(dkim_path)
        if not os.path.exists('{}/default.pub'.format(dkim_path)):
            dkim_shell = """
    mkdir -p {dkim_path}
    rspamadm dkim_keygen -s 'default' -b 1024 -d {domain} -k /www/server/dkim/{domain}/default.private > /www/server/dkim/{domain}/default.pub
    chmod 755 -R /www/server/dkim/{domain}
    """.format(dkim_path=dkim_path, domain=domain)
            public.ExecShell(dkim_shell)
        dkim_sign_content = self._build_dkim_sign_content(domain, dkim_path)
        if self._dkim_sign(domain, dkim_sign_content):
            public.ExecShell('systemctl reload rspamd')
        return True

    def _gen_dkim_key(self, domain):
        if not os.path.exists('/usr/share/perl5/vendor_perl/Getopt/Long.pm'):
            os.makedirs('/usr/share/perl5/vendor_perl/Getopt')
            public.ExecShell(
                'wget -O /usr/share/perl5/vendor_perl/Getopt/Long.pm {}/install/plugin/mail_sys/Long.pm -T 10'
                .format(public.get_url()))
        if not os.path.exists('/etc/opendkim/keys/{0}/default.private'.format(domain)):
            dkim_shell = '''
mkdir /etc/opendkim/keys/{domain}
opendkim-genkey -D /etc/opendkim/keys/{domain}/ -d {domain} -s default -b 1024
chown -R opendkim:opendkim /etc/opendkim/
systemctl restart  opendkim'''.format(domain=domain)
            keytable = "default._domainkey.{domain} {domain}:default:/etc/opendkim/keys/{domain}/default.private".format(
                domain=domain)
            sigingtable = "*@{domain} default._domainkey.{domain}".format(domain=domain)
            keytable_conf = public.readFile("/etc/opendkim/KeyTable")
            sigingtable_conf = public.readFile("/etc/opendkim/SigningTable")
            if keytable_conf:
                if keytable not in keytable_conf:
                    keytable_conf = keytable_conf + keytable + "\n"
                    public.writeFile("/etc/opendkim/KeyTable", keytable_conf)
            if sigingtable_conf:
                if sigingtable not in sigingtable_conf:
                    sigingtable_conf = sigingtable_conf + sigingtable + "\n"
                    public.writeFile("/etc/opendkim/SigningTable", sigingtable_conf)
            public.ExecShell(dkim_shell)

    def _get_dkim_value(self, domain):
        '''
        解析/etc/opendkim/keys/domain/default.txt得到域名要设置的dkim记录值
        :param domain:
        :return:
        '''
        if not os.path.exists("/www/server/dkim/{}".format(domain)):
            os.makedirs("/www/server/dkim/{}".format(domain))
        rspamd_pub_file = '/www/server/dkim/{}/default.pub'.format(domain)
        opendkim_pub_file = '/etc/opendkim/keys/{0}/default.txt'.format(domain)
        if os.path.exists(opendkim_pub_file) and not os.path.exists(rspamd_pub_file):
            opendkim_pub = public.readFile(opendkim_pub_file)
            public.writeFile(rspamd_pub_file, opendkim_pub)

            rspamd_pri_file = '/www/server/dkim/{}/default.private'.format(domain)
            opendkim_pri_file = '/etc/opendkim/keys/{}/default.private'.format(domain)
            opendkim_pri = public.readFile(opendkim_pri_file)
            public.writeFile(rspamd_pri_file, opendkim_pri)

        if not os.path.exists(rspamd_pub_file):
            return ''
        try:
            content = public.readFile(rspamd_pub_file)
            if not content.strip():  # 空文件处理
                os.remove(rspamd_pub_file)
                return ""

            # 提取关键值
            cleaned = content.replace(' ', '').replace('\n', '')
            parts = cleaned.split('"')

            if len(parts) < 4:
                raise ValueError("Invalid DKIM public key format")

            return parts[1] + parts[3]

        except Exception as e:
            # print(f"DKIM值解析失败: {e}")
            return ""


    def _get_session(self):
        session = public.readFile(self._session_conf)
        if session:
            session = json.loads(session)
        else:
            session = {}
        return session

    def _check_mx(self, domain):
        '''
        检测域名是否有mx记录
        :param domain:
        :return:
        '''
        a_record = self.M('domain').where('domain=?', domain).field('a_record').find()['a_record']
        key = '{0}:{1}'.format(domain, 'MX')
        now = int(time.time())
        try:
            value = ""
            if key in self._session and self._session[key]["status"] != 0:
                v_time = now - int(self._session[key]["v_time"])
                if v_time < self._check_time:
                    value = self._session[key]["value"]
            if '' == value:
                resolver = dns.resolver.Resolver()
                resolver.timeout = 1
                resolver.lifetime = 2
                try:
                    result = resolver.query(domain, 'MX')
                except:
                    result = resolver.resolve(domain, 'MX')
                value = str(result[0].exchange).strip('.')
            if not a_record:
                a_record = value
                self.M('domain').where('domain=?', domain).save('a_record', (a_record,))
            if value == a_record:
                self._session[key] = {"status": 1, "v_time": now, "value": value}
                return True
            self._session[key] = {"status": 0, "v_time": now, "value": value}
            return False
        except:
            # public.print_log(public.get_error_info())
            self._session[key] = {"status": 0, "v_time": now,
                                  "value": "None of DNS query names exist:{}".format(domain)}
            return False

    def _check_spf(self, domain):
        '''
        检测域名是否有spf记录
        :param domain:
        :return:
        '''
        key = '{0}:{1}'.format(domain, 'TXT')
        now = int(time.time())
        try:
            value = ""
            if key in self._session and self._session[key]["status"] != 0:
                v_time = now - int(self._session[key]["v_time"])
                if v_time < self._check_time:
                    value = self._session[key]["value"]
            if '' == value:
                resolver = dns.resolver.Resolver()
                resolver.timeout = 1
                resolver.lifetime = 2
                try:
                    result = resolver.query(domain, 'TXT')
                except:
                    result = resolver.resolve(domain, 'TXT')
                for i in result.response.answer:
                    for j in i.items:
                        value += str(j).strip()
            if 'v=spf1' in value.lower():
                self._session[key] = {"status": 1, "v_time": now, "value": value}
                return True
            self._session[key] = {"status": 0, "v_time": now, "value": value}
            return False
        except:
            # public.print_log(public.get_error_info())

            self._session[key] = {"status": 0, "v_time": now, "value": "None of DNS query spf exist:{}".format(domain)}
            return False

    def _check_dkim(self, domain):
        '''
        检测域名是否有dkim记录
        :param domain:
        :return:
        '''
        origin_domain = domain
        domain = 'default._domainkey.{0}'.format(domain)
        key = '{0}:{1}'.format(domain, 'TXT')
        now = int(time.time())
        try:
            value = ""
            if key in self._session and self._session[key]["status"] != 0:
                v_time = now - int(self._session[key]["v_time"])
                if v_time < self._check_time:
                    value = self._session[key]["value"]
            if '' == value:
                # result = model.resolver.query(domain, 'TXT')
                resolver = dns.resolver.Resolver()
                resolver.timeout = 1
                resolver.lifetime = 2
                try:
                    result = resolver.query(domain, 'TXT')
                except:
                    result = resolver.resolve(domain, 'TXT')
                for i in result.response.answer:
                    for j in i.items:
                        value += str(j).strip()
            new_v = self._get_dkim_value(origin_domain)
            if new_v and new_v in value:
                self._session[key] = {"status": 1, "v_time": now, "value": value}
                return True
            self._session[key] = {"status": 0, "v_time": now, "value": value}
            return False
        except:
            # public.print_log(public.get_error_info())
            self._session[key] = {"status": 0, "v_time": now,
                                  "value": "None of DNS query names exist:{}".format(domain)}
            return False

    def _check_dmarc(self, domain):
        '''
        检测域名是否有dmarc记录
        :param domain:
        :return:
        '''
        domain = '_dmarc.{0}'.format(domain)
        key = '{0}:{1}'.format(domain, 'TXT')
        now = int(time.time())
        try:
            value = ""
            if key in self._session and self._session[key]["status"] != 0:
                v_time = now - int(self._session[key]["v_time"])
                if v_time < self._check_time:
                    value = self._session[key]["value"]
            if '' == value:
                # result = model.resolver.query(domain, 'TXT')
                resolver = dns.resolver.Resolver()
                resolver.timeout = 1
                resolver.lifetime = 2
                try:
                    result = resolver.query(domain, 'TXT')
                except:
                    result = resolver.resolve(domain, 'TXT')
                for i in result.response.answer:
                    for j in i.items:
                        value += str(j).strip()
            if 'v=dmarc1' in value.lower():
                self._session[key] = {"status": 1, "v_time": now, "value": value}
                return True
            self._session[key] = {"status": 0, "v_time": now, "value": value}
            return False
        except:
            # public.print_log(public.get_error_info())
            self._session[key] = {"status": 0, "v_time": now,
                                  "value": "None of DNS query names exist:{}".format(domain)}
            return False

    def _query_ptr(self, reverse_domain):
        resolver = dns.resolver.Resolver()
        resolver.timeout = 1
        resolver.lifetime = 3
        try:
            result = resolver.query(reverse_domain, 'PTR')
            return [str(rdata.target).rstrip('.') for rdata in result]
        except dns.resolver.NXDOMAIN:
            return None
        except Exception as e:
            print(f"DNS query error: {e}")
            return None
    def _check_ptr(self, domain):
        """
        检测IP地址是否有PTR记录
        :param domain: 域名字符串
        :return: bool
        """
        # 后期改用户自己选择的ip去查询
        ip_addresses = [ip for ip in self._get_all_ip() if ip != '127.0.0.1']
        key = f'{domain}:PTR'
        now = int(time.time())

        # todo 临时注释
        # proprietaryIP = self._get_domainIP_conf().get(domain, {}).get('ip', None)
        # ip_addresses.append(proprietaryIP)
        # 去掉 None ip
        ip_addresses = [ip for ip in ip_addresses if ip]

        if key in self._session and self._session[key]["status"] != 0:
            v_time = now - int(self._session[key]["v_time"])
            if v_time < self._check_time2:
                return True

        found_ptr_record = False
        values = []
        ptr_addr = None

        for ip_address in ip_addresses:
            reverse_domain = (self._ipv6_to_ptr(ip_address) if ':' in ip_address else
                          '.'.join(reversed(ip_address.split('.'))) + '.in-addr.arpa')

            records = self._query_ptr(reverse_domain)
            if records:
                found_ptr_record = True
                ptr_addr = reverse_domain
                values.extend(records)

        if not found_ptr_record:
            self._session[key] = {"status": 0, "v_time": now,
                                  "value": f"None of DNS query PTR exist:{domain}", "key": ptr_addr, "values": []}
            return False

        for value in values:
            if value.lower().endswith(domain):
                self._session[key] = {"status": 1, "v_time": now, "value": value, "key": ptr_addr, "values": values}
                return True

        self._session[key] = {"status": 0, "v_time": now,"value": f"No matching PTR record:{values}", "key": ptr_addr, "values": values}
        return False


    def _ipv6_to_ptr(self, ipv6_address):
        parts = ipv6_address.split(':')
        normalized_parts = [part.zfill(4) for part in parts]
        # 去掉冒号
        normalized_address = ''.join(normalized_parts)
        # 反转字符串
        reversed_address = normalized_address[::-1]
        # 加上点号
        ptr_address_parts = list(reversed_address)
        ptr_address = '.'.join(ptr_address_parts)
        ptr_address += '.ip6.arpa'
        # public.print_log("ptr_address  ^--{}".format(ptr_address))

        return ptr_address

    def get_mx_txt_cache(self, args):
        session = self._get_session()
        if 'domain' not in args:
            return public.returnMsg(False, public.lang('DOMAIN NAME'))
        domain = args.domain

        mx_key = '{0}:{1}'.format(domain, 'MX')
        spf_key = '{0}:{1}'.format(domain, 'TXT')
        dkim_key = '{0}:{1}'.format('default._domainkey.{0}'.format(domain), 'TXT')
        dmarc_key = '{0}:{1}'.format('_dmarc.{0}'.format(domain), 'TXT')

        mx_value = session[mx_key] if mx_key in session else ''
        spf_value = session[spf_key] if spf_key in session else ''
        dkim_value = session[dkim_key] if dkim_key in session else ''
        dmarc_value = session[dmarc_key] if dmarc_key in session else ''

        return {'mx': mx_value, 'spf': spf_value, 'dkim': dkim_value, 'dmarc': dmarc_value}

    def delete_mx_txt_cache(self, args):
        session = self._get_session()
        if 'domain' not in args:
            return public.returnMsg(False, public.lang('DOMAIN NAME'))
        domain = args.domain

        mx_key = '{0}:{1}'.format(domain, 'MX')
        spf_key = '{0}:{1}'.format(domain, 'TXT')
        dkim_key = '{0}:{1}'.format('default._domainkey.{0}'.format(domain), 'TXT')
        dmarc_key = '{0}:{1}'.format('_dmarc.{0}'.format(domain), 'TXT')

        if mx_key in session: del (session[mx_key])
        if spf_key in session: del (session[spf_key])
        if dkim_key in session: del (session[dkim_key])
        if dmarc_key in session: del (session[dmarc_key])
        public.writeFile(self._session_conf, json.dumps(session))

        return public.returnMsg(True, public.lang('Refresh ({}) cached record successfully',domain))

    def add_domain(self, args):
        '''
        域名增加接口
        :param args:
        :return:
        '''
        if 'domain' not in args:
            return public.returnMsg(False, public.lang('DOMAIN NAME'))
        domain = args.domain
        a_record = args.a_record
        if not a_record.endswith(domain):
            return public.returnMsg(False, public.lang('A record [{}] does not belong to the domain name',a_record))
        if not self._check_a(a_record):
            return public.returnMsg(False, public.lang('A record parsing failed <br>Doamin: {}<br>IP: {}',a_record, self._session['{}:A'.format(a_record)]['value']))

        if self.M('domain').where('domain=?', domain).count() > 0:
            return public.returnMsg(False, public.lang('The domain name already exists'))

        cur_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            self.M('domain').add('domain,a_record,created', (domain, a_record, cur_time))
        except:
            return public.returnMsg(False, 'Mail server did not initialize successfully.<br>'
                                           'Please reopen the plugin to initialize,<br>'
                                           'If the server does not open <br>port 25 [outbound direction]<br>it cannot be initialized.<br> '
                                           'You can run:<br><br> [ telnet gmail-smtp-in.l.google.com 25 ] <br>in the terminal to check whether it is open.')


        if 'ips' in args:
            if args.ips == 'del':
                self.remove_domain(domain)
            else:
                args_addip = public.dict_obj()
                args_addip.ip = args.ips
                args_addip.domain = a_record # 发件ip
                self.add_domainIP_conf(args_addip)

        # 在虚拟用户家目录创建对应域名的目录
        if not os.path.exists('/www/vmail/{0}'.format(domain)):
            os.makedirs('/www/vmail/{0}'.format(domain))
        public.ExecShell('chown -R vmail:mail /www/vmail/{0}'.format(domain))
        # if len(errip) > 0:
        #     return public.returnMsg(True, public.lang('Add domain [{}] succeeded! ip err:{}', domain, errip))
        return public.returnMsg(True, public.lang('Add domain [{}] succeeded!',domain))

    def edit_domain_record(self, args):
        if 'domain' not in args:
            return public.returnMsg(False, public.lang('Please pass in the domain name'))
        domain = args.domain
        a_record = args.a_record
        if self.M('domain').where('domain=?', domain).count() == 0:
            return public.returnMsg(False, public.lang('The domain name does not exist'))
        self.M('domain').where('domain=?', domain).save('a_record', (a_record,))
        return public.returnMsg(True, public.lang('Modify the domain name [{0}] A record successfully!',domain))

    def delete_domain(self, args):
        '''
        域名删除接口
        :param args:
        :return:
        '''
        if 'domain' not in args:
            return public.returnMsg(False, public.lang('DOMAIN_NAME'))
        domain = args.domain

        # 删除域名记录
        domain_info = self.M('domain').where('domain=?', (domain,)).find()
        self.M('domain').where('domain=?', (domain,)).delete()
        public.WriteLog('Mail Server', f'Deleted mail domain [{domain}]')

        # 删除域名下的邮箱记录
        mailbox_count = self.M('mailbox').where('domain=?', (domain,)).count()
        self.M('mailbox').where('domain=?', (domain,)).delete()
        public.WriteLog('Mail Server', f'Deleted {mailbox_count} mailboxes under domain [{domain}]')

        self.delete_mx_txt_cache(args)

        # 删除caheAll
        self._deledte_catchall(domain)
        public.ExecShell('systemctl restart postfix')

        # 删除域名黑名单检测日志
        domain_check_log = f'/www/server/panel/plugin/mail_sys/data/{domain_info["a_record"]}_blcheck.txt'
        if os.path.exists(domain_check_log):
            os.remove(domain_check_log)

        # 在虚拟用户家目录删除对应域名的目录
        public.ExecShell('rm -rf /www/vmail/{0}'.format(domain))
        return public.returnMsg(True, public.lang('Deleting the domain successfully! ({})',domain))

    def create_mail_box(self, user, passwd):
        try:
            import imaplib
            conn = imaplib.IMAP4(port=143, host='127.0.0.1')
            conn.login(user, passwd)
            conn.logout()
            return True
        except:
            return False

    def get_mailboxs_total(self, args):
        '''
        邮箱用户查询接口  返回总数 total
        :param args:
        :return:
        '''
        p = int(args.p) if 'p' in args else 1
        rows = int(args.size) if 'size' in args else 12

        # 获取webmail配置
        webmail_config = roundcube_main._get_roundcube_config()
        domain_webmail_map = {}
        if webmail_config:
            for domain, config in webmail_config.items():
                # 根据ssl状态确定协议
                protocol = 'https://' if config.get('ssl_status', False) else 'http://'
                site_name = config.get('site_name', '')
                if site_name:
                    domain_webmail_map[domain] = {"url": f"{protocol}{site_name}", "ssl_status": config.get('ssl_status', False)}

        if "search" in args and args.search != "":
            where_str = "username LIKE ?"
            where_args = (f"%{args.search.strip()}%",)
        else:
            where_str = ""
            where_args = ()

        if 'domain' in args and args.domain != "":
            domain = args.domain
            if where_str and where_args:
                where_str = "domain=? AND username LIKE?"
                where_args = (domain, f"%{args.search.strip()}%")
            else:
                where_str = "domain=?"
                where_args = (domain,)



            with public.S('mailbox', '/www/vmail/postfixadmin.db') as obj_mailbox:
                # 获取总数
                count = obj_mailbox.where(where_str, where_args).count()
                # 获取当前页数据
                data_list = obj_mailbox.order('created', 'desc')\
                    .limit(rows, (p - 1) * rows)\
                    .where(where_str, where_args)\
                    .field('full_name,username,quota,created,modified,active,is_admin,password_encode,domain,current_usage,quota_active')\
                    .select()

            mx = self._check_mx_domain(domain)
            for i in data_list:
                i['password'] = self._decode(i['password_encode'])
                del i['password_encode']
                i['mx'] = mx
                i['webmail_url'] = domain_webmail_map.get(i['domain'], False)
            # 返回数据到前端
            return {'data': data_list, 'total': count}
        else:
            # 获取所有域名数据
            with public.S('mailbox', '/www/vmail/postfixadmin.db') as obj_mailbox:
                # 获取总数
                count = obj_mailbox.where(where_str, where_args).count()
                # 获取当前页数据
                data_list = obj_mailbox.order('created', 'desc')\
                    .limit(rows, (p - 1) * rows)\
                    .where(where_str, where_args)\
                    .field('full_name,username,quota,created,modified,active,is_admin,password_encode,domain,current_usage,quota_active')\
                    .select()
            # 获取所有域名的MX记录
            domains_mx = {}
            domains = self.get_domain_name(None)
            for i in domains:
                mx = self._check_mx_domain(i)
                domains_mx[i] = mx

            for i in data_list:
                try:
                    i['password'] = self._decode(i['password_encode'])
                    del i['password_encode']
                    # 获取mx记录
                    i['mx'] = domains_mx[i['domain']]
                    i['webmail_url'] = domain_webmail_map.get(i['domain'], False)
                except:
                    pass

            # 返回数据到前端
            return {'data': data_list, 'total': count}

    def get_mailboxs(self, args):
        '''
        邮箱用户查询接口  返回分页数据 后期停用
        :param args:
        :return:
        '''
        p = int(args.p) if 'p' in args else 1
        rows = int(args.size) if 'size' in args else 12
        callback = args.callback if 'callback' in args else ''
        if "search" in args and args.search != "":
            where_str = "username LIKE ?"
            where_args = (f"%{args.search.strip()}%",)
        else:
            where_str = ""
            where_args = ()
        if 'domain' in args and args.domain != "":
            domain = args.domain
            if where_str and where_args:
                where_str = "domain=? AND username LIKE?"
                where_args = (domain, f"%{args.search.strip()}%")
            else:
                where_str = "domain=?"
                where_args = (domain,)
            with self.M('mailbox') as obj_mailbox:
                count = obj_mailbox.where(where_str, where_args).count()
            # 获取分页数据
            page_data = public.get_page(count, p, rows, callback)
            # 获取当前页的数据列表
            with self.M('mailbox') as obj_mailbox:
                data_list = obj_mailbox.order('created desc').limit(
                    page_data['shift'] + ',' + page_data['row']).where(where_str, where_args).field(
                    'full_name,username,quota,created,modified,active,is_admin,password_encode,domain'
                ).select()
            mx = self._check_mx_domain(domain)
            for i in data_list:
                i['password'] = self._decode(i['password_encode'])
                del i['password_encode']
                i['mx'] = mx
            # 返回数据到前端
            return {'data': data_list, 'page': page_data['page']}
        else:
            with self.M('mailbox') as obj_mailbox:
                count = obj_mailbox.where(where_str, where_args).count()
            # 获取分页数据
            page_data = public.get_page(count, p, rows, callback)
            # 获取域名  以及域名对应mx记录
            domains_mx = {}
            domains = self.get_domain_name(None)
            for i in domains:
                mx = self._check_mx_domain(i)
                domains_mx[i] = mx
            # 获取当前页的数据列表
            with self.M('mailbox') as obj_mailbox:
                data_list = obj_mailbox.order('created desc').limit(
                    page_data['shift'] + ',' + page_data['row']).field(
                    'full_name,username,quota,created,modified,active,is_admin,password_encode,domain'
                ).where(where_str, where_args).select()
            for i in data_list:
                try:
                    i['password'] = self._decode(i['password_encode'])
                    del i['password_encode']
                    # 获取mx记录
                    i['mx'] = domains_mx[i['domain']]
                except:
                    pass

            # 返回数据到前端
            return {'data': data_list, 'page': page_data['page']}
        

    def _check_mx_domain(self, domain):
        '''
        查询域名的mx
        :param args:
        :return:
        '''
        key = '{0}:{1}'.format(domain, 'MX')
        session = public.readFile('/www/server/panel/plugin/mail_sys/session.json')
        if session:
            session = json.loads(session)
        else:
            return ''
        if session.get(key, ''):
            if session[key]['status']:
                mx = session[key]['value']
                return mx
        return ''
    def get_all_user(self, args):
        if 'domain' in args:
            data_list = self.M('mailbox').where('domain=? AND active=?', (args.domain, 1)).field(
                'full_name,username,quota,created,modified,active,is_admin,domain').select()
        else:
            data_list = self.M('mailbox').where('active=?', 1).field(
                'full_name,username,quota,created,modified,active,is_admin,domain').select()
        return data_list

    # 加密数据
    def _encode(self, data):
        str2 = data.strip()
        if sys.version_info[0] == 2:
            b64_data = base64.b64encode(str2)
        else:
            b64_data = base64.b64encode(str2.encode('utf-8'))
        return binascii.hexlify(b64_data).decode()

    # 解密数据
    def _decode(self, data):
        b64_data = binascii.unhexlify(data.strip())
        return base64.b64decode(b64_data).decode()

    # 检测密码强度
    def _check_passwd(self, password):
        return True if re.search(r"^(?=.*\d)(?=.*[a-z])(?=.*[A-Z]).*$", password) and len(password) >= 8 else False

    def _check_email_address(self, email_address):
        return True if re.match(r"^\w+([.-]?\w+)*@.*", email_address) else False

    # 生成MD5-CRYPT模式加密的密码
    def _generate_crypt_passwd(self, password):
        if sys.version_info[0] == 2:
            shell_str = 'doveadm pw -s MD5-CRYPT -p {0}'.format(password)
            return public.ExecShell(shell_str)[0][11:].strip()
        else:
            import crypt
            return crypt.crypt(password, crypt.mksalt(crypt.METHOD_MD5))

    # 批量创建邮箱
    def __create_mail_box_mulitiple(self, info, args):
        create_successfully = {}
        create_failed = {}
        # status = False
        for data in info:
            if not data:
                continue
            try:
                args.quota = '{} {}'.format(data['quota'], data['unit'])
                args.username = data['username']
                args.password = data['password']
                args.full_name = data['full_name']
                args.is_admin = 0
                result = self.add_mailbox(args)
                if result['status']:
                    create_successfully[data['username']] = result['msg']
                    continue
                # create_successfully[data['username']] = create_other
                create_failed[data['username']] = result['msg']
            except:
                create_failed[data['username']] = "create error"
        # if not create_failed:
        #     status = True
        return {'status': True, 'msg': "Create the mailbox [ {} ] successfully".format(','.join(create_successfully)),
                'error': create_failed,
                'success': create_successfully}

    # 批量创建邮箱
    def add_mailbox_multiple(self, args):
        '''
            @name 批量创建网站
            @author zhwen<2020-11-26>
            @param create_type txt  txt格式为 "Name|Address|Password|MailBox space|GB" 每个网站一行
                                                 "support|support|Password|5|GB"
            @param content     "["support|support|Password|5|GB"]"
        '''
        key = ['full_name', 'username', 'password', 'quota', 'unit']
        info = [dict(zip(key, i)) for i in
                [i.strip().split('|') for i in json.loads(args.content)]]
        if not info:
            return public.returnMsg(False,
                                    public.lang('The param is empty, Insufficient password strength (need to include uppercase and lowercase letters and numbers and no less than 8 in length)'))
        res = self.__create_mail_box_mulitiple(info, args)
        # # 批量创建完毕后
        # os.system('chown -R vmail:mail /www/vmail')
        return res

    def add_mailbox(self, args):
        '''
        新增邮箱用户
        :param args:
        :return:
        '''
        if 'username' not in args:
            return public.returnMsg(False, public.lang('ENTER ACCOUNT NAME'))
        if not self._check_passwd(args.password):
            return public.returnMsg(False,
                                    public.lang('Insufficient password strength (need to include uppercase and lowercase letters and numbers and no less than 8 in length)'))
        username = args.username
        # if not self._check_email_address(username):
        #     return public.returnMsg(False, public.lang('Email address format is incorrect'))
        if not username.islower():
            return public.returnMsg(False, public.lang('Email address cannot have uppercase letters!'))
        is_admin = args.is_admin if 'is_admin' in args else 0

        active = 1
        if 'active' in args and args.active == "0":
            active = 0
        local_part, domain = username.split('@')
        # 检查邮箱数量  查看数量限制
        with self.M('mailbox') as obj_mailbox:
            user_count = obj_mailbox.where('domain=?', (domain,)).count()
            count = obj_mailbox.where('username=?', (username,)).count()


        if count > 0:
            return public.returnMsg(False, public.lang('The email account already exists'))

        with self.M('domain') as obj_domain:
            domaincount = obj_domain.where('domain=?', (domain,)).getField("mailboxes")

        if user_count + 1 > domaincount:
            return public.returnMsg(False, public.lang('The number of mailboxes for {} has reached the {} limit',domain, domaincount))

        password_encrypt = self._generate_crypt_passwd(args.password)
        password_encode = self._encode(args.password)

        # domain_list = self.get_domain_name(None)
        # if domain not in domain_list:
        #     return public.returnMsg(False, public.lang('The domain name is not in the MailServer1 {}',domain))
        num, unit = args.quota.split()
        if unit == 'GB':
            quota = float(num) * 1024 * 1024 * 1024
        else:
            quota = float(num) * 1024 * 1024


        cur_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        is_insert = True
        while is_insert:
            try:
                with self.M('mailbox') as obj_mailbox:
                    res = obj_mailbox.add(
                        'full_name,is_admin,username,password,password_encode,maildir,quota,local_part,domain,created,modified,active',
                        (args.full_name, is_admin, username, password_encrypt, password_encode, args.username + '/', quota,
                         local_part, domain, cur_time, cur_time, active))
                if isinstance(res, str):
                    if 'error' in res:
                        # public.print_log("添加失败--{}".format(res))
                        continue

                is_insert = False
                # public.print_log("添加邮箱--{}".format(args.full_name))
            except:
                time.sleep(0.01)
                continue

        # 在虚拟用户家目录创建对应邮箱的目录
        user_path = '/www/vmail/{0}/{1}'.format(domain, local_part)
        os.makedirs(user_path)
        os.makedirs(user_path + '/tmp')
        os.makedirs(user_path + '/new')
        os.makedirs(user_path + '/cur')
        # 增加限额文件 maildirsize  限额 quota    第一行 [存储空间配额]S,[消息数量配额]C
        maildirsize_path = user_path + '/maildirsize'
        maildirsize_content = f"{int(quota)}S\n0 0\n"
        public.writeFile(maildirsize_path, maildirsize_content)

        # 增加发送目录
        dir_path = '/www/vmail/{0}/{1}/.Sent/cur'.format(domain, local_part)
        if not os.path.isdir(dir_path):
            os.makedirs(dir_path)

        # os.system('chown -R vmail:mail /www/vmail/{0}/{1}'.format(domain, local_part))

        public.recursive_set_own(user_path, 'vmail', 'mail')

        # 检查登录效果 暂未处理
        # self.create_mail_box(username, args.password)

        return public.returnMsg(True, public.lang("Add a mailbox user successfully {}",username))


    def add_mailbox_v2(self, args):
        '''
        新增邮箱用户--增加配额开关
        :param args:
        :return:
        '''
        if 'username' not in args:
            return public.returnMsg(False, public.lang('ENTER ACCOUNT NAME'))
        if not self._check_passwd(args.password):
            return public.returnMsg(False,public.lang('Insufficient password strength'))
        username = args.username
        # if not self._check_email_address(username):
        #     return public.returnMsg(False, public.lang('Email address format is incorrect'))
        if not username.islower():
            return public.returnMsg(False, public.lang('Email address cannot have uppercase letters!'))
        is_admin = args.is_admin if 'is_admin' in args else 0

        active = 1
        if 'active' in args and args.active == "0":
            active = 0
        quota_active = 1  # 默认开启配额
        if 'quota_active' in args:
            quota_active = 1 if int(args.get('quota_active', 1)) else 0
        local_part, domain = username.split('@')
        # 检查邮箱数量  查看数量限制
        with self.M('mailbox') as obj_mailbox:
            user_count = obj_mailbox.where('domain=?', (domain,)).count()
            count = obj_mailbox.where('username=?', (username,)).count()

        if count > 0:
            return public.returnMsg(False, public.lang('The email account already exists'))

        with self.M('domain') as obj_domain:
            domaincount = obj_domain.where('domain=?', (domain,)).getField("mailboxes")

        if user_count + 1 > domaincount:
            return public.returnMsg(False, public.lang('The number of mailboxes for {} has reached the {} limit',domain, domaincount))

        password_encrypt = self._generate_crypt_passwd(args.password)
        password_encode = self._encode(args.password)

        domain_list = self.get_domain_name(None)
        if domain not in domain_list:
            return public.returnMsg(False, public.lang('The domain name is not in the MailServer1 {}',domain))
        num, unit = args.quota.split()
        if unit == 'GB':
            quota = float(num) * 1024 * 1024 * 1024
        else:
            quota = float(num) * 1024 * 1024


        cur_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with self.M('mailbox') as obj_mailbox:
            res = obj_mailbox.add(
                'full_name,is_admin,username,password,password_encode,maildir,quota,local_part,domain,created,modified,active,quota_active',
                (args.full_name, is_admin, username, password_encrypt, password_encode, args.username + '/', quota,
                 local_part, domain, cur_time, cur_time, active,quota_active))

        # 在虚拟用户家目录创建对应邮箱的目录
        user_path = '/www/vmail/{0}/{1}'.format(domain, local_part)
        os.makedirs(user_path)
        os.makedirs(user_path + '/tmp')
        os.makedirs(user_path + '/new')
        os.makedirs(user_path + '/cur')
        # 增加限额文件 maildirsize  限额 quota    第一行 [存储空间配额]S,[消息数量配额]C
        maildirsize_path = user_path + '/maildirsize'
        if quota_active:
            maildirsize_content = f"{int(quota)}S\n0 0\n"
        else:
            maildirsize_content = f"0S\n0 0\n"
        public.writeFile(maildirsize_path, maildirsize_content)

        # 增加发送目录
        dir_path = '/www/vmail/{0}/{1}/.Sent/cur'.format(domain, local_part)
        if not os.path.isdir(dir_path):
            os.makedirs(dir_path)
        public.recursive_set_own(user_path, 'vmail', 'mail')

        # 检查登录效果 暂未处理
        # self.create_mail_box(username, args.password)

        return public.returnMsg(True, public.lang("Add a mailbox user successfully {}",username))

    def create_email_batch_random(self,args):
        """ 批量创建用户  随机创建  """
        # 随机用户名  maxnum 20  quota_active = 1 # 默认开启配额
        # 创建数量
        maxnum = int(args.get('maxnum', 10))
        # 默认密码
        password = args.password
        # 域名
        domain = args.domain
        quota_active = 1 if int(args.get('quota_active', 1)) else 0


        # 基础字符串 不允许特殊字符
        random_str = args.get('random_str', '')
        if random_str == '':
            random_str = public.GetRandomString(5)

        # 通用大小
        quota = args.get('quota', '5 GB')

        is_admin = 0  # 普通用户
        active = 1  # 活跃账号

        # 判断域名
        domain_list = self.get_domain_name(None)
        if domain not in domain_list:
            return public.returnMsg(False, public.lang('The domain name is not in the MailServer {}',domain))

        # 用户名   域名
        # local_part, domain = username.split('@')
        # 检查邮箱数量  查看数量限制
        with self.M('mailbox') as obj_mailbox:
            user_count = obj_mailbox.where('domain=?', (domain,)).count()
            # count = obj_mailbox.where('username=?', (username,)).count()

        with self.M('domain') as obj_domain:
            domaincount = obj_domain.where('domain=?', (domain,)).getField("mailboxes")

        if user_count + maxnum > domaincount:
            max = domaincount-user_count
            return public.returnMsg(False, public.lang('The number of mailboxes for {} has reached the {} , at most {} ',domain, domaincount,max))

        # 密码
        password_encrypt = self._generate_crypt_passwd(password)
        password_encode = self._encode(password)

        # 配额
        num, unit = quota.split()
        if unit == 'GB':
            quota = float(num) * 1024 * 1024 * 1024
        else:
            quota = float(num) * 1024 * 1024

        cur_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        insert_data = []
        # 生成20个邮箱名
        for i in range(maxnum):
            random = public.GetRandomString(3)
            full_name = (random_str + '_' + str(i) + '_' + random).lower()  # 用户名必须小写
            # is_admin = is_admin
            username = full_name + '@' + domain
            password = password_encrypt
            password_encode = password_encode
            maildir = username + '/'
            # quota = quota
            local_part = full_name
            # domain = domain
            created = cur_time
            modified = cur_time
            # active = active
            data = {
                "full_name":full_name,
                "is_admin":is_admin,
                "username":username,
                "password":password,
                "password_encode":password_encode,
                "maildir":maildir,
                "quota":quota,
                "local_part":local_part,
                "domain":domain,
                "created":created,
                "modified":modified,
                "active":active,
                "quota_active":quota_active,
            }
            insert_data.append(data)
        try:
            with public.S("mailbox", '/www/vmail/postfixadmin.db') as obj:
                add_num = obj.insert_all(insert_data, option='IGNORE')
        except:
            public.print_log(public.get_error_info())

        for i in insert_data:
            local_part = i['local_part']
            user_path = '/www/vmail/{0}/{1}'.format(domain, local_part)
            if not os.path.exists(user_path):
                os.makedirs(user_path)
                os.makedirs(user_path + '/tmp')
                os.makedirs(user_path + '/new')
                os.makedirs(user_path + '/cur')
                maildirsize_path = user_path + '/maildirsize'
                if quota_active:
                    maildirsize_content = f"{int(quota)}S\n0 0\n"
                else:
                    maildirsize_content = f"0S\n0 0\n"

                public.writeFile(maildirsize_path, maildirsize_content)
                # 增加发送目录
                dir_path = '/www/vmail/{0}/{1}/.Sent/cur'.format(domain, local_part)
                if not os.path.isdir(dir_path):
                    os.makedirs(dir_path)
                
                # os.system('chown -R vmail:mail /www/vmail/{0}/{1}'.format(domain, local_part))

                public.recursive_set_own(user_path, 'vmail', 'mail')

                # aa = self.create_mail_box(i['username'], args.password)
                #
                # public.print_log(f"  {i['username']}  结果{aa}")
                # time.sleep(0.1)


        return public.returnMsg(True, public.lang('{} mailboxes were successfully created', add_num))

    def update_mailbox_v2(self, args):
        '''
        邮箱用户修改接口 --增加配额开关修改
        :param args:
        :return:
        '''

        quota_active = 1
        if 'quota_active' in args and args.quota_active != '':
            quota_active = 1 if int(args.get('quota_active', 1)) else 0

        num, unit = args.quota.split()
        if unit == 'GB':
            quota = float(num) * 1024 * 1024 * 1024
        else:
            quota = float(num) * 1024 * 1024
        cur_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if 'password' in args and args.password != '':
            if not self._check_passwd(args.password):
                return public.returnMsg(False, public.lang('Insufficient password strength'))

            password_encrypt = self._generate_crypt_passwd(args.password)
            password_encode = self._encode(args.password)
            self.M('mailbox').where('username=?', args.username).save(
                'password,password_encode,full_name,quota,modified,active,is_admin,quota_active',
                (password_encrypt, password_encode, args.full_name, quota, cur_time, args.active, args.is_admin,quota_active))
            public.WriteLog('Mail Server', f'Modify email[{args.username}] --password')
        else:
            self.M('mailbox').where('username=?', args.username).save('full_name,quota,modified,active,is_admin,quota_active', (
                args.full_name, quota, cur_time, args.active, args.is_admin,quota_active))

        # 修改邮箱对应限额 quota
        try:
            # 获取用户信息
            mailbox_info = self.M('mailbox').where('username=?', args.username).find()
            if mailbox_info:
                local_part = mailbox_info.get('local_part')
                domain = mailbox_info.get('domain')

                # 构建邮箱路径
                maildir_path = os.path.join('/www/vmail', domain, local_part)
                maildirsize_path = os.path.join(maildir_path, 'maildirsize')

                if os.path.exists(maildir_path):
                    # 尝试更新maildirsize文件
                    if os.path.exists(maildirsize_path):
                        # 读取当前maildirsize文件内容
                        with open(maildirsize_path, 'r') as f:
                            lines = f.readlines()

                        if lines and len(lines) > 0:
                            # 替换第一行的配额信息
                            if quota_active:
                                lines[0] = f"{int(quota)}S\n"
                            else:
                                lines[0] = f"0S\n"

                            # 写回文件
                            with open(maildirsize_path, 'w') as f:
                                f.writelines(lines)

                            # 设置正确的权限
                            public.ExecShell(f"chown vmail:mail {maildirsize_path}")
                            public.WriteLog('Mail Server', f'The quota file for mailbox [{args.username}] was updated successfully')
                    else:
                        # 如果文件不存在，使用doveadm重新计算
                        public.ExecShell(f'doveadm quota recalc -u {args.username}')
                        public.WriteLog('Mail Server', f'Recalculate the quota for [{args.username}]')
        except Exception as e:
            public.WriteLog('Mail Server', f'Failed to update mailbox quota file: {str(e)}')

        return public.returnMsg(True, public.lang("Modify the mailbox user success {}",args.username, ))
    def update_mailbox(self, args):
        '''
        邮箱用户修改接口
        :param args:
        :return:
        '''
        num, unit = args.quota.split()
        if unit == 'GB':
            quota = float(num) * 1024 * 1024 * 1024
        else:
            quota = float(num) * 1024 * 1024
        cur_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if 'password' in args and args.password != '':
            if not self._check_passwd(args.password):
                return public.returnMsg(False,
                                        public.lang('Insufficient password strength (need to include uppercase and lowercase letters and numbers and no less than 8 in length)'))
            # shell_str = 'doveadm pw -s MD5-CRYPT -p {0}'.format(args.password)
            # password_encrypt = public.ExecShell(shell_str)[0][11:].strip()
            password_encrypt = self._generate_crypt_passwd(args.password)
            password_encode = self._encode(args.password)
            self.M('mailbox').where('username=?', args.username).save(
                'password,password_encode,full_name,quota,modified,active,is_admin',
                (password_encrypt, password_encode, args.full_name, quota, cur_time, args.active, args.is_admin))
        else:
            self.M('mailbox').where('username=?', args.username).save('full_name,quota,modified,active,is_admin', (
                args.full_name, quota, cur_time, args.active, args.is_admin))

        # 修改邮箱对应限额 quota
        try:
            # 获取用户信息
            mailbox_info = self.M('mailbox').where('username=?', args.username).find()
            if mailbox_info:
                local_part = mailbox_info.get('local_part')
                domain = mailbox_info.get('domain')

                # 构建邮箱路径
                maildir_path = os.path.join('/www/vmail', domain, local_part)
                maildirsize_path = os.path.join(maildir_path, 'maildirsize')

                if os.path.exists(maildir_path):
                    # 尝试更新maildirsize文件
                    if os.path.exists(maildirsize_path):
                        # 读取当前maildirsize文件内容
                        with open(maildirsize_path, 'r') as f:
                            lines = f.readlines()

                        if lines and len(lines) > 0:
                            # 替换第一行的配额信息
                            lines[0] = f"{int(quota)}S\n"

                            # 写回文件
                            with open(maildirsize_path, 'w') as f:
                                f.writelines(lines)

                            # 设置正确的权限
                            public.ExecShell(f"chown vmail:mail {maildirsize_path}")
                            public.WriteLog('Mail Server', f'The quota file for mailbox [{args.username}] was updated successfully')
                    else:
                        # 如果文件不存在，使用doveadm重新计算
                        public.ExecShell(f'doveadm quota recalc -u {args.username}')
                        public.WriteLog('Mail Server', f'Recalculate the quota for [{args.username}]')
        except Exception as e:
            public.WriteLog('Mail Server', f'Failed to update mailbox quota file: {str(e)}')

        return public.returnMsg(True, public.lang("Modify the mailbox user success {}",args.username, ))

    def delete_mailbox(self, args):
        '''
        删除邮箱用户
        :param args:
        :return:
        '''
        if 'username' not in args:
            return public.returnMsg(False, public.lang('ENTER ACCOUNT NAME'))
        username = args.username.strip()
        if '@' not in username or username.count('@') != 1:
            return public.returnMsg(False, "Invalid email format")
        local_part, domain = username.split('@')
        for part in [local_part, domain]:
            if not part or '..' in part or '/' in part or '\\' in part or part.startswith('.'):
                return public.returnMsg(False, "Invalid email format")

        res = self.M('mailbox').where('username=?', username).count()
        if not res:
            return public.returnMsg(False, public.lang("Delete Failed!"))
        self.M('mailbox').where('username=?', username).delete()

        # 在虚拟用户家目录删除对应邮箱的目录
        if os.path.exists('/www/vmail/{0}/{1}'.format(domain, local_part)):
            public.ExecShell('rm -rf /www/vmail/{0}/{1}'.format(domain, local_part))
        public.WriteLog('Mail Server', f'Delete the mailbox: [{username}] ')
        return public.returnMsg(True, public.lang("Delete mailbox user successfully {}",username, ))

    def send_mail(self, args):
        # 获取服务状态
        service_status = self.get_service_status(args)
        if not service_status['postfix']:
            return public.returnMsg(False,
                                    public.lang('Unable to send mail, error Cause: Some services are not started, please check the service status'))
        # 检测多个 SMTP 服务器的 25 端口是否可用
        if not self._check_smtp_port():
            return public.returnMsg(False,
                                    public.lang('Some cloud vendors (such as Google, Amazon) close port 25 by default, and you need to contact the vendor to open port 25 before you can use the post office service normally'))
        # smtp_server: localhost
        # mail_from: l11@1n123.top  发件人
        # mail_to: ["111@qq.com"]   收件人列表
        # subject: 测试发送           主题
        # content: < h3 >...        内容


        # 查询发件人
        mail_from = args.mail_from
        data = self.M('mailbox').where('username=?', mail_from).field('password_encode,full_name').find()
        password = self._decode(data['password_encode'])
        # 收件人 反序列成列表
        mail_to = json.loads(args.mail_to) if 'mail_to' in args else []

        # for mail_address in mail_to:
        #     # 邮件合法性
        #     if not self._check_email_address(mail_address):
        #         return public.returnMsg(False,
        #                                 public.lang('Failed to send mail, error reason: Incoming address format is incorrect'))
        subject = args.subject
        content = args.content


        # #增加订阅链接  测试----------------------
        #
        # # 生成邮箱jwt
        # mail_jwt = self.generate_jwt(mail_to[0])
        # # 获取公网ip
        # ip = public.readFile("/www/server/panel/data/iplist.txt")
        # # public.print_log("获取公网ip -- {}".format(ip))
        #
        # port = public.readFile('/www/server/panel/data/port.pl')
        # ssl_staus = public.readFile('/www/server/panel/data/ssl.pl')
        # if ssl_staus:
        #     ssl = 'https'
        # else:
        #     ssl = 'http'

        # if subtype.lower() == 'html':
        content = '<html>' + content + '</html>'

        # 附件?
        files = json.loads(args.files) if 'files' in args else []
        # 收件人判断
        if not isinstance(mail_to, list):
            return public.returnMsg(False, 'RECIPIENT LIST ERR')
        if len(mail_to) == 0:
            return public.returnMsg(False, 'RECIPIENT EMPTY ERR')

        try:

            # 登录
            send_mail_client = SendMail(mail_from, password, 'localhost')
            # public.print_log("--------------------登录信息000 ---{}--({})".format(mail_from, password))
            # 用户名full_name
            send_mail_client.setMailInfo(data['full_name'], subject, content, files)
            # 收件人列表  此处记录调用次数
            _, domain = mail_from.split('@')
            result = send_mail_client.sendMail(mail_to, domain, 1)
            return result
        except Exception as e:
            public.print_log(public.get_error_info())
            return public.returnMsg(False, public.lang('Failed to send mail, error reason [{0}]',str(e)))

    # 发送测试  -- 含退订
    def send_mail_test(self, args):
        # 获取服务状态
        service_status = self.get_service_status(args)
        if not service_status['postfix']:
            return public.returnMsg(False,
                                    public.lang('Unable to send mail, error Cause: Some services are not started, please check the service status'))
        # 检测多个 SMTP 服务器的 25 端口是否可用
        if not self._check_smtp_port():
            return public.returnMsg(False,
                                    public.lang('Some cloud vendors (such as Google, Amazon) close port 25 by default, and you need to contact the vendor to open port 25 before you can use the post office service normally'))

        try:
            from plugin.mail_sys.mail_send_bulk import SendMailBulk
        except:
            
            
            SendMailBulk = bulk.SendMailBulk

        return SendMailBulk().send_mail_test(args)

    def _check(self, args):
        if args['fun'] in ['send_mail_http']:
            return True
        else:
            return public.returnMsg(False, public.lang('Interface does not support public access!'))

    def send_mail_http(self, args):
        service_status = self.get_service_status(args)
        if not service_status['postfix']:
            return public.returnMsg(False,
                                    public.lang('Unable to send email, Reason: Some services are not started, please check the service status'))
        if not self._check_smtp_port():
            return public.returnMsg(False,
                                    public.lang('Some cloud vendors (such as Google, Amazon) close port 25 by default, and you need to contact the vendor to open port 25 before you can use the post office service normally'))

        mail_from = args.mail_from
        password = args.password
        mail_to = [item.strip() for item in args.mail_to.split(',')]
        # for mail_address in mail_to:
        #     if not self._check_email_address(mail_address):
        #         return public.returnMsg(False,
        #                                 public.lang('Failed to send mail, error reason: Incoming address format is incorrect'))
        subject = args.subject
        content = args.content

        content = '<html>' + content + '</html>'
        files = json.loads(args.files) if 'files' in args else []

        try:
            data = self.M('mailbox').where('username=?', mail_from).field('full_name').find()
            send_mail_client = SendMail(mail_from, password, 'localhost')
            send_mail_client.setMailInfo(data['full_name'], subject, content, files)
            _, domain = mail_from.split('@')
            result = send_mail_client.sendMail(mail_to, domain, 1)
            return result
        except Exception as e:
            public.print_log(public.get_error_info())
            return public.returnMsg(False, public.lang("Failed to send mail, error reason [{}]",str(e)))
    # 获取文件编码类型
    def get_encoding(self, file):
        import chardet

        try:
            # 二进制方式读取，获取字节数据，检测类型
            with open(file, 'rb') as f:
                data = f.read()
                return chardet.detect(data)['encoding']
        except:
            return 'ascii'

    def get_mails(self, args):
        # # 记录方法开始时间
        # start_time = time.time()
        import email
        import receive_mail
        reload(receive_mail)

        if 'username' not in args:
            return public.returnMsg(False, public.lang('ENTER ACCOUNT NAME'))
        username = args.username
        if '@' not in username:
            return public.returnMsg(False, public.lang('ACCOUNT NAME ERR'))
        local_part, domain = username.split('@')
        if 'p' not in args:
            args.p = 1
        if 'p=' in args.p:
            args.p = args.p.replace('p=', '')

        receive_mail_client = receive_mail.ReceiveMail()
        mail_list = []

        try:
            dir_path = '/www/vmail/{0}/{1}/cur'.format(domain, local_part)
            if os.path.isdir(dir_path):
                # 先将new文件夹的邮件移动到cur文件夹
                new_path = '/www/vmail/{0}/{1}/new'.format(domain, local_part)
                if os.path.isdir(new_path):
                    for file in os.listdir(new_path):
                        src = os.path.join(new_path, file)
                        dst = os.path.join(dir_path, file)
                        shutil.move(src, dst)
                files = []
                for fname in os.listdir(dir_path):
                    mail_file = os.path.join(dir_path, fname)
                    if not os.path.exists(mail_file): continue
                    f_info = {}
                    f_info['name'] = fname
                    f_info['mtime'] = os.path.getmtime(mail_file)
                    save_day = self.get_save_day(None)
                    if save_day > 0:
                        deltime = int(time.time()) - save_day * 86400
                        if int(f_info['mtime']) < deltime:
                            os.remove(mail_file)
                            continue
                    files.append(f_info)


                files = sorted(files, key=lambda x: x['mtime'], reverse=True)

                page_data = public.get_page(len(files), int(args.p), 10)

                # import re
                pattern = r"href='(?:/v2)?/plugin.*?\?p=(\d+)'"
                # 使用re.sub进行替换
                page_data['page'] = re.sub(pattern, r"href='\1'", page_data['page'])

                shift = int(page_data['shift'])
                row = int(page_data['row'])
                files = files[shift:shift + row]

                for d in files:
                    mail_file = os.path.join(dir_path, d['name'])
                    encoding = self.get_encoding(mail_file)
                    # print(encoding)
                    if sys.version_info[0] == 2:
                        import io
                        fp = io.open(mail_file, 'r', encoding=encoding)
                    else:
                        fp = open(mail_file, 'r', encoding=encoding)

                    try:
                        message = email.message_from_file(fp)
                        # 查出了邮件全部信息
                        mailInfo = receive_mail_client.getMailInfo(msg=message)
                        mailInfo['path'] = mail_file
                        mail_list.append(mailInfo)
                    except:
                        public.writeFile("{}/error.log".format(self.__setupPath), public.get_error_info())
                        continue

                return {'status': True, 'data': mail_list,
                        # /plugin%3Faction%3Da%26name%3Dmail_sys%26s%3Dget_sent_mails?p=2
                        # 'page': page_data['page'].replace('/plugin?action=a&name=mail_sys&s=get_mails&p=', '')}
                        'page': page_data['page']}
            else:
                page_data = public.get_page(0, int(args.p), 10)
                return {'status': True, 'data': mail_list,
                        # 'page': page_data['page'].replace('/plugin?action=a&name=mail_sys&s=get_mails&p=', '')}
                        'page': page_data['page']}
        except Exception as e:
            public.print_log(public.get_error_info())
            return public.returnMsg(False, public.lang('Failed to get mail, error reason[{0}]',str(e)))

    def delete_mail(self, args):
        path = args.path
        if not os.path.exists(path):
            return public.returnMsg(False, public.lang('Mail path does not exist'))
        os.remove(path)
        return public.returnMsg(True, public.lang('Delete mail successfully'))
    def delete_mail_multiple(self, args):
        """ 批量删除邮件内容 """
        path_all = args.path_all

        try:
            path_list = json.loads(path_all)
        except:
            return public.returnMsg(False, public.lang('Invalid JSON format for paths'))

        # 检查路径列表是否为空
        if not path_list:
            return public.returnMsg(False, public.lang('No paths provided'))

        # 记录删除失败的文件
        failed_paths = []

        # 批量删除文件
        for path in path_list:
            if not os.path.exists(path):
                failed_paths.append((path, public.lang('Mail path does not exist')))
                continue
            try:
                os.remove(path)
            except Exception as e:
                failed_paths.append((path, str(e)))

        # 根据删除结果返回消息
        if failed_paths:
            error_message = '\n'.join([f'Path: {p}, Error: {e}' for p, e in failed_paths])
            return public.returnMsg(False, public.lang('Some files were not deleted:\n') + error_message)
        else:
            return public.returnMsg(True, public.lang('All mails deleted successfully'))

    def get_config(self, args):
        from files import files

        if args.service == 'postfix':
            args.path = '/etc/postfix/main.cf'
        elif args.service == 'dovecot':
            args.path = '/etc/dovecot/dovecot.conf'
        elif args.service == 'rspamd':
            args.path = '/etc/rspamd/rspamd.conf'
        elif args.service == 'opendkim':
            args.path = '/etc/opendkim.conf'
        else:
            return public.returnMsg(False, public.lang('Service name is incorrect'))

        return files().GetFileBody(args)

    def save_config(self, args):
        from files import files

        if args.service == 'postfix':
            args.path = '/etc/postfix/main.cf'
        elif args.service == 'dovecot':
            args.path = '/etc/dovecot/dovecot.conf'
        elif args.service == 'rspamd':
            args.path = '/etc/rspamd/rspamd.conf'
        elif args.service == 'opendkim':
            args.path = '/etc/opendkim.conf'
        else:
            return public.returnMsg(False, public.lang('Service name is incorrect'))
        args.encoding = 'utf-8'

        result = files().SaveFileBody(args)
        if result['status']:
            if args.service == 'postfix':
                public.ExecShell('systemctl reload postfix')
            elif args.service == 'dovecot':
                public.ExecShell('systemctl reload dovecot')
            elif args.service == 'rspamd':
                public.ExecShell('systemctl reload rspamd')
            elif args.service == 'opendkim':
                public.ExecShell('systemctl reload opendkim')
        return result

    def service_admin(self, args):
        service_name = args.service
        if service_name.lower() not in ['postfix', 'dovecot', 'rspamd', 'opendkim']:
            return public.returnMsg(False, public.lang('Service name is incorrect'))
        type = args.type
        if type.lower() not in ['start', 'stop', 'restart', 'reload']:
            return public.returnMsg(False, public.lang('Incorrect operation'))

        exec_str = 'systemctl {0} {1}'.format(type, service_name)
        if type == 'reload':
            if service_name == 'postfix':
                exec_str = '/usr/sbin/postfix reload'
            elif service_name == 'dovecot':
                exec_str = '/usr/bin/doveadm reload'
            elif service_name == 'rspamd':
                exec_str = 'systemctl reload rspamd'
            elif service_name == 'opendkim':
                exec_str = 'systemctl reload opendkim'
        if service_name == 'opendkim' and type in ('start', 'restart'):
            exec_str = '''
sed -i "s#/var/run/opendkim/opendkim.pid#/run/opendkim/opendkim.pid#" /etc/opendkim.conf
sed -i "s#/var/run/opendkim/opendkim.pid#/run/opendkim/opendkim.pid#" /etc/sysconfig/opendkim
sed -i "s#/var/run/opendkim/opendkim.pid#/run/opendkim/opendkim.pid#" /usr/lib/systemd/system/opendkim.service
systemctl daemon-reload
systemctl enable opendkim
systemctl restart opendkim
'''

        public.ExecShell(exec_str)
        return public.returnMsg(True, public.lang('{} Successful execution of {} operation',service_name, type))

    # 获取收件箱 增加域名筛选
    def get_sent_mails(self, args):
        import email
        import receive_mail
        reload(receive_mail)

        if 'username' not in args:
            return public.returnMsg(False, public.lang('Please pass in the account name'))
        username = args.username
        if '@' not in username:
            return public.returnMsg(False, public.lang('The account name is invalid.'))
        local_part, domain = username.split('@')
        if 'p' not in args:
            args.p = 1
        if 'p=' in args.p:
            args.p = args.p.replace('p=', '')

        receive_mail_client = receive_mail.ReceiveMail()
        mail_list = []
        try:
            # 读取发件箱cur文件夹的邮件
            dir_path = '/www/vmail/{0}/{1}/.Sent/cur'.format(domain, local_part)
            if os.path.isdir(dir_path):
                files = []
                for fname in os.listdir(dir_path):
                    mail_file = os.path.join(dir_path, fname)
                    if not os.path.exists(mail_file): continue
                    f_info = {}
                    f_info['name'] = fname
                    f_info['mtime'] = os.path.getmtime(mail_file)
                    save_day = self.get_save_day(None)
                    if save_day > 0:
                        deltime = int(time.time()) - save_day * 86400
                        if int(f_info['mtime']) < deltime:
                            os.remove(mail_file)
                            continue
                    files.append(f_info)
                files = sorted(files, key=lambda x: x['mtime'], reverse=True)
                page_data = public.get_page(len(files), int(args.p), 10)
                # 替换掉 href标签里的多余信息 只保留页码
                # pattern =r"href='(/v2)?/plugin.*?\?p=(\d+)'"
                pattern = r"href='(?:/v2)?/plugin.*?\?p=(\d+)'"
                # 使用re.sub进行替换
                page_data['page'] = re.sub(pattern, r"href='\1'", page_data['page'])
                shift = int(page_data['shift'])
                row = int(page_data['row'])
                files = files[shift:shift + row]
                for d in files:
                    mail_file = os.path.join(dir_path, d['name'])
                    fp = open(mail_file, 'r')
                    try:
                        message = email.message_from_file(fp)
                        mailInfo = receive_mail_client.getMailInfo(msg=message)
                        mailInfo['path'] = mail_file
                        mail_list.append(mailInfo)
                    except:
                        public.print_log(public.get_error_info())
                        continue
                return {'status': True, 'data': mail_list,
                        # 'page': page_data['page'].replace('/plugin?action=a&name=mail_sys&s=get_sent_mails&p=', '')}
                        'page': page_data['page']}
            else:
                page_data = public.get_page(0, int(args.p), 10)
                return {'status': True, 'data': mail_list,
                        # 'page': page_data['page'].replace('/plugin?action=a&name=mail_sys&s=get_sent_mails&p=', '')}
                        'page': page_data['page']}
        except Exception as e:
            public.print_log(public.get_error_info())
            return public.returnMsg(False, public.lang('Failed to get sent mail, error reason [{0}]',str(e)))

    # 设置postfix ssl
    def set_postfix_ssl(self, csrpath, keypath, act):
        main_file = self.postfix_main_cf
        master_file = "/etc/postfix/master.cf"
        main_conf = public.readFile(main_file)
        master_conf = public.readFile(master_file)
        if act == "0":
            csrpath = "/etc/pki/dovecot/certs/dovecot.pem"
            keypath = "/etc/pki/dovecot/private/dovecot.pem"
            master_rep = r"\n*\s*-o\s+smtpd_tls_auth_only=yes"
            master_str = "\n#  -o smtpd_tls_auth_only=yes"
            master_rep1 = r"\n*\s*-o\s+smtpd_tls_wrappermode=yes"
            master_str1 = "\n#  -o smtpd_tls_wrappermode=yes"
        else:
            master_rep = r"\n*#\s*-o\s+smtpd_tls_auth_only=yes"
            master_str = "\n  -o smtpd_tls_auth_only=yes"
            master_rep1 = r"\n*#\s*-o\s+smtpd_tls_wrappermode=yes"
            master_str1 = "\n  -o smtpd_tls_wrappermode=yes"

        for i in [[main_conf, main_file], [master_conf, master_file]]:
            if not i[0]:
                return public.returnMsg(False, public.lang("Can not find postfix config file {}",i[1]))
        main_rep = r"smtpd_tls_cert_file\s*=\s*.+"
        main_conf = re.sub(main_rep, "smtpd_tls_cert_file = {}".format(csrpath), main_conf)
        main_rep = r"smtpd_tls_key_file\s*=\s*.+"
        main_conf = re.sub(main_rep, "smtpd_tls_key_file = {}".format(keypath), main_conf)
        public.writeFile(main_file, main_conf)
        # master_rep = "#\s*-o\s+smtpd_tls_auth_only=yes"
        master_conf = re.sub(master_rep, master_str, master_conf)
        master_conf = re.sub(master_rep1, master_str1, master_conf)
        public.writeFile(master_file, master_conf)

    def get_dovecot_version(self, args=None):
        data = public.ExecShell("dpkg -l|grep dovecot-core|awk -F':' '{print $2}'")[0]
        if os.path.exists('/etc/redhat-release'):
            data = public.ExecShell('rpm -qa | grep dovecot | grep -v pigeonhole')[0].split('-')[1]
        return data

    def set_dovecot_ssl(self, csrpath, keypath, act):
        dovecot_version = self.get_dovecot_version()
        ssl_file = "/etc/dovecot/conf.d/10-ssl.conf"
        ssl_conf = public.readFile(ssl_file)
        if not ssl_conf:
            return public.returnMsg(False, public.lang("Can not find postfix config file {}",ssl_file))
        if act == "0":
            csrpath = "/etc/pki/dovecot/certs/dovecot.pem"
            keypath = "/etc/pki/dovecot/private/dovecot.pem"
        ssl_rep = r"ssl_cert\s*=\s*<.+"
        ssl_conf = re.sub(ssl_rep, "ssl_cert = <{}".format(csrpath), ssl_conf)
        ssl_rep = r"ssl_key\s*=\s*<.+"
        ssl_conf = re.sub(ssl_rep, "ssl_key = <{}".format(keypath), ssl_conf)
        if dovecot_version.startswith('2.3'):
            if act == '1':
                if not os.path.exists('/etc/dovecot/dh.pem') or os.path.getsize('/etc/dovecot/dh.pem') < 300:
                    public.ExecShell('openssl dhparam 2048 > /etc/dovecot/dh.pem')
                ssl_conf = ssl_conf + "\nssl_dh = </etc/dovecot/dh.pem"
            else:
                ssl_conf = re.sub(r'\nssl_dh = </etc/dovecot/dh.pem', '', ssl_conf)
                os.remove('/etc/dovecot/dh.pem')
        public.writeFile(ssl_file, ssl_conf)

    # 设置ssl  弃用
    def set_ssl(self, args):
        path = '{}/cert/'.format(self.__setupPath)
        csrpath = path + "fullchain.pem"
        keypath = path + "privkey.pem"
        backup_cert = '/tmp/backup_cert_mail_sys'
        if hasattr(args, "act") and args.act == "1":
            if args.key.find('KEY') == -1: return public.returnMsg(False, public.lang('Private Key ERROR, please check!'))
            if args.csr.find('CERTIFICATE') == -1: return public.returnMsg(False, public.lang('Certificate ERROR, please check!'))
            public.writeFile('/tmp/mail_cert.pl', str(args.csr))
            if not public.CheckCert('/tmp/mail_cert.pl'): return public.returnMsg(False,
                                                                                  public.lang('Certificate ERROR, please paste the correct certificate in pem format!'))
            if os.path.exists(backup_cert): shutil.rmtree(backup_cert)
            if os.path.exists(path): shutil.move(path, backup_cert)
            if os.path.exists(path): shutil.rmtree(path)

            os.makedirs(path)
            public.writeFile(keypath, args.key)
            public.writeFile(csrpath, args.csr)
        else:
            if os.path.exists(csrpath):
                os.remove(csrpath)
            if os.path.exists(keypath):
                os.remove(keypath)

        # 写入配置文件
        p_result = self.set_postfix_ssl(csrpath, keypath, args.act)
        if p_result: return p_result
        d_result = self.set_dovecot_ssl(csrpath, keypath, args.act)
        if d_result: return d_result

        import time
        for i in ["dovecot", "postfix"]:
            args.service = i
            args.type = "restart"
            self.service_admin(args)
            time.sleep(1)
        # 清理备份证书
        if os.path.exists(backup_cert): shutil.rmtree(backup_cert)
        return public.returnMsg(True, public.lang('Successful setup'))

    # 获取ssl状态   弃用
    def get_ssl_status(self, args):
        path = '{0}/cert/'.format(self.__setupPath)
        csrpath = path + "fullchain.pem"
        keypath = path + "privkey.pem"
        if not (os.path.exists(csrpath) and os.path.exists(keypath)):
            return False
        main_file = self.postfix_main_cf
        main_conf = public.readFile(main_file)
        master_file = "/etc/postfix/master"
        master_conf = public.readFile(master_file)
        dovecot_ssl_file = "/etc/dovecot/conf.d/10-ssl.conf"
        dovecot_ssl_conf = public.readFile(dovecot_ssl_file)
        if main_conf:
            if csrpath not in main_conf and keypath not in main_conf:
                return False
        if master_conf:
            rep = r"\n*\s*-o\s+smtpd_sasl_auth_enable\s*=\s*yes"
            if not re.search(rep, master_conf):
                return False
        if dovecot_ssl_conf:
            if csrpath not in main_conf and keypath not in main_conf:
                return False
        return True

    # 获取可以监听的IP
    def _get_all_ip(self):
        # import psutil

        public_ip = self._get_pubilc_ip()
        net_info = psutil.net_if_addrs()
        addr = []
        for i in net_info.values():
            addr.append(i[0].address)
        locataddr = public.readFile('/www/server/panel/data/iplist.txt')
        if not locataddr:
            locataddr = ""
        ip_address = locataddr.strip()
        if ip_address not in addr:
            addr.append(ip_address)
        if public_ip not in addr:
            addr.append(public_ip)
        # 兼容用户新增ip
        return addr

    def get_mail_forward(self, args):
        result = self.M('alias').select()
        return result

    # 设置邮件转发
    def set_mail_forward(self, args):
        """
        user            domain_name/email_address
        forward_user    email_address
        domain          domain
        active          0/1
        :param args:
        :return:
        """
        # 检查被转发用户是否存在
        if self.M('alias').where('address=?', args.user).count() > 0:
            return public.returnMsg(False, public.lang('The forward user already exists'))
        # 检查域名是否存在
        if self.M('domain').where('domain=?', args.domain).count() <= 0:
            return public.returnMsg(False, public.lang('Domain name does not exist in the mail server'))
        # # 检查被用户是否存在邮局内
        # if self.M('mailbox').where('username=?', args.user).count() <= 0 and args.user[0] != '@':
        #     return public.returnMsg(False, public.lang('Forwarded user does not exist'))
        # 换行符替换为逗号
        tmp = args.forward_user.split('\\n')
        if "\n" in tmp[0]:
            tmp = tmp[0].split('\n')
        forward_user = []
        for i in tmp:
            if not i:
                continue
            forward_user.append(i)
        forward_users = ",".join(forward_user)
        create_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self.M('alias').add('address,goto,domain,created,modified,active',
                            (args.user, forward_users, args.domain, create_time, create_time, args.active))
        return public.returnMsg(True, public.lang('Mail forwarding added successfully'))

    def edit_mail_forward(self, args):
        if self.M('alias').where('address=?', args.user).count() == 0:
            return public.returnMsg(False, public.lang('The forward user not exists'))
        # 换行符替换为逗号
        tmp = args.forward_user.split('\\n')
        if "\n" in tmp[0]:
            tmp = tmp[0].split('\n')
        forward_user = []
        for i in tmp:
            if not i:
                continue
            forward_user.append(i)
        forward_users = ",".join(forward_user)
        modified_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self.M('alias').where('address=?', args.user).save(
            'goto,modified,active', (forward_users, modified_time, args.active))
        return public.returnMsg(True, public.lang('Mail forwarding modified successfully'))

    def delete_mail_forward(self, args):
        if self.M('alias').where('address=?', args.user).count() == 0:
            return public.returnMsg(False, public.lang('The forward user not exists'))
        self.M('alias').where('address=?', args.user).delete()
        return public.returnMsg(True, public.lang('Mail forwarding delete successfully'))

    def get_bcc(self, args):
        # account_id =int(args.account_id) if 'account_id' in args else 0  # 兼容子面板  后续改参数
        forward = public.readFile(self._forward_conf)
        if forward:
            forward = json.loads(forward)
        else:
            forward = {"recipient": [], "sender": []}
        # 如果没有 active 字段, 则增加 "active":1
        if forward['recipient']:
            for d in forward['recipient']:
                d.setdefault('active', 1)
        if forward['sender']:
            for d in forward['sender']:
                d.setdefault('active', 1)

          # if not account_id:
        #     # 隐藏子面板的配置
        #     domain_user_list = self.M('domain_user').field('domain').select()
        #     user_domain_list = [item['domain'] for item in domain_user_list]
        #
        #     # 使用列表推导式创建新的过滤后的列表
        #     forward['recipient'] = [
        #         item for item in forward['recipient']
        #         if item['domain'] not in user_domain_list
        #     ]
        #
        #     forward['sender'] = [
        #         item for item in forward['sender']
        #         if item['domain'] not in user_domain_list
        #     ]

        return forward

    # 设置邮件秘抄
    def set_mail_bcc(self, args):
        """
        type            sender/recipien
        user            domain_name/email_address
        forward_user    email_address
        domain          domain
        active          active  0/1   默认1 开启
        :param args:
        :return:
        """
        # 增加 active 默认1
        if not hasattr(args, 'active') or args.get('active/d', 1) == 1:
            args.active = 1
        else:
            args.active = 0
        # if not hasattr(args, 'domain') or args.get('domain/s', '') == '':
        #     args.domain = args.user.strip().split('@')[1]
        args.domain = args.user.strip().split('@')[1]
        data = self.get_bcc(args)
        for d in data[args.type]:
            if args.user == d["user"] and args.forward_user == d["forward_user"]:
                return public.returnMsg(False, public.lang("Forward name already exists"))

        # 启用的状态下才能加入密抄
        if args.active:
            rep = r"^(?=^.{3,255}$)[a-zA-Z0-9\_\-][a-zA-Z0-9\_\-]{0,62}(\.[a-zA-Z0-9\_\-][a-zA-Z0-9\_\-]{0,62})+$"
            if re.search(rep, args.user):
                content = "\n@{} {}".format(args.user, args.forward_user)
            else:
                content = "\n{} {}".format(args.user, args.forward_user)
            # 密抄文件
            bcc_file = "/etc/postfix/{}_bcc".format(args.type)
            public.writeFile(bcc_file, content, "a+")

        # 增加启停开关
        data[args.type].append(
            {"domain": args.domain, "user": args.user, "forward_user": args.forward_user, "active": args.active})

        public.writeFile(self._forward_conf, json.dumps(data))
        for i in ["/etc/postfix/sender_bcc", "/etc/postfix/recipient_bcc"]:
            if not os.path.exists(i):
                public.writeFile(i, "")
        # bcc_conf = '\nrecipient_bcc_maps = hash:/etc/postfix/recipient_bcc\nsender_bcc_maps = hash:/etc/postfix/sender_bcc\n'
        # public.writeFile(self.postfix_main_cf, bcc_conf, 'a+')

        bcc_conf =''
        if not self.check_postfix_bcc('recipient_bcc_maps'):
            bcc_conf +='\nrecipient_bcc_maps = hash:/etc/postfix/recipient_bcc\n'
        if not self.check_postfix_bcc('sender_bcc_maps'):
            bcc_conf +='sender_bcc_maps = hash:/etc/postfix/sender_bcc\n'
        if bcc_conf:
            public.writeFile(self.postfix_main_cf,'\n'+bcc_conf, 'a+')

        shell_str = '''
postmap /etc/postfix/recipient_bcc
postmap /etc/postfix/sender_bcc
systemctl reload postfix
'''
        public.ExecShell(shell_str)
        return public.returnMsg(True, public.lang("Set up successfully"))
    def check_postfix_bcc(self, act):
        try:      
            res = public.ExecShell('postconf {}'.format(act))
            if '='in res[0] and res[0].split('=')[1].strip():
                return True 
            else:
                return False
        except:
            return False
        

    # 删除邮件秘送
    def del_bcc(self, args):
        data = self.get_bcc(args)
        bcc_file = "/etc/postfix/{}_bcc".format(args.type)
        # 密抄配置
        conf = public.readFile(bcc_file)
        n = 0
        rep = r"\n*{}\s+{}".format(args.user, args.forward_user)
        for d in data[args.type]:
            if args.user == d["user"] and args.forward_user == d["forward_user"]:
                del (data[args.type][n])
                public.writeFile(self._forward_conf, json.dumps(data))
                conf = re.sub(rep, '', conf)
                public.writeFile(bcc_file, conf)
                public.ExecShell('postmap {} && systemctl reload postfix'.format(bcc_file))
                return public.returnMsg(True, public.lang('Successfully deleted'))
            n += 1
        return public.returnMsg(True, public.lang('Failed to delete'))

    # 修改邮件密送 -- 删除 添加
    def update_bcc(self, args):
        self.del_bcc(args)
        args.type = args.type_new
        args.forward_user = args.forward_user_new
        args.active = args.active_new
        self.set_mail_bcc(args)
        return public.returnMsg(True, 'modify successfully')

    # 设置邮件中继
    def set_smtp_relay(self, args):
        """
            username: mailgun的用户名
            passwd: mailgun的密码
            smtphost: smtp地址
            port: smtp端口
        """
        username = args.username
        passwd = args.passwd
        smtphost = args.smtphost
        port = args.port
        add_paramater = """
#BEGIN_POSTFIX_RELAY
relayhost = [{smtphost}]:{port}
smtp_sasl_auth_enable = yes
smtp_sasl_password_maps = static:{username}:{passwd}
smtp_sasl_security_options = noanonymous
#END_POSTFIX_RELAY
""".format(smtphost=smtphost, port=port, username=username, passwd=passwd)
        if self.get_smtp_status(args)['status']:
            return public.returnMsg(False, public.lang("The smtp relay already exists"))
        public.writeFile(self.postfix_main_cf, add_paramater, 'a+')
        return public.returnMsg(True, public.lang("Setup successfully"))

    # 获取中继信息
    def get_smtp_status(self, args):
        conf = public.readFile(self.postfix_main_cf)
        if not conf:
            return public.returnMsg(False, public.lang("No configuration information found"))
        if "BEGIN_POSTFIX_RELAY" in conf:
            host_port_reg = r"relayhost\s*=\s*\[([\.\w]+)\]:(\d+)"
            tmp = re.search(host_port_reg, conf)
            host = port = user = passwd = ""
            if tmp:
                host = tmp.groups(1)[0]
                port = tmp.groups(2)[1]
            user_passwd_reg = r"smtp_sasl_password_maps\s*=\s*static:(.*?):(.*)"
            tmp = re.search(user_passwd_reg, conf)
            if tmp:
                user = tmp.groups(1)[0]
                passwd = tmp.groups(2)[1]
            return public.returnMsg(True, {"host": host, "port": port, "user": user, "passwd": passwd})
        return public.returnMsg(False, public.lang("No configuration information found"))

    # 取消中继
    def cancel_smtp_relay(self, args):
        conf = public.readFile(self.postfix_main_cf)
        reg = r"\n#BEGIN_POSTFIX_RELAY(.|\n)+#END_POSTFIX_RELAY\n"
        tmp = re.search(reg, conf)
        if not tmp:
            return public.returnMsg(False, public.lang("The smtp relay does not exist"))
        conf = re.sub(reg, "", conf)
        public.writeFile(self.postfix_main_cf, conf)
        return public.returnMsg(True, public.lang("Setup successfully"))

    # 获取反垃圾服务监听ip和端口
    def _get_anti_server_ip_port(self, get):
        conf = public.readFile('/etc/amavisd/amavisd.conf')
        if not os.path.exists('/etc/redhat-release'):
            conf = public.readFile('/etc/amavis/conf.d/20-debian_defaults')
        reg = r'\n\${}\s*=\s*[\'\"]?(.*?)[\'\"]?;'
        spam_server_ip_reg = reg.format('inet_socket_bind')
        spam_server_port_reg = reg.format('inet_socket_port')
        spam_server_ip = re.search(spam_server_ip_reg, conf)
        if spam_server_ip:
            spam_server_ip = spam_server_ip.groups(1)[0]
        else:
            spam_server_ip = '127.0.0.1'
        spam_server_port = re.search(spam_server_port_reg, conf)
        if spam_server_port:
            spam_server_port = spam_server_port.groups(1)[0]
        else:
            spam_server_port = '10024'
        return {'spam_server_port': spam_server_port, 'spam_server_ip': spam_server_ip}

    # 设置postfix main配置支持反垃圾
    def _set_main_cf_anti_spam(self, args):
        conf = public.readFile(self.postfix_main_cf)
        anti_spam_conf = """
##BT-ANTISPAM-BEGIN
content_filter=amavisfeed:[{}]:{}
##BT-ANTISPAM-END
"""
        if 'amavisfeed' in conf:
            return
        if args.spam_server_ip == 'localhost':
            spam_server_info = self._get_anti_server_ip_port(get=None)
            anti_spam_conf = anti_spam_conf.format(spam_server_info['spam_server_ip'],
                                                   spam_server_info['spam_server_port'])
            public.writeFile(self.postfix_main_cf, conf + anti_spam_conf)
        else:
            anti_spam_conf = anti_spam_conf.format(args.spam_server_ip, args.spam_server_port)
            public.writeFile(self.postfix_main_cf, conf + anti_spam_conf)

    # 设置postfix master配置支持反垃圾
    def _set_master_cf_anti_spam(self):
        master_file = '/etc/postfix/master.cf'
        conf = public.readFile(master_file)
        if re.search('##BT-ANTISPAM-BEGIN', conf):
            return
        anti_conf = """
##BT-ANTISPAM-BEGIN
amavisfeed unix -   -   n   -   2    smtp
 -o smtp_data_done_timeout=1000
 -o smtp_send_xforward_command=yes
 -o disable_dns_lookups=yes
 -o max_use=20
127.0.0.1:10025 inet n -   n   -   -    smtpd
 -o content_filter=
 -o smtpd_delay_reject=no
 -o smtpd_client_restrictions=permit_mynetworks,reject
 -o smtpd_helo_restrictions=
 -o smtpd_sender_restrictions=
 -o smtpd_recipient_restrictions=permit_mynetworks,reject
 -o smtpd_data_restrictions=reject_unauth_pipelining
 -o smtpd_end_of_data_restrictions=
 -o smtpd_restriction_classes=
 -o mynetworks=127.0.0.0/8,192.168.0.0/16
 -o smtpd_error_sleep_time=0
 -o smtpd_soft_error_limit=1001
 -o smtpd_hard_error_limit=1000
 -o smtpd_client_connection_count_limit=0
 -o smtpd_client_connection_rate_limit=0
 -o receive_override_options=no_header_body_checks,no_unknown_recipient_checks,no_milters
 -o local_header_rewrite_clients=
##BT-ANTISPAM-END
 """
        public.writeFile(master_file, conf + anti_conf)

    def _set_dovecot_cf_anti_spam(self):
        '''
        设置dovecot配置支持反垃圾
        :return:
        '''
        # 判断dovecot-sieve是否安装成功
        if os.path.exists('/etc/dovecot/conf.d/90-sieve.conf'):
            download_conf_shell = '''
wget "{download_conf_url}/mail_sys/dovecot/dovecot.conf" -O /etc/dovecot/dovecot.conf -T 10
wget "{download_conf_url}/mail_sys/dovecot/15-lda.conf" -O /etc/dovecot/conf.d/15-lda.conf -T 10
wget "{download_conf_url}/mail_sys/dovecot/20-lmtp.conf" -O /etc/dovecot/conf.d/20-lmtp.conf -T 10
wget "{download_conf_url}/mail_sys/dovecot/90-plugin.conf" -O /etc/dovecot/conf.d/90-plugin.conf -T 10
wget "{download_conf_url}/mail_sys/dovecot/90-sieve.conf" -O /etc/dovecot/conf.d/90-sieve.conf -T 10
    '''.format(download_conf_url=public.get_url())
            public.ExecShell(download_conf_shell)
            if not os.path.exists('/etc/dovecot/sieve'):
                os.makedirs('/etc/dovecot/sieve')
            default_sieve = '''require "fileinto";
if header :contains "X-Spam-Flag" "YES" {
    fileinto "Junk";
}'''
            public.writeFile('/etc/dovecot/sieve/default.sieve', default_sieve)
            public.ExecShell('chown -R vmail:dovecot /etc/dovecot')

    # 开启反垃圾
    def turn_on_anti_spam(self, args):
        if args.spam_server_ip != 'localhost':
            return public.returnMsg(False, public.lang('Currently does not support remote scanning, the function is being tested'))
        if args.spam_server_ip == 'localhost' and not os.path.exists('/www/server/panel/plugin/anti_spam'):
            return public.returnMsg(False, public.lang('Please go to the app store to install the anti-spam'))
        self._set_main_cf_anti_spam(args)
        self._set_master_cf_anti_spam()
        self._set_dovecot_cf_anti_spam()
        public.ExecShell('/usr/sbin/postfix reload')
        public.ExecShell('systemctl restart dovecot')
        public.ExecShell('systemctl restart spamassassin')
        return public.returnMsg(True, public.lang('Setup successfully'))

    # # 关闭反垃圾
    def turn_off_anti_spam(self, args):
        # 清理master配置
        master_file = '/etc/postfix/master.cf'
        conf = public.readFile(master_file)
        reg = "\n##BT-ANTISPAM-BEGIN(.|\n)+##BT-ANTISPAM-END\n"
        conf = re.sub(reg, '', conf)
        public.writeFile(master_file, conf)
        # 清理main配置
        conf = public.readFile(self.postfix_main_cf)
        conf = re.sub(reg, '', conf)
        public.writeFile(self.postfix_main_cf, conf)
        public.ExecShell('/usr/sbin/postfix reload')
        return public.returnMsg(True, public.lang('Closed successfully'))

    # 获取反垃圾开启状态
    def get_anti_spam_status(self, args):
        conf = public.readFile(self.postfix_main_cf)
        if re.search('##BT-ANTISPAM-BEGIN', conf):
            return True
        return False

    # 获取数据备份任务是否存在的状态
    def get_backup_task_status(self, get):
        c_id = public.M('crontab').where('name=?', u'[Do not delete] Mail server data backup task').getField('id')
        if not c_id: return public.returnMsg(False, public.lang('Backup task does not exist!'))
        data = public.M('crontab').where('name=?', u'[Do not delete] Mail server data backup task').find()
        return public.returnMsg(True, data)

    # 打开数据备份任务
    def open_backup_task(self, get):
        import crontab
        p = crontab.crontab()

        c_id = public.M('crontab').where('name=?', u'[Do not delete] Mail server data backup task').getField('id')
        if c_id:
            data = {}
            data['id'] = c_id
            data['name'] = u'[Do not delete] Mail server data backup task'
            data['type'] = get.type
            data['where1'] = get.where1 if 'where1' in get else ''
            data['sBody'] = ''
            data['backupTo'] = get.backupTo if 'backupTo' in get else 'localhost'
            data['sType'] = 'path'
            data['hour'] = get.hour if 'hour' in get else ''
            data['minute'] = get.minute if 'minute' in get else ''
            data['week'] = get.week if 'week' in get else ''
            data['sName'] = '/www/vmail/'
            data['urladdress'] = ''
            data['save'] = get.save
            p.modify_crond(data)
            return public.returnMsg(True, public.lang('Edit successful!'))
        else:
            data = {}
            data['name'] = u'[Do not delete] Mail server data backup task'
            data['type'] = get.type
            data['where1'] = get.where1 if 'where1' in get else ''
            data['sBody'] = ''
            data['backupTo'] = get.backupTo if 'backupTo' in get else 'localhost'
            data['sType'] = 'path'
            data['hour'] = get.hour if 'hour' in get else ''
            data['minute'] = get.minute if 'minute' in get else ''
            data['week'] = get.week if 'week' in get else ''
            data['sName'] = '/www/vmail/'
            data['urladdress'] = ''
            data['save'] = get.save
            p.AddCrontab(data)
            return public.returnMsg(True, public.lang('Setup successful!'))

    # 关闭数据备份任务
    def close_backup_task(self, get):
        import crontab

        p = crontab.crontab()
        c_id = public.M('crontab').where('name=?', u'[Do not delete] Mail server data backup task').getField('id')
        if not c_id: return public.returnMsg(False, public.lang('Backup task does not exist!'))
        args = {"id": c_id}
        p.DelCrontab(args)
        return public.returnMsg(True, public.lang('Close successful!'))

    # 获取已安装云存储插件列表
    def get_cloud_storage_list(self, get):
        data = []
        tmp = public.readFile('data/libList.conf')
        libs = json.loads(tmp)
        for lib in libs:
            if 'opt' not in lib: continue
            filename = 'plugin/{}'.format(lib['opt'])
            if not os.path.exists(filename): continue
            data.append({'name': lib['name'], 'value': lib['opt']})
        return data

    # 获取本地备份文件列表
    def get_backup_file_list(self, get):
        dir_path = get.path.strip()
        # /vmail 备份目录  dir_path 拼接/vmail
        if not dir_path.endswith('/vmail'):
            dir_path = dir_path+'/vmail'

        if not os.path.exists(dir_path):
            os.makedirs(dir_path, 384)
        files = []

        for file_name in os.listdir(dir_path):
            # public.print_log("循环 --{}".format(file_name))
            if not file_name.startswith('path_vmail'):
                # public.print_log("跳过1")
                continue
            file_path = os.path.join(dir_path, file_name)
            if not os.path.exists(file_path):
                # public.print_log("跳过2")
                continue
            f_info = {}
            f_info['name'] = file_name
            f_info['mtime'] = os.path.getmtime(file_path)
            files.append(f_info)
        # public.print_log("files --{}".format(files))
        files = sorted(files, key=lambda x: x['mtime'], reverse=True)
        return files

    def get_backup_path(selfg, get):
        path = public.M('config').where("id=?", (1,)).getField('backup_path')
        path = os.path.join(path, 'path')
        # 邮局专属备份目录
        path = path + '/vmail'
        return path

    # 数据恢复
    def restore(self, get):
        file_path = get.file_path.strip()
        if not os.path.exists(file_path):
            return public.returnMsg(False, public.lang('File does not exist!'))
        # 检测当前文件是否是正确的备份文件 /.../path_vmail_20240614_095728.tar.gz
        # 以 path_vmail开头  并且是 .tar.gz 结尾
        file_name = os.path.basename(file_path)
        if file_name.startswith('path_vmail') and file_name.endswith('.tar.gz'):
            cmd = 'cd {} && tar -xzvf {} 2>&1'.format('/www', file_path)
            print(cmd)
            public.ExecShell(cmd)
            return public.returnMsg(True, public.lang('Recovery complete'))
        else:
            return public.returnMsg(False,
                                    public.lang('This is not a valid backup file! The filename should start with "path_vmail" and end with ".tar.gz"'))

    # 设置收件箱和发件箱邮件保存的天数
    def set_save_day(self, get):
        # 更新缓存
        # from BTPanel import cache
        skey = "mail_save_day"
        cache.set(skey, get.save_day, 86400)

        public.writeFile(self._save_conf, get.save_day)
        return public.returnMsg(True, public.lang('Setup successful'))

    # 获取收件箱和发件箱邮件保存的天数
    def get_save_day(self, get):
        # from BTPanel import cache
        skey = "mail_save_day"
        cache_day = cache.get(skey)
        if cache_day:
            return int(cache_day)
        if not os.path.exists(self._save_conf):
            return 0
        save_day = int(public.readFile(self._save_conf))
        cache.set(skey, save_day, 86400)
        return save_day

    def _get_old_certificate_path(self, conf):
        # 以前设置的获取证书路径
        cert_file_reg = r'#smtpd_tls_cert_file\s*=\s*(.*)'
        cert_key_reg = r'#smtpd_tls_key_file\s*=\s*(.*)'
        cert_tmp = re.search(cert_file_reg, conf)
        if cert_tmp:
            cert_file = cert_tmp.groups(1)[0]
            cert_key = re.search(cert_key_reg, conf).groups(1)[0]
        else:
            cert_key = '/etc/pki/dovecot/private/dovecot.pem'
            cert_file = '/etc/pki/dovecot/certs/dovecot.pem'
        return {'cert_key': cert_key, 'cert_file': cert_file}

    def _set_new_certificate_conf(self, conf, cert_file, cert_key):
        """添加新的证书配置,支持多域名不同证书"""
        # 确保SNI映射配置存在
        sni_reg = r'\ntls_server_sni_maps\s*=(.*)'
        if not re.search(sni_reg, conf):
            conf += '\ntls_server_sni_maps = hash:/etc/postfix/vmail_ssl.map\n'

        # 确保使用单独的smtpd_tls_cert_file和smtpd_tls_key_file配置
        # 这些只作为默认证书,当SNI无法匹配时使用
        cert_reg = r'\nsmtpd_tls_cert_file\s*=(.*)'
        key_reg = r'\nsmtpd_tls_key_file\s*=(.*)'

        if re.search(cert_reg, conf):
            conf = re.sub(cert_reg, '\nsmtpd_tls_cert_file = {}'.format(cert_file), conf)
        else:
            conf += '\nsmtpd_tls_cert_file = {}'.format(cert_file)

        if re.search(key_reg, conf):
            conf = re.sub(key_reg, '\nsmtpd_tls_key_file = {}'.format(cert_key), conf)
        else:
            conf += '\nsmtpd_tls_key_file = {}'.format(cert_key)

        # 移除可能存在的chain_files配置,因为它会覆盖SNI
        chain_reg = r'\nsmtpd_tls_chain_files\s*=(.*)'
        if re.search(chain_reg, conf):
            conf = re.sub(chain_reg, '', conf)

        return conf

    def _set_vmail_certificate(self, args, arecord, cert_file, cert_key):
        """设置证书给某个A记录和域名，完善SNI映射"""
        domain = args.domain
        if args.act == 'add':
            vmail_ssl_map = '/etc/postfix/vmail_ssl.map'
            # 读取现有映射文件
            map_content = ""
            if os.path.isfile(vmail_ssl_map):
                map_content = public.readFile(vmail_ssl_map)
                if map_content is None:
                    map_content = ""

            # 构建域名到证书的映射行
            domain_map_line = '{} {} {}\n'.format(domain, cert_key, cert_file)
            arecord_map_line = '{} {} {}\n'.format(arecord, cert_key, cert_file)

            # 如果该域名已存在映射，则更新它
            if re.search(r'^{}.*$'.format(domain), map_content, re.M):
                map_content = re.sub(r'^{}.*$'.format(domain), domain_map_line.strip(), map_content, flags=re.M)
            else:
                map_content += domain_map_line

            # 如果该A记录已存在映射，则更新它
            if re.search(r'^{}.*$'.format(arecord), map_content, re.M):
                map_content = re.sub(r'^{}.*$'.format(arecord), arecord_map_line.strip(), map_content, flags=re.M)
            else:
                map_content += arecord_map_line

            # 写入映射文件
            public.writeFile(vmail_ssl_map, map_content)
            os.system('postmap -F hash:{}'.format(vmail_ssl_map))
        else:
            # 删除操作
            vmail_ssl_map = '/etc/postfix/vmail_ssl.map'
            if os.path.exists(vmail_ssl_map):
                map_content = public.readFile(vmail_ssl_map)
                if map_content:
                    # 移除该域名和A记录的映射行
                    map_content = re.sub(r'^{}.*$\n?'.format(domain), '', map_content, flags=re.M)
                    map_content = re.sub(r'^{}.*$\n?'.format(arecord), '', map_content, flags=re.M)
                    public.writeFile(vmail_ssl_map, map_content)
                    os.system('postmap -F hash:{}'.format(vmail_ssl_map))

    def _set_dovecot_cert_global(self, cert_file, cert_key, conf):
        default_cert_key = r'ssl_key\s*=\s*<\s*/etc/pki/dovecot/private/dovecot.pem'
        default_cert_file = r'ssl_cert\s*=\s*<\s*/etc/pki/dovecot/certs/dovecot.pem'
        if not re.search(default_cert_file, conf):
            return conf
        conf = re.sub(default_cert_file, "ssl_cert = <{}".format(cert_file), conf)
        conf = re.sub(default_cert_key, "ssl_key = <{}".format(cert_key), conf)
        return conf

    # 修改dovecot的ssl配置
    def _set_dovecot_certificate(self, args, a_record, cert_file, cert_key):
        dovecot_version = self.get_dovecot_version()
        ssl_file = "/etc/dovecot/conf.d/10-ssl.conf"
        ssl_conf = public.readFile(ssl_file)
        if not ssl_conf:
            return public.returnMsg(False, public.lang("Can not find the dovecot configuration file {}",ssl_file))
        # 2.3版本的dovecot要加上ssl_dh配置
        if dovecot_version.startswith('2.3'):
            if args.act == 'add':
                if not os.path.exists('/etc/dovecot/dh.pem') or os.path.getsize('/etc/dovecot/dh.pem') < 300:
                    public.ExecShell('openssl dhparam 2048 > /etc/dovecot/dh.pem')
                if 'ssl_dh = </etc/dovecot/dh.pem' not in ssl_conf:
                    ssl_conf = ssl_conf + "\nssl_dh = </etc/dovecot/dh.pem"
        # 将自签证书替换为用户设置的证书
        reg_cert = r'local_name\s+{}'.format(a_record)
        if args.act == 'add' and not re.search(reg_cert, ssl_conf):
            ssl_conf = self._set_dovecot_cert_global(cert_file, cert_key, ssl_conf)
            domain_ssl_conf = """
#DOMAIN_SSL_BEGIN_%s
local_name %s {
    ssl_cert = < %s
    ssl_key = < %s
}
#DOMAIN_SSL_END_%s""" % (a_record, a_record, cert_file, cert_key, a_record)
            reg = r'ssl\s*=\s*yes'
            ssl_conf = re.sub(reg, 'ssl = yes' + domain_ssl_conf, ssl_conf)
        if args.act == 'delete':
            reg = '#DOMAIN_SSL_BEGIN_{a}(.|\n)+#DOMAIN_SSL_END_{a}\n'.format(a=a_record)
            ssl_conf = re.sub(reg, '', ssl_conf)

        public.writeFile(ssl_file, ssl_conf)
        public.ExecShell('systemctl restart dovecot')

    def _verify_certificate(self, args, path, csrpath, keypath):
        # 验证并写入证书
        # path = '{}/cert/{}/'.format(self.__setupPath, args.domain)
        # csrpath = path + "fullchain.pem"
        # keypath = path + "privkey.pem"
        backup_cert = '/tmp/backup_cert_mail_sys'
        if hasattr(args, "act") and args.act == "add":
            if args.key.find('KEY') == -1: return public.returnMsg(False, public.lang('Private Key ERROR, please check!'))
            if args.csr.find('CERTIFICATE') == -1: return public.returnMsg(False, public.lang('Certificate ERROR, please check!'))
            public.writeFile('/tmp/mail_cert.pl', str(args.csr))
            if not public.CheckCert('/tmp/mail_cert.pl'): return public.returnMsg(False,
                                                                                  public.lang('Certificate ERROR, please paste the correct certificate in pem format!'))
            if os.path.exists(backup_cert): shutil.rmtree(backup_cert)
            if os.path.exists(path): shutil.move(path, backup_cert)
            if os.path.exists(path): shutil.rmtree(path)
            os.makedirs(path)
            public.writeFile(keypath, args.key)
            os.chown(keypath, 0, 0)
            os.chmod(keypath, 0o600)
            public.writeFile(csrpath, args.csr)
            os.chown(csrpath, 0, 0)
            os.chmod(csrpath, 0o600)
        # else:
        #     if os.path.exists(csrpath):
        #         public.ExecShell('rm -rf {}'.format(path))

    def _check_postfix_conf(self):
        result = public.process_exists('master', '/usr/libexec/postfix/master')
        if "ubuntu" in self.sys_v:
            result = public.process_exists('master', '/usr/lib/postfix/sbin/master')
        return result

    def _get_ubuntu_version(self):
        return public.readFile('/etc/issue').strip().split("\n")[0].replace('\\n', '').replace(r'\l',
                                                                                               '').strip().lower()

    def _modify_old_ssl_perameter(self, conf):
        if not os.path.exists('/etc/postfix/vmail_ssl.map'):
            # 注释以前的证书设置
            if '#smtpd_tls_cert_file' not in conf:
                conf = conf.replace('smtpd_tls_cert_file', '#smtpd_tls_cert_file')
                conf = conf.replace('smtpd_tls_key_file', '#smtpd_tls_key_file')
            # 以前设置的获取证书路径
            old_cert_info = self._get_old_certificate_path(conf)
            # 设置新的证书配置和默认TLS配置
            if 'tls_server_sni_maps' not in conf:
                conf = self._set_new_certificate_conf(conf, old_cert_info['cert_file'], old_cert_info['cert_key'])
        public.writeFile(self.postfix_main_cf, conf)

    def _fix_default_cert(self, conf, cert_file, cert_key):
        # 检查并清理chain_files配置
        chain_reg = r'smtpd_tls_chain_files\s*=(.*)'
        chain_found = re.search(chain_reg, conf)

        # 检查标准证书配置
        cert_reg = r'smtpd_tls_cert_file\s*=(.*)'
        key_reg = r'smtpd_tls_key_file\s*=(.*)'
        cert_found = re.search(cert_reg, conf)
        key_found = re.search(key_reg, conf)

        # 判断是否需要更新
        need_update = False

        # 如果存在chain_files配置，需要替换
        if chain_found:
            need_update = True

        # 如果证书配置不完整或是默认证书，需要更新
        if not (cert_found and key_found):
            need_update = True
        elif cert_found and key_found:
            cert_path = cert_found.groups()[0].strip()
            key_path = key_found.groups()[0].strip()
            if 'dovecot.pem' in cert_path or 'dovecot.pem' in key_path:
                need_update = True

        # 进行更新
        if need_update:
            conf = self._set_new_certificate_conf(conf, cert_file, cert_key)
        return conf

    def _set_master_ssl(self):
        master_file = "/etc/postfix/master.cf"
        master_conf = public.readFile(master_file)
        master_rep = r"\n*#\s*-o\s+smtpd_tls_auth_only=yes"
        master_str = "\n  -o smtpd_tls_auth_only=yes"
        master_rep1 = r"\n*#\s*-o\s+smtpd_tls_wrappermode=yes"
        master_str1 = "\n  -o smtpd_tls_wrappermode=yes"
        master_conf = re.sub(master_rep, master_str, master_conf)
        master_conf = re.sub(master_rep1, master_str1, master_conf)
        public.writeFile(master_file, master_conf)

    def set_mail_certificate_multiple(self, args):
        '''
        设置域名的SSL证书
        :param args: domain 要设置证书的域名
        :param args: csr
        :param args: key
        :param args: act add/delete
        :return:
        '''
        conf = public.readFile(self.postfix_main_cf)
        domain = args.domain
        cert_path = '/www/server/panel/plugin/mail_sys/cert/{}'.format(domain)
        cert_file = "{}/fullchain.pem".format(cert_path)
        cert_key = "{}/privkey.pem".format(cert_path)
        if not os.path.exists(cert_path):
            os.makedirs(cert_path)
        # 备份配置文件
        public.back_file(self.postfix_main_cf)

        # conf = self._fix_default_cert(conf, cert_file, cert_key)
        self._modify_old_ssl_perameter(conf)
        # 修改master.cf开启tls/ssl
        self._set_master_ssl()
        # 获取域名的A记录
        domain_info = self.M('domain').where('domain=?', domain).field('a_record').find()
        arecord = domain_info['a_record']
        if arecord == '':
            return public.returnMsg(False, public.lang('The set domain name does not exist'))
        # 验证域名证书是否有效
        if args.csr != '':
            verify_result = self._verify_certificate(args, cert_path, cert_file, cert_key)
            if verify_result:
                return verify_result
        # 将证书配置到vmail_ssl.map
        self._set_vmail_certificate(args, arecord, cert_file, cert_key)
        self._set_dovecot_certificate(args, arecord, cert_file, cert_key)

        public.ExecShell('postmap -F hash:/etc/postfix/vmail_ssl.map && systemctl restart postfix')
        if not self._check_postfix_conf():
            public.restore_file(self.postfix_main_cf)
            public.WriteLog('Mail Server', f'Failed to update the SSL certificate for the domain name [{domain}].')
            return public.returnMsg(False, public.lang('Setup Failed, restore the configuration file now'))
        public.WriteLog('Mail Server', f'Update the SSL certificate for the domain name [{domain}].')
        return public.returnMsg(True, public.lang('Setup Successful'))

    # # 取证书内容 兼容老版本  弃用
    # def get_multiple_certificate(self, domain):
    #     """
    #         @name 获取某个域名的证书内容
    #         @author zhwen<zhw@aapanel.com>
    #         @param domain 需要获取的域名
    #     """
    #     # domain = args.domain
    #     path = '{}/cert/{}/'.format(self.__setupPath, domain)
    #     if not os.path.exists('/etc/redhat-release') and 'debian gnu/linux 10' not in self._get_ubuntu_version():
    #         if 'ubuntu 2' not in self._get_ubuntu_version():
    #             path = '/www/server/panel/plugin/mail_sys/cert/'
    #     csrpath = path + "fullchain.pem"
    #     keypath = path + "privkey.pem"
    #     if not os.path.exists(csrpath):
    #         return {'csr': '', 'key': ''}
    #         # return public.returnMsg(False, 'SSL has not been set up for this domain')
    #     csr = public.readFile(csrpath)
    #     key = public.readFile(keypath)
    #     data = {'csr': csr, 'key': key}
    #     return data

    # 检查ssl状态
    def _get_multiple_certificate_domain_status(self, domain):
        path = '/www/server/panel/plugin/mail_sys/cert/{}/fullchain.pem'.format(domain)
        ssl_conf = public.readFile('/etc/postfix/vmail_ssl.map')
        # if not os.path.exists('/etc/redhat-release') and 'debian gnu/linux 10' not in self._get_ubuntu_version():
        #     if 'ubuntu 2' not in self._get_ubuntu_version():
        #         path = '/www/server/panel/plugin/mail_sys/cert/fullchain.pem'
        if not os.path.exists(path):
            return False
        if not ssl_conf or domain not in ssl_conf:
            return False
        return True

    # 备份配置文件
    def back_file(self, file, act=None):
        """
            @name 备份配置文件
            @author zhwen<zhw@bt.cn>
            @param file 需要备份的文件
            @param act 如果存在，则备份一份作为默认配置
        """
        file_type = "_bak"
        if act:
            file_type = "_def"
        public.ExecShell("/usr/bin/cp -p {0} {1}".format(
            file, file + file_type))

    # 还原配置文件
    def restore_file(self, file, act=None):
        """
            @name 还原配置文件
            @author zhwen<zhw@bt.cn>
            @param file 需要还原的文件
            @param act 如果存在，则还原默认配置
        """
        file_type = "_bak"
        if act:
            file_type = "_def"
        public.ExecShell("/usr/bin/cp -p {1} {0}".format(
            file, file + file_type))

    def enable_catchall(self, args):
        """
            @name 设置邮局捕获不存在的用户邮局并转发到指定邮箱
            @author zhwen<zhw@aapanel.com>
            @param domain 需要捕获的域名
            @param email 不存在的用户将会转发到这个用户
        """
        conf = public.readFile(self.postfix_main_cf)
        catchall_exist = self._get_catchall_status(args.domain)
        domain = '@' + args.domain.strip()
        email = args.email.strip()
        if catchall_exist:
            self.M('alias').where('address=?', domain).delete()
            # 当alias表内无数据时 才能恢复配置
            num = self.M('alias').count()
            new_conf = 'virtual_alias_maps= sqlite:/etc/postfix/btrule.cf'
            if num < 1:
                new_conf = 'virtual_alias_maps = sqlite:/etc/postfix/sqlite_virtual_alias_maps.cf, sqlite:/etc/postfix/sqlite_virtual_alias_domain_maps.cf, sqlite:/etc/postfix/sqlite_virtual_alias_domain_catchall_maps.cf'

        else:

            create_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            self.M('alias').add('address,goto,domain,created,modified,active',
                                (domain, email, args.domain.strip(), create_time, create_time, '1'))
            new_conf = 'virtual_alias_maps= sqlite:/etc/postfix/btrule.cf'
            if public.FileMd5('/etc/postfix/btrule.cf') != 'c96897b9285db8b53f2e1e2358918264':
                public.ExecShell(
                    'wget -O /etc/postfix/btrule.cf {}/mail_sys/postfix/btrule.cf -T 10'.format(public.get_url()))
        conf = re.sub(r'virtual_alias_maps\s*=.*', new_conf, conf)
        public.writeFile(self.postfix_main_cf, conf)
        public.ExecShell('systemctl restart postfix')
        return public.returnMsg(True, public.lang('Setup Successfully'))

    def _add_enable_catchall(self, args):
        """
            @name 设置邮局捕获不存在的用户邮局并转发到指定邮箱
            @author zhwen<zhw@aapanel.com>
            @param domain 需要捕获的域名
            @param email 不存在的用户将会转发到这个用户
        """

        conf = public.readFile(self.postfix_main_cf )
        domain = '@' + args.domain.strip()
        email = args.email.strip()

        create_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self.M('alias').add('address,goto,domain,created,modified,active',
                            (domain, email, args.domain.strip(), create_time, create_time, '1'))

        new_conf = 'virtual_alias_maps= sqlite:/etc/postfix/btrule.cf'
        if public.FileMd5('/etc/postfix/btrule.cf') != 'c96897b9285db8b53f2e1e2358918264':
            public.ExecShell(
                'wget -O /etc/postfix/btrule.cf {}/mail_sys/postfix/btrule.cf -T 10'.format(public.get_url()))
        conf = re.sub(r'virtual_alias_maps\s*=.*', new_conf, conf)
        public.writeFile(self.postfix_main_cf, conf)
        public.ExecShell('systemctl restart postfix')
        return True

    def _get_catchall_status(self, domain):
        """
            @name 获取某个域名下catchall是否开启
            @author zhwen<zhw@aapanel.com>
            @param domain 需要捕获的域名
        """
        domain = '@' + domain.strip()
        conf = public.readFile(self.postfix_main_cf)
        reg = r'virtual_alias_maps\s*=\s*sqlite:/etc/postfix/btrule.cf'
        if not conf:
            return False
        catchall_exist = re.search(reg, conf)
        if not catchall_exist:
            return False
        result = self.M('alias').where('address=?', domain).select()
        if result:
            return True
        return False

    def get_junk_mails(self, args):
        '''
        获取垃圾邮件列表
        :param args:
        :return:
        '''
        import email
        import receive_mail
        reload(receive_mail)

        if 'username' not in args:
            return public.returnMsg(False, public.lang('Please input account name'))
        username = args.username
        if '@' not in username:
            return public.returnMsg(False,public.lang('Invalid account name, for example: xx@example.com'))
        local_part, domain = username.split('@')
        if 'p' not in args:
            args.p = 1
        if 'p=' in args.p:
            args.p = args.p.replace('p=', '')

        receive_mail_client = receive_mail.ReceiveMail()
        mail_list = []
        try:
            dir_path = '/www/vmail/{0}/{1}/.Junk/cur'.format(domain, local_part)
            if os.path.isdir(dir_path):
                # 先将new文件夹的邮件移动到cur文件夹
                new_path = '/www/vmail/{0}/{1}/.Junk/new'.format(domain, local_part)
                if os.path.isdir(new_path):
                    for file in os.listdir(new_path):
                        src = os.path.join(new_path, file)
                        dst = os.path.join(dir_path, file)
                        shutil.move(src, dst)
                files = []
                for fname in os.listdir(dir_path):
                    mail_file = os.path.join(dir_path, fname)
                    if not os.path.exists(mail_file): continue
                    f_info = {}
                    f_info['name'] = fname
                    f_info['mtime'] = os.path.getmtime(mail_file)
                    save_day = self.get_save_day(None)
                    if save_day > 0:
                        deltime = int(time.time()) - save_day * 86400
                        if int(f_info['mtime']) < deltime:
                            os.remove(mail_file)
                            continue
                    files.append(f_info)
                files = sorted(files, key=lambda x: x['mtime'], reverse=True)
                page_data = public.get_page(len(files), int(args.p), 10)
                # 替换掉 href标签里的多余信息 只保留页码
                # pattern =r"href='(/v2)?/plugin.*?\?p=(\d+)'"
                pattern = r"href='(?:/v2)?/plugin.*?\?p=(\d+)'"
                # 使用re.sub进行替换
                page_data['page'] = re.sub(pattern, r"href='\1'", page_data['page'])
                shift = int(page_data['shift'])
                row = int(page_data['row'])
                files = files[shift:shift + row]
                for d in files:
                    mail_file = os.path.join(dir_path, d['name'])
                    encoding = self.get_encoding(mail_file)
                    # if sys.version_info[0] == 2:
                    #     import io
                    #     fp = io.open(mail_file, 'r', encoding=encoding,errors='replace')
                    # else:
                    #     fp = open(mail_file, 'r', encoding=encoding,errors='replace')
                    with open(mail_file, 'rb') as fp:
                        try:
                            # public.writeFile('/tmp/2',str(encoding)+'\n','a+')
                            message = email.message_from_binary_file(fp)
                            mailInfo = receive_mail_client.getMailInfo(msg=message)
                            mailInfo['path'] = mail_file
                            mail_list.append(mailInfo)
                        except:
                            # if sys.version_info[0] == 2:
                            #     import io
                            #     fp = io.open(mail_file, 'rb')
                            # else:
                            #     fp = open(mail_file, 'rb')
                            # try:
                            #     # public.writeFile('/tmp/2',str(encoding)+'\n','a+')
                            #     # message = email.message_from_file(fp)
                            #     try:
                            #         message = email.message_from_binary_file(fp)  # Python 3
                            #     except AttributeError:
                            #         message = email.message_from_file(fp)  # Python 2
                            #     mailInfo = receive_mail_client.getMailInfo(msg=message)
                            #     mailInfo['path'] = mail_file
                            #     mail_list.append(mailInfo)
                            # except:

                            # public.writeFile('/tmp/2', str(
                            # public.get_error_info()) + '\n' + '1111111111111111111111111' + mail_file, 'a+')
                            public.print_log(public.get_error_info())
                            continue
                return {'status': True, 'data': mail_list,
                        # 'page': page_data['page'].replace('/plugin?action=a&name=mail_sys&s=get_junk_mails&p=', '')}
                        'page': page_data['page']}
            else:
                page_data = public.get_page(0, int(args.p), 10)
                return {'status': True, 'data': mail_list,
                        # 'page': page_data['page'].replace('/plugin?action=a&name=mail_sys&s=get_junk_mails&p=', '')}
                        'page': page_data['page']}
        except Exception as e:
            public.print_log(public.get_error_info())
            return public.returnMsg(False, public.lang('Obtaining failure, reason: [{0}]', str(e)))

    def move_to_junk(self, get):
        '''
        将收件箱的邮件标记为垃圾邮件
        :param get:
        :return:
        '''
        if 'username' not in get:
            return public.returnMsg(False, public.lang('Please input account name'))
        username = get.username
        if '@' not in username:
            return public.returnMsg(False, public.lang('Invalid account name, for example: xx@example.com'))
        local_part, domain = username.split('@')

        src = get.path.strip()
        if not os.path.exists('/www/vmail/{0}/{1}/.Junk'.format(domain, local_part)):
            data = self.M('mailbox').where('username=?', username).field('password_encode,full_name').find()
            password = self._decode(data['password_encode'])
            self.create_mail_box(username, password)
        if not os.path.exists(src):
            return public.returnMsg(False, public.lang('Mail path does not exist'))
        dir_path = '/www/vmail/{0}/{1}/.Junk/cur'.format(domain, local_part)
        dst = os.path.join(dir_path, os.path.basename(src))
        shutil.move(src, dst)
        return public.returnMsg(True, public.lang('Mark successful'))

    def move_out_junk(self, get):
        '''
        将垃圾箱的邮件移动到收件箱
        :param get:
        :return:
        '''
        if 'username' not in get:
            return public.returnMsg(False, public.lang('Please input account name'))
        username = get.username
        if '@' not in username:
            return public.returnMsg(False, public.lang('Invalid account name, for example: xx@example.com'))
        local_part, domain = username.split('@')

        src = get.path.strip()
        if not os.path.exists(src):
            return public.returnMsg(False, public.lang('Mail path does not exist'))
        dir_path = '/www/vmail/{0}/{1}/cur'.format(domain, local_part)
        dst = os.path.join(dir_path, os.path.basename(src))
        shutil.move(src, dst)
        return public.returnMsg(True, public.lang('Moved successfully'))

    # 获取SSL证书时间到期时间
    def get_ssl_info(self, domain):

        try:
            import data
            fullchain_file = '/www/server/panel/plugin/mail_sys/cert/{}/fullchain.pem'.format(domain)
            privkey_file = '/www/server/panel/plugin/mail_sys/cert/{}/privkey.pem'.format(domain)
            if not os.path.exists(fullchain_file) or not os.path.exists(privkey_file):
                return {'dns': [domain]}
            os.chown(fullchain_file, 0, 0)
            os.chmod(fullchain_file, 0o600)
            os.chown(privkey_file, 0, 0)
            os.chmod(privkey_file, 0o600)

            ssl_info = data.data().get_cert_end(fullchain_file)
            if not ssl_info:
                return {'dns': [domain]}
            ssl_info['src'] = public.readFile(fullchain_file)
            ssl_info['key'] = public.readFile(privkey_file)
            ssl_info['endtime'] = int(
                int(time.mktime(time.strptime(ssl_info['notAfter'], "%Y-%m-%d")) - time.time()) / 86400)
            return ssl_info
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {'dns': [domain]}

    # 仅支持dns申请
    # 申请证书
    def apply_cert(self, args):
        """
        domains 邮箱域名 ['example.com']
        auth_to CloudFlareDns|email|token 当auth_to 为 dns时是需要手动添加解析
        auto_wildcard = 1
        auth_type = dns
        :param args:
        :return:
        """
        import acme_v2
        domains = json.loads(args.domains)
        apply_cert_module = acme_v2.acme_v2()
        apply_cert = apply_cert_module.apply_cert(domains, 'dns', args.auth_to, auto_wildcard=1)
        return apply_cert

    # 手动验证dns
    def apply_cert_manual(self, args):
        """
        index
        :param args:
        :return:
        """
        import acme_v2
        apply_cert_module = acme_v2.acme_v2()
        return apply_cert_module.apply_cert([], 'dns', 'dns', index=args.index)

    def check_rspamd_route(self, args):
        panel_init = public.readFile("/www/server/panel/BTPanel/__init__.py")
        if "proxy_rspamd_requests" in panel_init:
            return public.returnMsg(True, "")
        return public.returnMsg(False, "")

    @staticmethod
    def change_hostname(args):
        hostname = args.hostname
        rep_domain = r"^(?=^.{3,255}$)[a-zA-Z0-9\_\-][a-zA-Z0-9\_\-]{0,62}(\.[a-zA-Z0-9\_\-][a-zA-Z0-9\_\-]{0,62})+$"
        if not re.search(rep_domain, hostname):
            return public.returnMsg(False, public.lang("Please enter the FQDN (Fully Qualified Domain Name e.g mail.aapanel.com)"))
        public.ExecShell('hostnamectl set-hostname --static {}'.format(hostname))
        h = socket.gethostname()
        if h == hostname:
            return public.returnMsg(True, public.lang("Setup successfully"))
        return public.returnMsg(False, public.lang("Setup failed"))

    def check_init_result(self, args):
        """
        检查安装结果：
        服务状态
        配置文件完整性
        :return:
        """
        result = dict()
        result['missing_file'] = self.check_confile_completeness()
        result['service_status'] = self.get_service_status()
        return result

    def check_confile_completeness(self):
        file_list = public.readFile("{}/services_file.txt".format(self.__setupPath))
        if not file_list:
            return ["%s/services_file.txt|{download_conf_url}/mail_sys" % self.__setupPath]
        file_list = [i for i in file_list.split()]
        missing_files = []
        for file in file_list:
            tmp = public.readFile(file.split('|')[0])
            if not tmp:
                missing_files.append(file)
        return missing_files

    @staticmethod
    def get_init_log(args=None):
        """
        获取初始化日志
        :param args:
        :return:
        """
        logfile = '/tmp/mail_init.log'
        return public.returnMsg(True, public.GetNumLines(logfile, 50))

    @staticmethod
    def check_smtp_port(args):
        """
        检查服务器能否连接其他服务的25端口
        :param args:
        :return:
        """
        domain = args.domain
        rep_domain = r"^(?=^.{3,255}$)[a-zA-Z0-9\_\-][a-zA-Z0-9\_\-]{0,62}(\.[a-zA-Z0-9\_\-][a-zA-Z0-9\_\-]{0,62})+$"
        if not re.search(rep_domain, domain):
            return public.returnMsg(False, public.lang("Please enter the FQDN (Fully Qualified Domain Name e.g smtp.gmail.com),"))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((domain, 25))
        if result == 0:
            return public.returnMsg(True, public.lang("Port 25 is opened"))
        return public.returnMsg(False,
                                public.lang("Cannot connect to port 25 of other services, please contact your hosting provider"))

    def download_file(self, args):
        filename = args.filename
        tmp = filename.split('|')
        local_file = tmp[0]
        remote_file = tmp[1].format(download_conf_url="https://raw.githubusercontent.com/kumaraguru1735/aapanel-pro/main/plugin/mail_sys/mail_conf")
        data = public.readFile("/www/server/panel/plugin/mail_sys/services_file.txt")
        if not data:
            return public.returnMsg(False, public.lang("Get source file error!"))
        if remote_file not in data or local_file not in data:
            return public.returnMsg(False, public.lang("There is no such file!"))
        public.ExecShell(
            "wget {remote_file} -O {local_file} -T 10 --no-check-certificate".format(remote_file=remote_file,
                                                                                     local_file=local_file))
        return public.returnMsg(True, public.lang("Re-download successful"))

    # 邮局-定期，一键检查域名是否被列入垃圾域名    一键检测  刷新检测    定时任务

    # 获取域名是否被列入垃圾域名
    def check_domains_blacklist(self):
        '''
        获取域名是否被列入垃圾域名
        :param
        :return:  dict
        domains_info = {
            'kern123.top':{
                "is_blacklist": False,  # 无黑名单记录
                "blacklist": [],
            },
            'moyumao.top': {
                "is_blacklist": True,   # 有黑名单记录
                "blacklist": ['dnsbl.sorbs.net'],
            },
         }
        '''

        data_list = self.M('domain').order('created desc').field('domain').select()
        domain_list = [item['domain'] for item in data_list]
        domains_info = {}
        cache_key_template = "{}_checkBlacklist"

        for domain in domain_list:
            cache_key = cache_key_template.format(domain)
            cached_result = cache.get(cache_key)
            if cached_result is None:
                cached_result = {"is_blacklist": False, "blacklist": []}
                blacklist_info = self._check_spam_blacklist(domain)
                cached_result.update(blacklist_info)
                cache.set(cache_key, cached_result, 86400)
            domains_info[domain] = cached_result

        return domains_info

    def check_domain_blacklist(self, domain):
        '''
        获取域名是否被列入垃圾域名
        :param
        :return:  dict
        domain_info = {
                "is_blacklist": False,  # 无黑名单记录
                "blacklist": [],
            }
        '''

        cache_key = "{}_checkBlacklist".format(domain)
        cached_result = cache.get(cache_key)
        # 如果缓存中没有结果，进行查询并设置缓存
        if cached_result is None:
            cached_result = self._check_spam_blacklist(domain)
            cache.set(cache_key, cached_result, 86400)
            public.WriteLog('Mail Server', f'Detects if the domain name [{domain}] is listed as a spam domain')
        return cached_result

    # 检测邮箱域名是否被列入垃圾域名(无变化缓存1天  刷新检测重新检测内容)
    def _check_spam_blacklist(self, domain):
        # 常见的DNSBL服务列表，可以根据需要添加更多
        blacklist_services = [
            "zen.spamhaus.org",
            "bl.spamcop.net",
            "dnsbl.sorbs.net",
            "multi.surbl.org",
            "bl.spamcop.net",
            "http.dnsbl.sorbs.net",
            "misc.dnsbl.sorbs.net",
            "socks.dnsbl.sorbs.net",
            "web.dnsbl.sorbs.net",
            "rbl.spamlab.com",
            "cbl.anti - spam.org.cn",
            "httpbl.abuse.ch",
            "virbl.bit.nl",
            "dsn.rfc - ignorant.org",
            "opm.tornevall.org",
            "multi.surbl.org",
            "relays.mail - abuse.org",
            "rbl - plus.mail - abuse.org",
            "rbl.interserver.net",
            "dul.dnsbl.sorbs.net",
            "smtp.dnsbl.sorbs.net",
            "spam.dnsbl.sorbs.net",
            "zombie.dnsbl.sorbs.net",
            "drone.abuse.ch",
            "rbl.suresupport.com",
            "spamguard.leadmon.net",
            "netblock.pedantic.org",
            "blackholes.mail - abuse.org",
            "dnsbl.dronebl.org",
            "query.senderbase.org",
            "csi.cloudmark.com",
            "0spam - killlist.fusionzero.com",
            "0spam.fusionzero.com",
            "access.redhawk.org",
            "all.rbl.jp",
            "all.spam - rbl.fr",
            "all.spamrats.com",
            "aspews.ext.sorbs.net",
            "b.barracudacentral.org",
            "backscatter.spameatingmonkey.net",
            "badnets.spameatingmonkey.net",
            "bb.barracudacentral.org",
            "bl.drmx.org",
            "bl.konstant.no",
            "bl.nszones.com",
            "bl.spamcannibal.org",
            "bl.spameatingmonkey.net",
            "bl.spamstinks.com",
            "black.junkemailfilter.com",
            "blackholes.five - ten - sg.com",
            "blacklist.sci.kun.nl",
            "blacklist.woody.ch",
            "bogons.cymru.com",
            "bsb.empty.us",
            "bsb.spamlookup.net",
            "cart00ney.surriel.com",
            "cbl.abuseat.org",
            "cbl.anti - spam.org.cn",
            "cblless.anti - spam.org.cn",
            "cblplus.anti - spam.org.cn",
            "cdl.anti - spam.org.cn",
            "cidr.bl.mcafee.com",
            "combined.rbl.msrbl.net",
            "db.wpbl.info",
            "dev.null.dk",
            "dialups.visi.com",
            "dnsbl - 0.uceprotect.net",
            "dnsbl - 1.uceprotect.net",
            "dnsbl - 2.uceprotect.net",
            "dnsbl - 3.uceprotect.net",
            "dnsbl.anticaptcha.net",
            "dnsbl.aspnet.hu",
            "dnsbl.inps.de",
            "dnsbl.justspam.org",
            "dnsbl.kempt.net",
            "dnsbl.madavi.de",
            "dnsbl.rizon.net",
            "dnsbl.rv - soft.info",
            "dnsbl.rymsho.ru",
            "dnsbl.sorbs.net",
            "dnsbl.zapbl.net",
            "dnsrbl.swinog.ch",
            "dul.pacifier.net",
            "dyn.nszones.com",
            "dyna.spamrats.com",
            "fnrbl.fast.net",
            "fresh.spameatingmonkey.net",
            "hostkarma.junkemailfilter.com",
            "images.rbl.msrbl.net",
            "ips.backscatterer.org",
            "ix.dnsbl.manitu.net",
            "korea.services.net",
            "l2.bbfh.ext.sorbs.net",
            "l3.bbfh.ext.sorbs.net",
            "l4.bbfh.ext.sorbs.net",
            "list.bbfh.org",
            "list.blogspambl.com",
            "mail - abuse.blacklist.jippg.org",
            "netbl.spameatingmonkey.net",
            "netscan.rbl.blockedservers.com",
            "no - more - funn.moensted.dk",
            "noptr.spamrats.com",
            "orvedb.aupads.org",
            "pbl.spamhaus.org",
            "phishing.rbl.msrbl.net",
            "pofon.foobar.hu",
            "psbl.surriel.com",
            "rbl.abuse.ro",
            "rbl.blockedservers.com",
            "rbl.dns - servicios.com",
            "rbl.efnet.org",
            "rbl.efnetrbl.org",
            "rbl.iprange.net",
            "rbl.schulte.org",
            "rbl.talkactive.net",
            "rbl2.triumf.ca",
            "rsbl.aupads.org",
            "sbl - xbl.spamhaus.org",
            "sbl.nszones.com",
            "sbl.spamhaus.org",
            "short.rbl.jp",
            "spam.dnsbl.anonmails.de",
            "spam.pedantic.org",
            "spam.rbl.blockedservers.com",
            "spam.rbl.msrbl.net",
            "spam.spamrats.com",
            "spamrbl.imp.ch",
            "spamsources.fabel.dk",
            "st.technovision.dk",
            "tor.dan.me.uk",
            "tor.dnsbl.sectoor.de",
            "tor.efnet.org",
            "torexit.dan.me.uk",
            "truncate.gbudb.net",
            "ubl.unsubscore.com",
            "uribl.spameatingmonkey.net",
            "urired.spameatingmonkey.net",
            "virbl.dnsbl.bit.nl",
            "virus.rbl.jp",
            "virus.rbl.msrbl.net",
            "vote.drbl.caravan.ru",
            "vote.drbl.gremlin.ru",
            "web.rbl.msrbl.net",
            "work.drbl.caravan.ru",
            "work.drbl.gremlin.ru",
            "wormrbl.imp.ch",
            "xbl.spamhaus.org",
            "zen.spamhaus.org",
        ]
        is_blacklist = False
        blacklist = []
        for service in blacklist_services:
            try:
                # 构造DNS查询，A记录通常用来表示域名是否在黑名单中
                query_domain = domain + "." + service
                response = dns.resolver.resolve(query_domain, "A")

                # 如果有响应，说明域名在黑名单中
                if response:
                    is_blacklist = True
                    blacklist.append(service)

            except Exception as e:
                pass
                # print(f"查询 {service} 时发生错误: {e}")

        data = {
            "is_blacklist": is_blacklist,
            "blacklist": blacklist,
        }

        return data

    # 获取监控任务状态
    def get_service_monitor_status(self, get):
        c_id = public.M('crontab').where('name=?', u'[Do not delete] Mail Service monitoring').getField('id')
        if not c_id:
            return public.returnMsg(True, False)

        data = public.M('crontab').where('name=?', u'[Do not delete] Mail Service monitoring').find()
        return public.returnMsg(True, data)

     # 创建监控任务
    def create_service_monitor_task(self, get):
        import crontab
        p = crontab.crontab()

        try:

            c_id = public.M('crontab').where('name=?', u'[Do not delete] Mail Service monitoring').getField('id')
            if c_id:
                data = {}
                data['id'] = c_id
                data['name'] = u'[Do not delete] Mail Service monitoring'
                # data['type'] = get.type
                # data['where1'] = get.where1 if 'where1' in get else ''
                data['type'] = 'minute-n'
                data['where1'] = '1'
                data['sBody'] = 'btpython /www/server/panel/plugin/mail_sys/script/monitor_script.py'
                data['backupTo'] = ''
                data['sType'] = 'toShell'
                # data['hour'] = get.hour if 'hour' in get else ''
                # data['minute'] = get.minute if 'minute' in get else ''
                # data['week'] = get.week if 'week' in get else ''
                data['hour'] = ''
                data['minute'] = ''
                data['week'] = ''
                data['sName'] = ''
                data['urladdress'] = ''
                data['save'] = ''
                p.modify_crond(data)
                return public.returnMsg(True, public.lang('Edit successful!'))
            else:
                data = {}
                data['name'] = u'[Do not delete] Mail Service monitoring'
                # data['type'] = get.type
                # data['where1'] = get.where1 if 'where1' in get else ''
                data['type'] = 'minute-n'
                data['where1'] = '1'
                data['sBody'] = 'btpython /www/server/panel/plugin/mail_sys/script/monitor_script.py'
                data['backupTo'] = ''
                data['sType'] = 'toShell'
                # data['hour'] = get.hour if 'hour' in get else ''
                # data['minute'] = get.minute if 'minute' in get else ''
                # data['week'] = get.week if 'week' in get else ''
                data['hour'] = ''
                data['minute'] = ''
                data['week'] = ''
                data['sName'] = ''
                data['urladdress'] = ''
                data['save'] = ''
                p.AddCrontab(data)
                return public.returnMsg(True, public.lang('Setup successful!'))
        except Exception as e:
            public.print_log(public.get_error_info())

    # 打开服务状态监测任务 弃用
    def open_service_monitor_task(self, get):
        import crontab
        p = crontab.crontab()

        try:

            c_id = public.M('crontab').where('name=?', u'[Do not delete] Mail Service monitoring').getField('id')
            if c_id:
                data = {}
                data['id'] = c_id
                data['name'] = u'[Do not delete] Mail Service monitoring'
                # data['type'] = get.type
                # data['where1'] = get.where1 if 'where1' in get else ''
                data['type'] = 'minute-n'
                data['where1'] = '1'
                data['sBody'] = 'btpython /www/server/panel/plugin/mail_sys/script/monitor_script.py'
                data['backupTo'] = ''
                data['sType'] = 'toShell'
                # data['hour'] = get.hour if 'hour' in get else ''
                # data['minute'] = get.minute if 'minute' in get else ''
                # data['week'] = get.week if 'week' in get else ''
                data['hour'] = ''
                data['minute'] = ''
                data['week'] = ''
                data['sName'] = ''
                data['urladdress'] = ''
                data['save'] = ''
                p.modify_crond(data)
                return public.returnMsg(True, public.lang('Edit successful!'))
            else:
                data = {}
                data['name'] = u'[Do not delete] Mail Service monitoring'
                # data['type'] = get.type
                # data['where1'] = get.where1 if 'where1' in get else ''
                data['type'] = 'minute-n'
                data['where1'] = '1'
                data['sBody'] = 'btpython /www/server/panel/plugin/mail_sys/script/monitor_script.py'
                data['backupTo'] = ''
                data['sType'] = 'toShell'
                # data['hour'] = get.hour if 'hour' in get else ''
                # data['minute'] = get.minute if 'minute' in get else ''
                # data['week'] = get.week if 'week' in get else ''
                data['hour'] = ''
                data['minute'] = ''
                data['week'] = ''
                data['sName'] = ''
                data['urladdress'] = ''
                data['save'] = ''
                p.AddCrontab(data)
                return public.returnMsg(True, public.lang('Setup successful!'))
        except Exception as e:
            public.print_log(public.get_error_info())

    # 关闭服务状态监控任务 弃用
    def close_service_monitor_task(self, get):
        import crontab

        p = crontab.crontab()
        c_id = public.M('crontab').where('name=?', u'[Do not delete] Mail Service monitoring').getField('id')
        if not c_id: return public.returnMsg(False, public.lang('task does not exist!'))
        args = {"id": c_id}
        p.DelCrontab(args)
        return public.returnMsg(True, public.lang('Close successful!'))

    # 导出用户
    def export_users(self, get):

        rule_path = '/www/server/panel/data/mail/'
        if not os.path.exists(rule_path):
            os.makedirs(rule_path, exist_ok=True)

        file_name = "All_users_{}".format(int(time.time()))
        # domain = get.get('domain/s', '')
        query = self.M('mailbox').order('created desc').field(
            'full_name,is_admin,username,password,password_encode,maildir,quota,local_part,domain')

        if hasattr(get, 'domain') and get.get('domain/s', '') != '' and get.get('domain/s', '') != 'all':
            domain = get.get('domain/s', '')
            # 导出某域名
            file_name = "{}_users_{}".format(domain, int(time.time()))
            query = self.M('mailbox').where('domain=?', domain).order('created desc').field(
                'full_name,is_admin,username,password,password_encode,maildir,quota,local_part,domain')

        data_list = query.select()

        if not data_list:
            return public.returnMsg(False, public.lang('No user can export'))

        file_path = "{}{}.json".format(rule_path, file_name)
        public.writeFile(file_path, public.GetJson(data_list))
        public.WriteLog('Mail Server', f'Export mailbox users')

        return public.returnMsg(True, file_path)

    # 导入用户
    def import_users(self, get):

        get.file = get.get('file/s', '')

        if not get.file:
            return public.returnMsg(False, public.lang('The file cannot be empty'))

        if not os.path.exists(get.file):
            return public.returnMsg(False, public.lang('File does not exist'))

        try:
            data = public.readFile(get.file)
            data = json.loads(data)
            data.reverse()
        except:
            return public.returnMsg(False, public.lang('Abnormal or malformed file contents'))


        create_successfully = {}
        create_failed = {}

        args = public.dict_obj()
        for item in data:

            if not item:
                continue
            if not item['username'] or not item['password']:
                continue

            try:
                
                args.full_name = item['full_name']
                args.is_admin = item['is_admin']
                args.username = item['username']
                args.password_encrypt = item['password']  # 处理后的
                args.password_encode = item['password_encode']
                args.maildir = item['maildir']
                args.quota = item['quota']
                args.local_part = item['local_part']
                args.domain = item['domain']
                result = self._add_mailbox2(args)
                if result['status']:
                    create_successfully[item['username']] = result['msg']
                    continue
                create_failed[item['username']] = result['msg']
            except Exception as ex:
                public.print_log(traceback.format_exc())
                create_failed[item['username']] = "create error {}".format(ex)

        if create_successfully:
            public.WriteLog('Mail Server', f'Import mailbox user success: {len(create_successfully)}')
            return public.returnMsg(True, public.lang('{} imports were successful',len(create_successfully)))

        return public.returnMsg(True, public.lang('No new email address'))
    # 添加导入的用户
    def _add_mailbox2(self, args):
        '''
        新增邮箱用户  取消存储空间字节转换   取消密码加密(存的就是加密的)
        :param args:
        :return:
        '''

        username = args.username
        # if not self._check_email_address(username):
        #     return public.returnMsg(False, public.lang('Email address format is incorrect'))
        if not username.islower():
            return public.returnMsg(False, public.lang('Email address cannot have uppercase letters!'))
        is_admin = args.is_admin if 'is_admin' in args else 0

        local_part, domain = username.split('@')
        # 检查邮箱数量  查看数量限制
        user_count = self.M('mailbox').where('domain=?', (args.domain,)).count()
        domaincount = self.M('domain').where('domain=?', (args.domain,)).getField("mailboxes")
        if user_count + 1 > domaincount:
            return public.returnMsg(False, public.lang('The number of mailboxes for {} has reached the {} limit',args.domain,
                                                                                                            domaincount))

        domain_list = [item['domain'] for item in self.M('domain').field('domain').select()]
        if domain not in domain_list:
            return public.returnMsg(False, public.lang('The domain name is not in the MailServer {}',domain))

        count = self.M('mailbox').where('username=?', (username,)).count()
        if count > 0:
            return public.returnMsg(False, public.lang('EMAIL EXIST'))

        cur_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.M('mailbox').add(
            'full_name,is_admin,username,password,password_encode,maildir,quota,local_part,domain,created,modified',
            (args.full_name, is_admin, username, args.password_encrypt, args.password_encode, args.username + '/',
             args.quota,
             local_part, args.domain, cur_time, cur_time))

        # 在虚拟用户家目录创建对应邮箱的目录
        user_path = '/www/vmail/{0}/{1}'.format(domain, local_part)
        os.makedirs(user_path)
        os.makedirs(user_path + '/tmp')
        os.makedirs(user_path + '/new')
        os.makedirs(user_path + '/cur')
        maildirsize_path = user_path + '/maildirsize'
        maildirsize_content = f"{int(args.quota)}S\n0 0\n"
        public.writeFile(maildirsize_path, maildirsize_content)
        public.ExecShell('chown -R vmail:mail /www/vmail/{0}/{1}'.format(domain, local_part))
        # 此处密码需要先解密
        password = self._decode(args.password_encode)
        self.create_mail_box(username, password)
        return public.returnMsg(True, public.lang("Add a mailbox user successfully {}",username))


    def check_field_exists(self,db_obj,table_name, field_name):
        """
        @name 检查表字段是否存在
        @param db_obj 数据库对象
        @param table_name 表名
        @param field_name 要检查的字段
        """
        try:
            res = db_obj.query("PRAGMA table_info({})".format(table_name))
            for val in res:
                if field_name == val[1]:
                    return True
        except:pass
        return False


    # 检查字段是否存在 不存在创建
    def check_domain_column(self,):
        """
        @name 检查数据库表或字段是否完整
        """
        with self.M("domain") as obj:
            if not self.check_field_exists(obj, "domain", "a_record"):
                obj.execute('ALTER TABLE `domain` ADD COLUMN `a_record` Text default "";')

            if not self.check_field_exists(obj, "domain", "mailboxes"):
                obj.execute('ALTER TABLE `domain` ADD COLUMN `mailboxes` INT DEFAULT 50;')

            if not self.check_field_exists(obj, "domain", "mailbox_quota"):
                obj.execute('ALTER TABLE `domain` ADD COLUMN `mailbox_quota` BIGINT(20) NOT NULL DEFAULT 5368709120;')

            if not self.check_field_exists(obj, "domain", "quota"):
                obj.execute('ALTER TABLE `domain` ADD COLUMN `quota` BIGINT(20) NOT NULL DEFAULT 10737418240;')

            if not self.check_field_exists(obj, "domain", "rate_limit"):
                obj.execute('ALTER TABLE `domain` ADD COLUMN `rate_limit` INT DEFAULT 12;')
            # ssl告警
            if not self.check_field_exists(obj, "domain", "ssl_alarm"):
                obj.execute('ALTER TABLE `domain` ADD COLUMN `ssl_alarm` INT DEFAULT 0;')
            # 域名使用量
            if not self.check_field_exists(obj, "domain", "current_usage"):
                obj.execute('ALTER TABLE `domain` ADD COLUMN `current_usage` BIGINT(20)  NOT NULL DEFAULT 0;')
        with self.M("mailbox") as obj:
            # 邮箱使用量
            if not self.check_field_exists(obj, "mailbox", "current_usage"):
                obj.execute('ALTER TABLE `mailbox` ADD COLUMN `current_usage` BIGINT(20)  NOT NULL DEFAULT 0;')
            # 配额开关
            if not self.check_field_exists(obj, "mailbox", "quota_active"):
                obj.execute('ALTER TABLE `mailbox` ADD COLUMN `quota_active` tinyint(1) NOT NULL DEFAULT 1;')

        sql2 = '''CREATE TABLE IF NOT EXISTS `email_task` (
          `id` INTEGER  PRIMARY KEY AUTOINCREMENT,    
          `task_name` varchar(255) NOT NULL,        -- 任务名
          `addresser` varchar(320) NOT NULL,        -- 发件人
          `recipient_count` int NOT NULL,           -- 收件人数量
          `task_process` tinyint NOT NULL,     -- 任务进程  0待执行   1执行中  2 已完成
          `pause` tinyint NOT NULL,      -- 暂停状态  1 暂停中     0 未暂停     执行中的任务才能暂停
          `temp_id` INTEGER NOT NULL,          -- 邮件对应id
          `is_record` INTEGER NOT NULL DEFAULT 0,        -- 是否记录到发件箱
          `unsubscribe` INTEGER NOT NULL DEFAULT 0,      -- 是否增加退订按钮   0 没有   1 增加退订按钮
          `threads` INTEGER NOT NULL DEFAULT 0,          -- 线程数量 控制发送线程数 0时自动控制线程   0~10
          `created` INTEGER NOT NULL,
          `modified` INTEGER NOT NULL,
          `active` tinyint(1) NOT NULL DEFAULT 0    --  预留字段
          );'''
        # 增加索引  task_name 和 addresser
        sql_index = '''CREATE INDEX IF NOT EXISTS `task_name_addresser_index` ON `email_task` (`task_name`, `addresser`);'''
        with self.M("") as obj:
            obj.execute(sql2, ())
            obj.execute(sql_index, ())
            # self.M('').execute(sql2, ())

        # 判断存在 /www/vmail目录后再操作 避免新安装的失败
        if os.path.exists('/www/vmail'):
            sql = '''CREATE TABLE IF NOT EXISTS `mail_errlog` (
              `id` INTEGER  PRIMARY KEY AUTOINCREMENT,
              `created` INTEGER NOT NULL,            -- 收件人
              `recipient` varchar(320) NOT NULL,            -- 收件人
              `delay` varchar(320) NOT NULL,            -- 延时
              `delays` varchar(320) NOT NULL,            -- 各阶段延时
              `dsn` varchar(320) NOT NULL,            -- dsn
              `relay` text NOT NULL,                    -- 中继服务器
              `domain` varchar(320) NOT NULL,               -- 域名
              `status` varchar(255) NOT NULL,               -- 错误状态
              `err_info` text NOT NULL,                   -- 错误详情
              UNIQUE(created, recipient)
              );'''

            with self.MD("", "postfixmaillog") as obj2:
                obj2.execute(sql, ())

            # 退订表   退订时间和退订邮箱联合唯一   /www/vmail/mail_unsubscribe.db
            sql = '''CREATE TABLE IF NOT EXISTS `mail_unsubscribe` (
              `id` INTEGER  PRIMARY KEY AUTOINCREMENT,
              `created` INTEGER NOT NULL,
              `recipient` varchar(320) NOT NULL,            -- 收件人
              `etype`  INTEGER NOT NULL DEFAULT 1,           -- 邮件类型id
              `active` tinyint(1) NOT NULL DEFAULT 0,    --  0 取消订阅      1订阅
              `task_id` INTEGER  DEFAULT 0,       -- 群发任务 id  (退订有关联id  订阅没有)
              UNIQUE(etype, recipient)
              );'''
            # 增加索引  etype 和 recipient active
            sql_index = '''CREATE INDEX IF NOT EXISTS `etype_recipient_active_index` ON `mail_unsubscribe` (`etype`, `recipient`, `active`);'''

            with self.MD("","mail_unsubscribe") as obj3:
                aa = obj3.execute(sql, ())
                obj3.execute(sql_index, ())
                #  public.print_log("初始化退订表 --{}".format(aa))

            # 异常用户表
            sql = '''CREATE TABLE IF NOT EXISTS `abnormal_recipient` (
            `id` INTEGER  PRIMARY KEY AUTOINCREMENT,
            `created` INTEGER NOT NULL,               -- 邮件时间 时间戳
            `recipient` varchar(320) NOT NULL,        -- 收件人
            `count` INTEGER NOT NULL,                 -- 次数
            `status` varchar(255) NOT NULL,           -- 状态
            `task_time` INTEGER NOT NULL DEFAULT 0,   -- 任务时间 
            `task_name` varchar(255) NOT NULL,      -- 任务名
            UNIQUE(recipient)
            );'''
            # 增加索引  recipient count status
            sql_index = '''CREATE INDEX IF NOT EXISTS `recipient_count_status_index` ON `abnormal_recipient` (`recipient`, `count`, `status`);'''
            # 增加索引  id status
            sql_index2 = '''CREATE INDEX IF NOT EXISTS `id_status_index` ON `abnormal_recipient` (`id`, `status`);'''
            with self.MD("","abnormal_recipient") as obj4:
                obj4.execute(sql, ())
                obj4.execute(sql_index, ())
                obj4.execute(sql_index2, ())
                # 异常邮箱增加任务关联时间
                if not self.check_field_exists(obj, "abnormal_recipient", "task_time"):
                    obj4.execute('ALTER TABLE `abnormal_recipient` ADD COLUMN `task_time` INTEGER NOT NULL DEFAULT 0;')


        # 邮件日志分析统计表  接收 received, 发送 delivered, 延迟 deferred, 退回 bounced, 拒绝 rejected  25.3.3 已弃用
        sql = '''CREATE TABLE IF NOT EXISTS `log_analysis` (
          `id` INTEGER  PRIMARY KEY AUTOINCREMENT,
          `received` INTEGER NOT NULL DEFAULT 0,        -- 接收
          `delivered` INTEGER NOT NULL DEFAULT 0,       -- 发送
          `deferred` INTEGER NOT NULL DEFAULT 0,        -- 延迟
          `bounced` INTEGER NOT NULL DEFAULT 0,         -- 退回
          `rejected` INTEGER NOT NULL DEFAULT 0,        -- 拒绝
          `time` INTEGER NOT NULL,                    -- 时间  每小时时间戳
           UNIQUE(`time`)    
          );'''
        with self.M("") as obj:
            obj.execute(sql, ())

        # 邮件类型表不存在时创建并插入一条数据
        mail_type_table_str = self.M('sqlite_master').where('type=? AND name=?', ('table', 'mail_type')).find()
        if not mail_type_table_str:
            # 邮件类型表  欢迎邮件 营销邮件
            sql = '''CREATE TABLE IF NOT EXISTS `mail_type` (
              `id` INTEGER  PRIMARY KEY AUTOINCREMENT,
              `mail_type` varchar(320) NOT NULL,            -- 邮件类型
              `created` INTEGER NOT NULL,
              `active` tinyint(1) NOT NULL DEFAULT 0    --  预留字段
              );'''
            with self.M("") as obj:
                obj.execute(sql, ())

            # 插入一条类型
            sql_insert = ''' INSERT INTO `mail_type`(`mail_type`, `created`) VALUES ('Default',  strftime('%s', 'now'));'''
            with self.M("") as obj:
                obj.execute(sql_insert, ())

        # 邮箱自动回复
        sql3 = """CREATE TABLE IF NOT EXISTS `auto_reply` (
            `id` INTEGER  PRIMARY KEY AUTOINCREMENT,
            `username` varchar(255)  NOT NULL,      -- 邮箱
            `full_name` varchar(255) NOT NULL,      --发件人名称
            `domain` varchar(255) NOT NULL,         -- 域名
            `active` tinyint(1) NOT NULL DEFAULT 1, --启用   
            `html` tinyint(1) NOT NULL DEFAULT 1,   --是否html  正文内容是html
            `subject` TEXT,                         --主题
            `content` TEXT,                         --正文
            `interval` INTEGER,                --间隔时间
            `start_time` DATETIME,                  --生效开始时间
            `end_time` DATETIME ,                   --结束时间
            `created` INTEGER NOT NULL,             -- 创建时间
            `modified` INTEGER NOT NULL,
            UNIQUE(`username`)
        );"""

        with self.MD("", "auto_reply") as obj:
            obj.execute(sql3, ())


        # 自动回复记录
        sql4 = """CREATE TABLE IF NOT EXISTS `auto_reply_logs` (
            `id` INTEGER  PRIMARY KEY AUTOINCREMENT,
            `username` varchar(255)  NOT NULL,      -- 发件人
            `addressee` varchar(255)  NOT NULL,      -- 收件人
            `last_time` DATETIME ,                   --上次回复时间
            UNIQUE (`addressee`, `username`)  -- 联合唯一约束
        );"""
        with self.MD("","auto_reply") as obj:
            obj.execute(sql4, ())

        # 多用户表
        sql = '''CREATE TABLE IF NOT EXISTS `domain_user` (
          `id` INTEGER PRIMARY KEY AUTOINCREMENT, -- 自增，主键
          `domain` VARCHAR(24) NOT NULL DEFAULT '', -- 主域名
          `account_id` INTEGER NOT NULL DEFAULT 0, -- 所属用户ID
          `create_time` INTEGER NOT NULL DEFAULT (strftime('%s', 'now')), -- 创建时间
          `updated_time` INTEGER NOT NULL DEFAULT (strftime('%s', 'now')) -- 最后一次修改时间
           );'''
        with self.M("") as obj:
            obj.execute(sql, ())

    def _convert_quota_to_bytes(self, quota):
        num, unit = quota.split()
        if unit == 'GB':
            quota = float(num) * 1024 * 1024 * 1024
        else:
            quota = float(num) * 1024 * 1024
        return quota

    # 新 添加域名
    def add_domain_new(self, args):
        '''
        域名增加接口
        :param args:
        :return:
        '''

        if 'domain' not in args:
            return public.returnMsg(False, public.lang('DOMAIN_NAME'))
        domain = args.domain
        a_record = 'mail.'+domain if hasattr(args, "hash") and args.get('automatic/d', 0) == 1 else args.a_record
        # if not a_record.endswith(domain):
        #     return public.returnMsg(False, public.lang('A record [{}] does not belong to the domain name',a_record))
        # if not self._check_a(a_record):
        #     return public.returnMsg(False, public.lang('A record parsing failed <br>Doamin: {}<br>IP: {}',a_record, self._session['{}:A'.format(a_record)]['value']))

        if self.M('domain').where('domain=?', domain).count() > 0:
            return public.returnMsg(False, public.lang('The domain name already exists'))
        # 邮箱数  邮箱空间   域名空间   每秒几封 全数字类型
        if not hasattr(args, 'mailboxes') or args.get('mailboxes/d', 0) == 0:
            args.mailboxes = 50
        if not hasattr(args, 'mailbox_quota') or args.get('mailbox_quota/s', "") == "":
            args.mailbox_quota = "5 GB"
        if not hasattr(args, 'quota') or args.get('quota/s', "") == "":
            args.quota = "10 GB"
        if not hasattr(args, 'rate_limit') or args.get('rate_limit/d', 0) == 0:
            args.rate_limit = 12


        try:
            mailboxes = args.mailboxes
            rate_limit = args.rate_limit
            mailbox_quota = self._convert_quota_to_bytes(args.mailbox_quota)
            quota = self._convert_quota_to_bytes(args.quota)

            # 通过 添加
            cur_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            try:
                self.M('domain').add('domain,a_record,mailboxes,mailbox_quota,quota,rate_limit,created',
                                     (domain, a_record, mailboxes, mailbox_quota, quota, rate_limit, cur_time))
            except:
                return public.returnMsg(False, 'Mail server did not initialize successfully.<br>'
                                               'Please reopen the plugin to initialize,<br>'
                                               'If the server does not open <br>port 25 [outbound direction]<br>it cannot be initialized.<br> '
                                               'You can run:<br><br> [ telnet gmail-smtp-in.l.google.com 25 ] <br>in the terminal to check whether it is open.')




            # # 增加域名的专属ip地址记录
            # if 'ips' in args:
            #     if args.ips == 'del':
            #         self.remove_domain(domain)
            #     else:
            #         args_addip = public.dict_obj()
            #         args_addip.ip = args.ips
            #         args_addip.domain = a_record # 发件ip
            #         self.add_domainIP_conf(args_addip)


            # 增加 catchAll
            if hasattr(args, 'email') and args.get('email/s', "") != "":
                self._add_enable_catchall(args)
            # 在虚拟用户家目录创建对应域名的目录
            if not os.path.exists('/www/vmail/{0}'.format(domain)):
                os.makedirs('/www/vmail/{0}'.format(domain))
            public.ExecShell('chown -R vmail:mail /www/vmail/{0}'.format(domain))

            # 自动解析
            if hasattr(args, "hash") and args.get('automatic/d', 0) == 1:
                try:
                    import threading
                    from ssl_domainModelV2.service import init_mail_dns
                    # 添加申请证书, 解析,代理, 仅限同域
                    mail_dns_data = {
                        'hash': args.get('hash', ''),
                        'domain': domain,
                    }
                    new_list = [mail_dns_data]
                    task = threading.Thread(target=init_mail_dns, args=(new_list,))
                    task.start()
                    public.set_module_logs("sys_domain", "AddMail_Auto", 1)
                except:
                    public.print_log(public.get_error_info())
                    pass



        except:
            public.print_log(public.get_error_info())

        public.WriteLog('Mail Server', f'Add domain: [{domain}]')
        return public.returnMsg(True, public.lang('Add domain [{}] succeeded!',domain))

    def get_domain_record(self,args):
        '''
        获取域名解析记录--面板模块查询
        :param args:   hash  str  证书
        :param args:   a_record  str  a记录
        :return:
        '''
        if not hasattr(args, "hash") or not hasattr(args, "domain"):
            return public.returnMsg(False, public.lang('Necessary parameters are missing'))
        if args.get('hash', '') and args.get('domain', ''):
            try:
                import threading
                from ssl_domainModelV2.service import get_mail_record
                mail_data = {
                    'hash': args.get('hash', ''),
                    'domain': args.get('domain', ''),
                }
                record_data = get_mail_record(mail_data)

                return record_data

            except:
                public.print_log(public.get_error_info())
                return {}
        else:
            return {}

    # 自动部署已有证书
    def auto_deploy_cert(self,args):
        if not args.get('hash', '') or not args.get('domain', ''):
            return public.returnMsg(False, public.lang('Necessary parameters are missing'))

        hash = args.get('hash', '')
        domain = args.get('domain', '')
        from ssl_domainModelV2.model import DnsDomainSSL
        ssl_info = DnsDomainSSL.objects.filter(hash=hash).first()


        if ssl_info:
            cert_path = ssl_info.path
            if os.path.exists(cert_path):
                key_path = cert_path + '/privkey.pem'
                csr_path = cert_path + '/fullchain.pem'
                csr = public.readFile(csr_path)
                key = public.readFile(key_path)

                try:
                    args = public.dict_obj()
                    args.csr = csr
                    args.key = key
                    args.domain = domain
                    args.act = 'add'
                    self.set_mail_certificate_multiple(args)
                except Exception as e:
                    public.print_log(public.get_error_info())
        else:
            return public.returnMsg(False, public.lang('There is no certificate'))

        public.WriteLog('Mail Server', f'The automatic deployment of the certificate is successful: [{domain}]')
        return public.returnMsg(True, public.lang('The deployment was successful'))

    # 获取域名ssl模块已有证书
    def get_auto_cert(self, args):
        if not args.get('hash', ''):
            return public.returnMsg(False, public.lang('Necessary parameters are missing'))

        hash = args.get('hash', '')

        from ssl_domainModelV2.model import DnsDomainSSL
        ssl_info = DnsDomainSSL.objects.filter(hash=hash).first()
        if ssl_info:
            ssl_info_data = {
                'dns': ssl_info.dns,
                'info': ssl_info.info,
            }
            return ssl_info_data
        else:
            return public.returnMsg(False, public.lang('There is no certificate'))

    # 一键解析域名dns记录
    def auto_resolves_domain(self,args):
        if not args.get('hash', '') or not args.get('domain', ''):
            return public.returnMsg(False, public.lang('Necessary parameters are missing'))

        hash = args.get('hash', '')
        domain = args.get('domain', '')
        from ssl_domainModelV2.model import DnsDomainProvider, DnsDomainSSL


        from class_v2.ssl_domainModelV2.service import create_mail_dns_records
        ssl_obj = DnsDomainSSL.objects.find_one(hash=hash)
        # 获取DNS提供商
        provider = DnsDomainProvider.objects.filter(id=ssl_obj.provider_id).first()

        # 创建DNS记录
        # success = create_mail_dns_records(domain, provider)

        try:
            import threading
            task = threading.Thread(target=create_mail_dns_records, args=(domain, provider))
            task.start()
            public.set_module_logs("sys_domain", "create_mail_dns_records", 1)
        except:
            public.print_log(public.get_error_info())
            pass

        time.sleep(0.5)

        public.WriteLog('Mail Server', f'One-click DNS resolution of domain: [{domain}]')
        return public.returnMsg(True, public.lang("The DNS record is being created and will take effect, please be patient"))


    def update_domain(self, args):
        '''
        域名编辑接口
        :param args:
        :return:
        '''
        if 'domain' not in args:
            return public.returnMsg(False, public.lang('Missing domain'))

        domain = args.domain
        domain_info = self.M('domain').where('domain=?', domain).find()
        if not domain_info:
            return public.returnMsg(False, public.lang('The domain name does not exist'))
        a_record = domain_info['a_record']
        if not hasattr(args, 'rate_limit') or args.get('rate_limit/d', 0) == 0:
            args.rate_limit = 12
        if not hasattr(args, 'mailboxes') or args.get('mailboxes/d', 0) == 0:
            args.mailboxes = 50
        if not hasattr(args, 'mailbox_quota') or args.get('mailbox_quota/s', "") == "":
            args.mailbox_quota = "5 GB"
        if not hasattr(args, 'quota') or args.get('quota/s', "") == "":
            args.quota = "10 GB"

        rate_limit = args.rate_limit
        mailboxes = args.mailboxes
        mailbox_quota = self._convert_quota_to_bytes(args.mailbox_quota)
        quota = self._convert_quota_to_bytes(args.quota)

        try:
            data = {
                "mailboxes": mailboxes,
                "mailbox_quota": mailbox_quota,
                "quota": quota,
                "rate_limit": rate_limit,
            }
            self.M('domain').where('domain=?', domain).update(data)
        except Exception as ex:
            public.print_log(public.get_error_info())


        # 修改cacheall  开启 先删再加   关闭 加
        if hasattr(args, 'email'):
            email_old = self._get_domain_forward(domain)
            if args.get('email/s', "") == "":
                self._deledte_catchall(domain)
                public.ExecShell('systemctl restart postfix')
            else:
                if email_old != args.email:
                    catchall_exist = self._get_catchall_status(args.domain)
                    if not catchall_exist:
                        self.enable_catchall(args)
                    else:

                        self._deledte_catchall(domain)
                        self.enable_catchall(args)
        # 修改专属ip
        if 'ips' in args:
            if args.ips == 'del':
                bb = self.remove_domain(a_record) # 发件ip
                # public.print_log(f'删除  {bb} ')
            else:
                args_addip = public.dict_obj()
                args_addip.ip = args.ips
                args_addip.domain = a_record # 发件ip
                aa = self.add_domainIP_conf(args_addip)
                # public.print_log(f'ddd99  {aa} ')

        return public.returnMsg(True, public.lang('Modified domain [{}] succeeded!',domain))

    # 删除转发
    def _deledte_catchall(self, domain):
        '''
        删除邮件被转发
        :param args:
        :return:
        '''
        try:
            domain = '@' + domain.strip()
            self.M('alias').where('address=?', domain).delete()
            public.WriteLog('Mail Server', f'Deleted catchall configuration for domain [{domain}]')
        except Exception as e:
            public.WriteLog('Mail Server', f'Failed to delete catchall for domain [{domain}]: {str(e)}')


    # 定时分析记录日志到数据库 弃用
    def _mail_logs_task(self, args):

        import crontab
        p = crontab.crontab()
        try:
            c_id = public.M('crontab').where('name=?', u'[Do not delete] Mail Logs').getField('id')

            if not c_id:
                data = {}
                data['name'] = u'[Do not delete] Mail Logs'
                data['type'] = 'minute-n'
                data['where1'] = '10'
                data['sBody'] = 'btpython /www/server/panel/plugin/mail_sys/script/mail_logs.py'
                data['backupTo'] = ''
                data['sType'] = 'toShell'
                data['hour'] = ''
                data['minute'] = ''
                data['week'] = ''
                data['sName'] = ''
                data['urladdress'] = ''
                data['save'] = ''
                p.AddCrontab(data)
                return public.returnMsg(True, public.lang('Setup successful!'))
        except Exception as e:
            public.print_log(public.get_error_info())


    # 获取最新日志详情   弃用
    def mail_log_list(self, args):
        # self._mail_logs_task(None)
        p = int(args.p) if 'p' in args else 1
        rows = int(args.size) if 'size' in args else 10
        callback = args.callback if 'callback' in args else ''
        try:
            count = self.M('email_log').count()
            # 获取分页数据
            page_data = public.get_page(count, p, rows, callback)
            pattern = r"href='(?:/v2)?/plugin.*?\?p=(\d+)'"
            # 使用re.sub进行替换
            page_data['page'] = re.sub(pattern, r"href='\1'", page_data['page'])
            # 获取当前页的数据列表
            data_list = self.M('email_log').order('created desc').limit(
                page_data['shift'] + ',' + page_data['row']).select()
            # 返回数据到前端
            return {'data': data_list, 'page': page_data['page']}
        except Exception as ex:
            public.print_log(public.get_error_info())


    # 添加 roundcube  添加成功后记录路由  修复 只检测nginx服务的问题
    def add_roundcube(self, args):
        is_ok = roundcube_main.get_roundcube_status()
        if isinstance(is_ok, dict) and is_ok['status']:
             return public.returnMsg(False,public.lang("roundcube already exists"))

        if not os.path.exists('/usr/bin/mysql') and not os.path.exists('/www/server/mysql/bin/mysql'):
            return public.returnMsg(False, public.lang('No MySQL service detected, please install it first!'))
        # 检测mysql是否安装
        from panelModelV2.publicModel import main
        get1 = public.dict_obj()
        get1.name = 'mysql'
        mysqlinfo = main().get_soft_status(get1)
        if mysqlinfo['status'] == 0:
            if not mysqlinfo['message']['setup'] or not mysqlinfo['message']['status']:
                return public.returnMsg(False, public.lang('No MySQL service detected, please install it first!'))

        # 查看当前web服务
        webserver = public.GetWebServer()
        if webserver == 'nginx':
            # 检测 nginx
            if not os.path.exists('/etc/init.d/nginx'):
                return public.returnMsg(False, public.lang('No nginx service detected, please install it first!'))
            get2 = public.dict_obj()
            get2.name = 'nginx'
            mysqlinfo = main().get_soft_status(get2)
            if mysqlinfo['status'] == 0:
                if not mysqlinfo['message']['setup'] or not mysqlinfo['message']['status']:
                    return public.returnMsg(False, public.lang('No nginx service detected, please install it first!'))

        # if webserver == 'apache':
        #     ...


        args.dname = 'roundcube'
        if not hasattr(args, 'site_name') or args.get('site_name/s', "") == "":
            return public.returnMsg(False, public.lang('Parameter site_name error'))
        if not hasattr(args, 'php_version') or args.get('php_version/s', "") == "":
            return public.returnMsg(False, public.lang('Parameter php_version error'))
        site_name = args.site_name
        php_version = args.php_version

        # 先添加网站 数据库
        from panel_site_v2 import panelSite

        ps = site_name.replace('.', '_').replace('-', '_')
        data = panelSite().AddSite(public.to_dict_obj({
            'webname': json.dumps({
                'domain': site_name,
                'domainlist': [],
                'count': 0,
            }),
            'type': 'PHP',
            'version': php_version,
            'port': '80',
            'path': '/www/wwwroot/'+site_name,
            'sql': 'MySQL',
            'datauser':  'sql_' + ps,
            'datapassword': public.GetRandomString(16).lower(),
            'codeing': 'utf8mb4',
            'ps': ps,
            'set_ssl': 0,
            'force_ssl': 0,
            'ftp': False,
        }))
        # The site you tried to add already exists
        if int(data.get('status', 0)) != 0:
            return data.get('message', {})['result']

        data = data.get('message', {})

        # 部署 roundcube
        import plugin_deployment_v2
        sysObject = plugin_deployment_v2.plugin_deployment()
        deployment = sysObject.SetupPackage_roundcube(args)
        if not deployment['status']:
            return deployment

        tistamp = int(time.time())
        # 将网址和创建时间写入文件
        roundcube_info = {
            "status": True,
            "id": data['siteId'],
            "site_name": site_name,
            "php_version": php_version,
            "ssl_status": False,
            # "ssl_info": self.get_ssl_info(site_name),
            "timestimp": tistamp,
        }
        path = "/www/server/panel/plugin/mail_sys/roundcube.json"
        public.writeFile(path, json.dumps(roundcube_info))
        return public.returnMsg(True, public.lang('Install successfully'))


    def get_domain(self, args):
        '''
        查询网站
        :param args:
        :return:
        '''

        data_list = public.M('sites').field('id,name,path').select()
        return data_list

    # 添加已有网站到部署信息里
    def add_roundcube_info(self, args):
        if not hasattr(args, 'id') or args.get('id/d', 0) == 0:
            return public.returnMsg(False, public.lang('Parameter id error'))
        if not hasattr(args, 'site_name') or args.get('site_name/s', "") == "":
            return public.returnMsg(False, public.lang('Parameter site_name error'))
        if not hasattr(args, 'path') or args.get('path/s', "") == "":
            return public.returnMsg(False, public.lang('Parameter path error'))

        id = args.get('id/d', 0)
        name = args.get('site_name/s', "")
        path = args.get('path/s', "")
        # /www/wwwroot/webmail.moyumao.top /composer.json
        if path.endswith('/'):
            path = path.rstrip('/')
        cmp_path = path + '/composer.json'
        if not os.path.exists(cmp_path):
            return public.returnMsg(False, public.lang('roundcube is not deployed on this site'))
        info = json.loads(public.readFile(cmp_path))
        # roundcube
        if info['name'].find("roundcube") == -1:
            return public.returnMsg(False, public.lang('roundcube is not deployed on this site'))

        tistamp = int(time.time())
        # 将网址和创建时间写入文件
        roundcube_info = {
            "status": True,
            "id": id,
            "site_name": name,
            "php_version": None,
            "ssl_status": self._get_multiple_certificate_domain_status(name),
            "timestimp": tistamp,
        }
        path = "/www/server/panel/plugin/mail_sys/roundcube.json"
        public.writeFile(path, json.dumps(roundcube_info))

        return public.returnMsg(True, public.lang('Add successfully'))

    # --------------------------------------多域名webmail管理------------------------------------
    def uninstall_roundcube(self, args):
        """ 卸载多域名webmail"""

        data = roundcube_main.uninstall_roundcube(args)
        return data
    def deploy_roundcube(self, args):
        """ 部署多域名webmail"""
        data = roundcube_main.deploy_roundcube(args)
        return data
    def get_roundcube_status(self,args):
        """ 获取多域名webmail状态"""
        data = roundcube_main.get_roundcube_status()
        return data

    # 获取roundcube新配置
    def get_roundcube_config(self, args):
        data = roundcube_main.get_roundcube_config(args)
        return data

    def login_roundcube_multiple(self, args):
        '''
        一键登录 roundcube webmail  适用于多webmail
        :param args: rc_user账号  rc_pass密码
        :return: url
        '''
        roundcube_main = Roundcube_main()
        data = roundcube_main.login_roundcube_multiple(args)

        return data
        
    def recipient_blacklist_open(self, status):
        # 开启 Ture,  关闭 False
        result = public.readFile(self.postfix_main_cf)
        # 没有配置
        if not result:
            return False
        match = re.search(r"smtpd_recipient_restrictions\s*=\s*(.+)", result)
        if not match:
            return False

        if status:
            new_restrictions = 'check_recipient_access hash:/etc/postfix/blacklist,permit_sasl_authenticated, permit_mynetworks, reject_unauth_destination'
            updated_config = re.sub(
                r"smtpd_recipient_restrictions\s*=\s*(.+)",
                f"smtpd_recipient_restrictions = {new_restrictions}",
                result
            )
            public.writeFile(self.postfix_main_cf, updated_config)
        else:
            new_restrictions = 'permit_sasl_authenticated, permit_mynetworks, reject_unauth_destination'
            updated_config = re.sub(
                r"smtpd_recipient_restrictions\s*=\s*(.+)",
                f"smtpd_recipient_restrictions = {new_restrictions}",
                result
            )
            public.writeFile(self.postfix_main_cf, updated_config)
        return True

    # 黑名单状态
    def _recipient_blacklist_status(self):
        # 查看配置是否有黑名单限制
        result = public.readFile(self.postfix_main_cf)

        match = re.search(r"smtpd_recipient_restrictions\s*=\s*(.+)", result)
        if not match:
            return False

        restrictions = match.group(1)
        if 'check_recipient_access hash:/etc/postfix/blacklist' not in restrictions:
            return False
        else:
            return True



    # 收件人黑名单
    def recipient_blacklist(self, args):
        keyword = args.get('keyword/s', '')

        if not keyword or keyword == '':
            keyword = None

        # 判断是否开启黑名单
        if not self._recipient_blacklist_status():
            # return public.returnMsg(False, 'Blacklist is not open')
            return public.returnMsg(True, [])


        # 黑名单文件是否存在
        if not os.path.exists(self.postfix_recipient_blacklist):
            public.writeFile(self.postfix_recipient_blacklist, '')
            public.ExecShell('postmap /etc/postfix/blacklist')

        try:
            with open(self.postfix_recipient_blacklist, 'r') as file:
                emails = file.read().splitlines()
        except Exception as e:
            emails = []

        # 去掉  REJECT
        if emails:
            emails = [email.split()[0] for email in emails]
        else:
            # 黑名单为空 关闭
            st = self.recipient_blacklist_open(False)
            if st:
                public.ExecShell('systemctl reload postfix')
            return public.returnMsg(True, [])

        # 模糊查询匹配的邮箱
        if keyword:
            emails = [email for email in emails if re.search(keyword, email)]

        return public.returnMsg(True, emails)


    # 添加收件人黑名单
    def add_recipient_blacklist(self, args):
        # 收件人列表  一行一个
        if not os.path.exists(self.postfix_recipient_blacklist):
            public.writeFile(self.postfix_recipient_blacklist, '')

        emails_to_add = args.emails_to_add if 'emails_to_add' in args else []
        try:
            emails_to_add = json.loads(args.emails_to_add)
        except:
            pass

        try:

            if not emails_to_add:
                return public.returnMsg(False, public.lang('Parameter emails_to_add error'))

            # 构造要追加的行的集合
            add_set = {f"{email} REJECT\n" for email in emails_to_add}

            try:
                # 读取现有文件内容
                with open(self.postfix_recipient_blacklist, 'r') as file:
                    existing_lines = set(file.readlines())

                # 获取待追加但不重复的邮箱
                new_lines = add_set - existing_lines

                # 将新的行追加到文件
                if new_lines:
                    with open(self.postfix_recipient_blacklist, 'a') as file:
                        file.writelines(new_lines)

            except Exception as e:
                return public.returnMsg(False, e)

            # 未开启黑名单配置 先开启
            if not self._recipient_blacklist_status():
                # 开启
                self.recipient_blacklist_open(True)

            shell_str = '''
            postmap /etc/postfix/blacklist
            systemctl reload postfix
            '''
            public.ExecShell(shell_str)
        except:
            public.print_log(public.get_error_info())

        return public.returnMsg(True, public.lang('Add blacklist successfully'))


    # 删除收件人黑名单
    def del_recipient_blacklist(self, args):
        try:
            emails_to_remove = json.loads(args.emails_to_remove) if 'emails_to_remove' in args else []

            if not emails_to_remove:
                return public.returnMsg(False, public.lang('Parameter emails_to_remove error'))

            remove_set = {f"{email} REJECT\n" for email in emails_to_remove}


            try:
                # 读取现有文件内容
                with open(self.postfix_recipient_blacklist, 'r') as file:
                    lines = file.readlines()

                # 写回不在删除集合中的行
                with open(self.postfix_recipient_blacklist, 'w') as file:
                    for line in lines:
                        if line not in remove_set:
                            file.write(line)

            except Exception as e:
                return public.returnMsg(False, e)

            # 检测黑名单是否为空  为空关闭黑名单
            # if not os.path.exists(self.postfix_recipient_blacklist):
            #     public.writeFile(self.postfix_recipient_blacklist, '')
            filedata = public.readFile(self.postfix_recipient_blacklist)
            if not filedata or filedata == '':
                self.recipient_blacklist_open(False)

            shell_str = '''
            postmap /etc/postfix/blacklist
            systemctl reload postfix
            '''
            public.ExecShell(shell_str)
        except:
            public.print_log(public.get_error_info())
        return public.returnMsg(True, public.lang('The blacklist was deleted'))

    # 导出收件人黑名单
    def export_recipient_blacklist(self,args):

        # 黑名单文件存在
        if not os.path.exists(self.postfix_recipient_blacklist):
            return public.returnMsg(False, public.lang('There are no blacklist files'))

        try:
            with open(self.postfix_recipient_blacklist, 'r') as file:
                emails = file.read().splitlines()
        except Exception as e:
            emails = []

        # 去掉  REJECT
        if emails != []:
            emails = [email.split()[0] for email in emails]
        else:
            return public.returnMsg(False, public.lang('There is no blacklist that can be exported'))
        file_name = 'recipient_blacklist'
        rule_path = '/www/server/panel/data/mail/'
        file_path = "{}{}.json".format(rule_path, file_name)
        public.writeFile(file_path, public.GetJson(emails))
        return public.returnMsg(True, file_path)
    # 导入收件人黑名单
    def import_recipient_blacklist(self,args):
        try:
            file = args.get('file/s', '')

            if not file:
                return public.returnMsg(False, public.lang('The file cannot be empty'))

            if not os.path.exists(file):
                return public.returnMsg(False, public.lang('File does not exist'))

            try:
                data = public.readFile(file)
                data = json.loads(data)
            except Exception as e:
                return public.returnMsg(False, public.lang('Abnormal or malformed file contents: {}', e))
            args.emails_to_add = data
            self.add_recipient_blacklist(args)
            return public.returnMsg(True, public.lang('The blacklist is successfully imported'))
        except:
            public.print_log(public.get_error_info())



    # ---------------------------------------------- 退订管理(新) -----------------------------


    # 获取异常邮件列表  status筛选  search查询
    def get_abnormal_recipient(self, args):
        p = int(args.p) if 'p' in args else 1
        rows = int(args.size) if 'size' in args else 12

        if "search" in args and args.search != "":
            where_str = "recipient LIKE ? OR task_name LIKE ?"
            where_args = (f"%{args.search.strip()}%", f"%{args.search.strip()}%")
        else:
            where_str = "id!=?"
            where_args = (0,)

        if 'status' in args and args.status != "":
            status = args.status
            if where_str and where_args:
                where_str = "status=? AND (recipient LIKE? OR task_name LIKE ?)"

                where_args = (status, f"%{args.search.strip()}%",f"%{args.search.strip()}%")
            else:
                where_str = "status=?"
                where_args = (status,)

            with public.S("abnormal_recipient", "/www/vmail/abnormal_recipient") as obj:
                count = obj.where(where_str, where_args).select()
                data_list = obj.order('created', 'DESC').limit(rows, (p - 1) * rows).where(where_str, where_args).select()

            for i in data_list:
                if i['status'] == 'bounced':
                    i['state'] = 1
                else:
                    i['state'] = 1 if i['count'] >= 3 else 0

            return {'data': data_list, 'total': len(count)}

        else:
            with public.S("abnormal_recipient","/www/vmail/abnormal_recipient") as obj:
                count = obj.where(where_str, where_args).select()
                data_list = obj.order('created', 'DESC').limit(rows, (p - 1) * rows).where(where_str, where_args).select()

            for i in data_list:
                if i['status'] == 'bounced':
                    i['state'] = 1
                else:
                    i['state'] = 1 if i['count'] >= 3 else 0
            # 返回数据到前端
            return {'data': data_list, 'total': len(count)}
        
    def get_abnormal_status(self,args):
        with public.S("abnormal_recipient", "/www/vmail/abnormal_recipient") as obj:
            count = obj.group('status').field('status').select()
        return count



    # 删除数据  批量删  单独删
    def del_abnormal_recipient(self,args):
        try:
            # delnum = 0
            if "ids" in args and args.ids != "":
                ids_list = args.ids.split(',')
                ids_list = [int(id_str) for id_str in ids_list]
                with public.S("abnormal_recipient","/www/vmail/abnormal_recipient.db") as obj:
                    nums = obj.where_in('id', ids_list).column('id')
                    if len(nums) > 0:
                        obj.where_in('id', ids_list).delete()
            public.WriteLog('Mail Server', f'Delete the abnormal mailbox: {len(nums)}')
            return public.returnMsg(True, public.lang('successfully delete'))
        except Exception as e:
            public.WriteLog('Mail Server', f'Failed to delete the abnormal mailbox: {str(e)}')
            return public.returnMsg(False, public.lang('err: {}', e))

    # 清空数据
    def clear_abnormal_recipient(self,args):
        try:

            if "status" in args and args.status != "":
                status = args.status
            else:
                status = 'all'

            if status == 'all':    # 全部删除
                with public.S("abnormal_recipient", "/www/vmail/abnormal_recipient.db") as obj:
                    obj.delete()
            else:
                with public.S("abnormal_recipient", "/www/vmail/abnormal_recipient.db") as obj:
                    nums = obj.where('status', status).delete()
                    # public.print_log('清空 {}个'.format(nums))
            public.WriteLog('Mail Server', f'Clear the abnormal mailbox')
            return public.returnMsg(True, public.lang('Empty {} successfully',type))
        except Exception as e:
            return public.returnMsg(False, public.lang('err: {}', e))

    def _sync_blacklist_to_unsubscribe_db(self):
        # 黑名单列表同步到退订数据库
        # 获取黑名单  构造数据    批量插入数据库  判断数量  关闭黑名单
        if not os.path.exists('/www/vmail'):
            return
        # 判断同步标记
        path = '/www/server/panel/data/mail_sync_black_to_unsubscribe_db.pl'
        if os.path.exists(path):
            return

        recipient_blacklist = []
        if not self._recipient_blacklist_status() or not os.path.exists(self.postfix_recipient_blacklist):
        # if not os.path.exists(self.postfix_recipient_blacklist):
            recipient_blacklist = []
        else:

            try:
                with open(self.postfix_recipient_blacklist, 'r') as file:
                    emails = file.read().splitlines()
            except Exception as e:
                emails = []
            # 去掉  REJECT
            if emails:
                recipient_blacklist = [email.split()[0] for email in emails]

        # 存在黑名单 处理
        if recipient_blacklist:
            created = int(time.time())
            insert_data = []
            for recipient in recipient_blacklist:
                insert_data.append({
                    "created": created,
                    "recipient": recipient,
                    "etype": 0,
                })

            # 邮件类型和收件人唯一 不会重复插入
            with public.S("mail_unsubscribe", "/www/vmail/mail_unsubscribe.db") as obj:
                aa = obj.insert_all(insert_data, option='IGNORE')
            # public.print_log("黑名单列表同步到退订数据库  --{}".format(aa))
        # if aa != len(recipient_blacklist):
            # public.print_log("000黑名单同步不正常  插入--{}   原始--{}".format(aa, len(recipient_blacklist)))

        # 关闭黑名单
        st = self.recipient_blacklist_open(False)
        if st:
            public.ExecShell('systemctl reload postfix')

        # 添加处理标记
        public.writeFile(path, 1)

    # 修改后群发专用退订管理
    def get_unsubscribe_list(self, args):
        '''
        获取退订用户列表
        :param args: etype  邮件类型id
        :param args: search  搜索  收件人
        :param args: active  类型  0退订  1订阅
        :return:
        '''
        p = int(args.p) if 'p' in args else 1
        rows = int(args.size) if 'size' in args else 12
        active = int(args.active) if 'active' in args else 0

        # 构建查询条件
        conditions = ["active=?"]
        params = [active]

        # 添加搜索条件
        if "search" in args and args.search.strip():
            conditions.append("recipient LIKE ?")
            params.append(f"%{args.search.strip()}%")

        # 添加邮件类型条件
        if 'etype' in args and args.etype:
            conditions.append("etype=?")
            params.append(int(args.etype))

        where_str = " AND ".join(conditions)

        # 获取邮件类型映射表（只需获取一次）
        typelist = {str(item["id"]): item["mail_type"] for item in self.get_mail_type_list(None)}

        with public.S("mail_unsubscribe", '/www/vmail/mail_unsubscribe.db') as obj:
            # 获取唯一收件人总数
            count_query = obj.where(where_str, tuple(params)).group('recipient')
            count = len(count_query.select())

            # 获取分页数据
            max_ids = obj.order('created', 'DESC').limit(rows, (p - 1) * rows).where(where_str,
                                                                                     tuple(params)).group(
                'recipient').column('max(id) as max_id')

            # 获取当前页的数据列表
            data_list = obj.where_in('id', max_ids).order('id', 'DESC').select()

            # 优化：批量获取每个收件人的邮件类型
            recipients = [i['recipient'] for i in data_list]
            if recipients:
                # 如果有数据，一次性查询所有收件人的邮件类型
                etype_query = obj.where('active', active).where_in('recipient', recipients).field(
                    'recipient,etype').select()

                # 为每个收件人创建邮件类型映射
                recipient_etypes = {}
                for etype_record in etype_query:
                    recipient = etype_record['recipient']
                    etype = str(etype_record['etype'])

                    if recipient not in recipient_etypes:
                        recipient_etypes[recipient] = []

                    if etype in typelist:
                        recipient_etypes[recipient].append({etype: typelist[etype]})

                # 将邮件类型添加到结果中
                for item in data_list:
                    item['mail_type'] = recipient_etypes.get(item['recipient'], [])

        return {'data': data_list, 'total': count}

    def get_contacts_list(self, args):
        '''
        获取联系人列表 趋势图展示
        :param args: active  类型  0退订  1订阅
        :return:
        '''

        from datetime import datetime
        from dateutil.relativedelta import relativedelta

        active = args.active if 'active' in args else 0

        with public.S("mail_unsubscribe", '/www/vmail/mail_unsubscribe.db') as obj:
            # query = obj.where('active', active).order('created', 'DESC').select()

            # 获取最后12个月的起始时间戳
            current_time = int(time.time())
            twelve_months_ago = current_time - (86400 * 365)  # 大约一年的秒数

            monthly_counts = obj.where('active', active) \
                .where('created > ?', twelve_months_ago) \
                .field("strftime('%Y-%m', datetime(created, 'unixepoch')) as month", 'COUNT(*) as count') \
                .group('month') \
                .order('month', 'desc') \
                .select()

        # 将结果转换为字典，便于查找
        data_dict = {item['month']: item['count'] for item in monthly_counts}

        # 生成最近12个月的月份列表
        current_date = datetime.now()
        months_list = []
        for i in range(11, -1, -1):  # 从11个月前到当前月
            month_date = current_date - relativedelta(months=i)
            months_list.append(month_date.strftime('%Y-%m'))

        # 补全数据，若某个月没有数据，设置count为0
        completed_data = []
        for month in months_list:
            count = data_dict.get(month, 0)
            completed_data.append({'month': month, 'count': count})

        return completed_data

    def complete_monthly_data(self, data, last_month_date):
        """ 补全12个月数据 """
        from datetime import datetime
        from collections import defaultdict
        from dateutil.relativedelta import relativedelta
        # 获取从 last_month_date 向前推12个月的数据
        months_list = []
        for i in range(12):
            # 使用 relativedelta 来往回推 i 个月
            month_date = last_month_date - relativedelta(months=i)  # 按月往回推
            months_list.append(month_date.strftime('%Y-%m'))  # 获取年月，格式 '2024-12'

        # 将原始数据存入一个字典，按月分组
        data_dict = {entry['month']: entry['count'] for entry in data}

        # 补全数据，若某个月没有数据，设置 count 为 0
        completed_data = []
        for month in months_list[::-1]:  # 倒序遍历，确保从最早的月份到最新的月份
            if month in data_dict:
                completed_data.append({'month': month, 'count': data_dict[month]})
            else:
                completed_data.append({'month': month, 'count': 0})

        return completed_data

    def edit_type_unsubscribe_list(self,args):
        """切换联系人的列表类型"""
        etypes_list = []
        recipients_list = []

        if "active" not in args or args.active == "":
            return public.returnMsg(False, public.lang('Missing parameter: active'))
        active = int(args.active)

        # 需要修改的类型
        if "etypes" in args and args.etypes != "":
            etypes_list = args.etypes.split(',')

        # 需要操作的 联系人
        if "recipients" in args and args.recipients != "":
            recipients_list = args.recipients.split(',')
        created = int(time.time())
        try:
            insert_data_alletype = []
            with public.S("mail_unsubscribe", "/www/vmail/mail_unsubscribe.db") as obj:
                # 删除已经存在的退订或订阅
                aa = obj.where('active', active).where_in('recipient', recipients_list).delete()

                for etype in etypes_list:
                    insert_data = []
                    for recipients in recipients_list:
                        insert_data.append({
                            'created': created,
                            'recipient': recipients,
                            'etype': int(etype),
                            'active': active,
                        })

                    insert_data_alletype += insert_data

                num = obj.insert_all(insert_data_alletype, option='IGNORE')

        except Exception as e:
            return public.returnMsg(False, public.lang('err: {}', e))

        return public.returnMsg(True, public.lang('The type changed successfully'))



    def update_subscription_state(self,args):
        """切换订阅退订状态"""
        try:
            if "active" not in args or args.active == "":
                return public.returnMsg(False, public.lang('Missing parameter: active'))
            if "recipient" not in args or args.recipient == "":
                return public.returnMsg(False, public.lang('Missing parameter: recipient'))
            active = int(args.active)
            recipient = args.recipient
            with public.S("mail_unsubscribe","/www/vmail/mail_unsubscribe.db") as obj:
                obj.where('recipient', recipient).update({'active': active})
        except Exception as e:
            return public.returnMsg(False, public.lang('err: {}', e))
        public.WriteLog('Mail Server', f'Toggle the subscription unsubscribe status: [{recipient}]')
        return public.returnMsg(True, public.lang('Success'))

    def del_unsubscribe_list(self,args):
        try:
            if "active" not in args or args.active == "":
                return public.returnMsg(False, public.lang('Missing parameter: active'))
            active = int(args.active)
            if "mails" in args and args.mails != "":
                emails = args.mails.strip().split('\n')
                if len(emails) > 0:
                    with public.S("mail_unsubscribe","/www/vmail/mail_unsubscribe.db") as obj:
                        info = obj.where('active', active).where_in('recipient', emails).delete()
        except Exception as e:
            return public.returnMsg(False, public.lang('err: {}', e))
        active_str = 'unsubscribe' if active == 0 else 'subscribe'
        public.WriteLog('Mail Server', f'Delete {active_str} contact: {len(emails)}')
        return public.returnMsg(True, public.lang('successfully delete'))


    # todo  增加 active
    def add_unsubscribe(self, args):
        # 使用默认邮件类型
        email = args.emails
        etype = int(args.etype)
        emaillist = email.splitlines()
        active = int(args.active)

        try:
            insert_data = []
            for i in emaillist:
                created = int(time.time())
                email = i
                insert_data.append({
                    'created': created,
                    'recipient': email,
                    'etype': etype,
                    'active': active,
                })
            with public.S("mail_unsubscribe", '/www/vmail/mail_unsubscribe.db') as obj:
                num = obj.insert_all(insert_data, option='IGNORE')
                # num = obj.insert_all(insert_data)

            return public.returnMsg(True, public.lang('Add {} unsubscribe lists', num))

        except Exception as e:
            return public.returnMsg(False, public.lang('fail to add {}', e))

    def get_mail_type_list(self, args):
        '''
        获取邮件类型列表
        :param args:
        :return:
        '''


        with self.M('mail_type') as obj:
            data_list = obj.order('created desc').select()

        return data_list

    def get_mail_type_info_list(self, args):
        '''
        获取邮件类型列表
        :param args: search  搜索
        :return:
        '''

        if "search" in args and args.search != "":
            where_str = "mail_type LIKE ?"
            where_args = (f"%{args.search.strip()}%")
        else:
            # 避免空条件报错
            where_str = "id!=?"
            where_args = (0,)
        p = int(args.p) if 'p' in args else 1
        rows = int(args.size) if 'size' in args else 10
        # 获取当前页的数据列表
        with self.M('mail_type') as obj:
            count = obj.order('created desc').where(where_str,where_args).count()
            data_list = obj.order('created desc').where(where_str,where_args).limit(rows, (p - 1) * rows).select()

        with public.S("mail_unsubscribe", '/www/vmail/mail_unsubscribe.db') as obj:
            etypes = obj.where('active', 1).group('etype').field('etype', 'count(*) as `cnt`').select()
            unetypes = obj.where('active', 0).group('etype').field('etype', 'count(*) as `cnt`').select()
        # public.print_log(f'etypes  111 {etypes}')
        etype_cnt = {}
        unetype_cnt = {}
        for i in etypes:
            etype_cnt[str(i['etype'])] = i['cnt']
        for i in unetypes:
            unetype_cnt[str(i['etype'])] = i['cnt']
        
        
        SendMailBulk = bulk.SendMailBulk

        url = SendMailBulk().get_unsubscribe_url()


        for i in data_list:
            i['subscribe_url'] = f"{url}/mailUnsubscribe?action=Subscribe&etype={i['id']}"
            i['subscribers'] = etype_cnt.get(str(i['id']), 0)
            i['unsubscribers'] = unetype_cnt.get(str(i['id']), 0)

        return {'data': data_list, 'total': count}

    # 删除邮件类型 清空并删除
    def del_mail_type_list(self,args):

        # 1 Default分类不能删    分类下有退订邮箱的不能删
        if "ids" in args and args.ids != "":
            ids_list = args.ids.split(',')
            ids_list = [int(id_str) for id_str in ids_list if id_str != '1']

            with public.S("mail_unsubscribe","/www/vmail/mail_unsubscribe.db") as obj:
                obj.where_in('etype', ids_list).delete()


            with public.S("mail_type","/www/vmail/postfixadmin.db") as obj:
                type_names = obj.where_in('id', ids_list).field('mail_type').select()
                type_name_list = [i['mail_type'] for i in type_names]
                obj.where_in('id', ids_list).delete()
        public.WriteLog('Mail Server', f'Delete the mail type: {type_name_list}')
        return public.returnMsg(True, public.lang('Removed successfully'))

    # 修改邮件类型
    def edit_mail_type(self, args):
        id = int(args.id)
        mail_type = args.mail_type

        if id == 1:
            return public.returnMsg(False, public.lang('Default types can be changed'))

        try:
            with self.M('mail_type') as obj:
                info = obj.where('id=?', id).update({"mail_type": mail_type})
            # return public.returnMsg(True, info)
            return public.returnMsg(True, public.lang('Edit success'))
        except Exception as e:
            return public.returnMsg(False, public.lang('err: {}', e))

    # 添加邮件类型
    def add_mail_type(self, args):
        mail_type = args.mail_type
        try:
            created = int(time.time())
            insert = {
                'created': created,
                'mail_type': mail_type,
            }

            with self.M('mail_type') as obj:
                exit = obj.where('mail_type =?', (mail_type,)).count()
                if exit:
                    return public.returnMsg(False, public.lang('This type already exists'))
                obj.insert(insert)
            public.WriteLog('Mail Server', f'Add a message type: {mail_type}')
            return public.returnMsg(True, public.lang('Add successful'))
        except Exception as e:
            return public.returnMsg(False, public.lang('Add failed {}', e))
        
    # 查看指定邮件类型
    def get_mail_type(self, args):
        id = args.id
        try:
            with self.M('mail_type') as obj:
                info = obj.where('id=?', id).find()
            return public.returnMsg(True, info)
        except Exception as e:
            return public.returnMsg(False, public.lang('err: {}', e))





    # ----------------------------------------------  批量发件 --------------------------------
    # 生成批量发件任务的数据库    兼容(如果查不到数据库 就从原始数据库中查
    # def Ms(self, table_name, db_path):
    #     import db
    #     sql = db.Sql()
    #     sql._Sql__DB_FILE = db_path
    #     sql._Sql__encrypt_keys = []
    #     return sql.table(table_name)
    def tables2(self, get):

        # 删除表
        # sql = '''DROP TABLE IF EXISTS `auto_reply`;'''
        # self.M('').execute(sql, ())
        # with self.MD("", "auto_reply") as obj:
        #     obj.execute(sql, ())

        # sql = '''DROP TABLE IF EXISTS `email_task`;'''
        # self.M('').execute(sql, ())
        # sql = '''DROP TABLE IF EXISTS `task_count`;'''
        # self.M('').execute(sql, ())
        # sql = '''DROP TABLE IF EXISTS `mail_unsubscribe`;'''
        # self.M3('').execute(sql, ())
        # sql = '''DROP TABLE IF EXISTS `abnormal_recipient`;'''
        # with self.Ms('', '/www/vmail/abnormal_recipient.db') as obj:
        #     obj.execute(sql, ())
        ...
    def get_task_list(self, args):
        '''
        任务列表
        :param args:
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().get_task_list(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}
    def get_task_all(self, args):
        '''
        获取全部群发任务 无分页
        :param args:
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().get_task_all(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}


    # 查看任务是否要执行 定时任务调用 不改返回
    def check_task_status(self, args):
        '''
        执行发送邮件的定时任务
        :param
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        # 获取服务状态
        service_status = self.get_service_status(None)
        if not service_status['postfix']:
            return False
        # 检测多个 SMTP 服务器的 25 端口是否可用
        if not self._check_smtp_port():
            return False

        try:
            return SendMailBulk().check_task_status(None)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}
    def check_task_status_new(self, args):
        '''
        执行发送邮件的定时任务 -- 执行指定任务
        :param
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        # 获取服务状态
        service_status = self.get_service_status(None)
        if not service_status['postfix']:
            return False
        # 检测多个 SMTP 服务器的 25 端口是否可用
        if not self._check_smtp_port():
            return False
        try:
            return SendMailBulk().check_task_status_new(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}



    #  定时任务调用 不改返回
    def check_task_finish(self, args):
        '''
        发送完毕后处理发送失败的日志
        :param
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().check_task_finish()
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}
    def check_task_finish_new(self, args):
        '''
        发送完毕后处理发送失败的日志  -- 处理指定任务
        :param
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().check_task_finish_new(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}
    def processing_recipient(self, args):
        '''
        导入收件人
        :param  file
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().processing_recipient(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}

    def get_recipient_data(self, args):
        '''
        获取发送预计完成时间
        :param  file
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().get_recipient_data(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}

    def add_task(self, args):
        '''
        添加批量发送任务
        :param args:
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().add_task(args)
        except public.HintException:
            raise
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}

    def pause_task(self, args):
        '''
        暂停发送任务   判断状态为执行中的可以暂停   task_process 1
        :param args: task_id 任务id;   pause 1暂停 0 重启
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().pause_task(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}

    def delete_task(self, args):
        '''
        删除任务
        :param args: task_id 任务id
        :return:
        '''

        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().delete_task(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}

    def get_log_rank(self, args):
        '''
        获取错误排行
        :param args: task_id 任务id
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().get_log_rank(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}

    def get_log_list(self, args):
        '''
        获取错误详情
        :param args: task_id 任务id
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().get_log_list(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}


    # 查看群发邮件的邮件内容/邮件路径
    def get_task_email_content(self, args):

        if 'id' in args and args.id != '':
            id = int(args.id)
        else:
            return public.returnMsg(False, public.lang('The id parameter must be passed!'))


        email_info = self.M('temp_email').where('id=?', id).find()
        if not email_info:
            return public.returnMsg(False, public.lang('The template does not exist'))

        content_path = email_info['content']
        render_path = email_info['render']
        types = email_info['type']
        if os.path.exists(content_path):
            content = public.readFile(content_path)
            # try:
            #     content = json.loads(content)
            # except:
            #     pass
        else:
            content = '{}file does not exist'.format(content_path)

        if types:
            if os.path.exists(render_path):
                render = public.readFile(render_path)
                # try:
                #     content = json.loads(render)
                # except:
                #     pass
            else:
                render = '{} file does not exist'.format(render_path)
        else:
            render = ''

        data = {
            'name': email_info['name'],
            'type': email_info['type'],
            'content_path': content_path,
            'content': content,
            'render_path': render_path,
            'render': render,
        }
        return data

    # 查看任务配置 传任务id
    def get_task_find(self, args):

        if 'id' in args and args.id != '':
            id = int(args.id)
        else:
            return public.returnMsg(False, public.lang('The id parameter must be passed!'))
        # id = 17
        task_info = self.M('email_task').where('id=?', id).find()
        if not isinstance(task_info, dict):
            return public.returnMsg(False, task_info)
        email_info = self.M('temp_email').where('id=?',task_info['temp_id']).find()

        data = {
            "task_info":task_info,
            "email_info":email_info,
        }

        return data


    def update_task(self, args):
        '''
        修改发送任务
        :param args:
        :return:
        '''
        if not self.__check_auth():
            return public.returnMsg(False, public.lang("Sorry. This feature is professional member only."))
        
        
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().update_task(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}

    # 获取当天日志详情
    def get_data_info1(self, args):
        now = datetime.now()

        # 将时间调整为当天的开始时间（零点）
        today_start = datetime(now.year, now.month, now.day)

        start = args.get('start', int(today_start.timestamp()))
        end = args.get('end', start+86400)
        public.print_log(f'start {start} end {end}')

        # 取缓存
        cache_key = 'mail_sys:get_day_errlog_{}'.format(start)
        # 兼容子面板
        if 'domains' in args and args.domains != '':
            cache_key = 'mail_sys:get_day_errlog_{}_{}'.format(args.domains,start)
        cache = public.cache_get(cache_key)
        if cache:
            return cache
        try:

            with self.MD("mail_errlog", "postfixmaillog") as obj2:
                # 兼容子面板
                if 'domains' in args and args.domains != '':
                    query = obj2.order('created desc').where('created >? AND created<?', (start, end)).where('domain in (?)', args.domains).select()
                else:
                    # query1 = obj2.order('created desc').where('created >? AND created<?', (start, end)).count()
                    query = obj2.order('created desc').where('created >? AND created<?', (start, end)).select()


        except:
            public.print_log(public.get_error_info())

        # 缓存
        public.cache_set(cache_key, query, 30*60)

        return query
    def get_data_info(self, args):
        now = datetime.now()
        domain = args.get('domain', None)
        # 将时间调整为当天的开始时间（零点）
        today_start = datetime(now.year, now.month, now.day)

        # 将当天的开始时间转换为时间戳
        start = int(args.get('start', int(today_start.timestamp())))

        end = int(args.get('end', start+86400))
        # 取缓存
        cache_key = 'mail_sys:get_day_errlog_{}'.format(start)

        query = public.S('send_mails').alias('rm').prefix('')
        query.inner_join('senders s', 'rm.postfix_message_id=s.postfix_message_id')
        query.where('s.postfix_message_id is not null')

        if domain is not None:
            query.where('s.sender like ?', '%@{}'.format(domain))


        if start > 0:
            query.where('rm.log_time > ?', start - 1)

        if end > 0:
            query.where('rm.log_time < ?', end + 1)
        query.where('rm.status  !=?', 'sent')
        # query.field('recipient,sender,rm.log_time')

        from power_mta.maillog_stat import query_maillog_with_time_section
        ret = query_maillog_with_time_section(query, start, end)

        # 缓存
        public.cache_set(cache_key, ret, 30*60)

        return ret


    # 弃用
    def _get_errlist(self, timestamp):
        '''
        获取错误详情
        :return:
        '''

        start = int(timestamp)
        end = int(timestamp) + 3599
        # 当前小时以后的不获取   3点半   3-4点v  4-5x
        current_time = int(time.time())
        if current_time < start:
            return []

        # 取缓存
        cache_key = 'mail_sys:get_errlog_{}'.format(timestamp)
        cache = public.cache_get(cache_key)
        if cache:
            return cache
        try:
            with self.MD("mail_errlog", "postfixmaillog") as obj2:
                query = obj2.order('created desc').where('created >? AND created<?', (start, end)).select()
        except:
            public.print_log(public.get_error_info())

        # 缓存
        if current_time > end:
            public.cache_set(cache_key, query, 60*60*24)
        else:
            public.cache_set(cache_key, query, 30*60)

        return query


    # 统计错误日志 弃用
    def task_cut_maillog(self):
        cmd = '''
        if pgrep -f "cut_maillog.py" > /dev/null
        then
            echo "The task [Cut_maillog] is executing"
            exit 1;
        else
            btpython /www/server/panel/plugin/mail_sys/script/cut_maillog.py
        fi
        '''

        import crontab
        p = crontab.crontab()
        try:
            c_id = public.M('crontab').where('name=?', u'[Do not delete] Cut_maillog').getField('id')
            if not c_id:
                data = {}
                data['name'] = u'[Do not delete] Cut_maillog'
                data['type'] = 'hour-n'
                data['where1'] = '1'
                data['sBody'] = cmd
                data['backupTo'] = ''
                data['sType'] = 'toShell'
                data['hour'] = ''
                data['minute'] = '0'
                data['week'] = ''
                data['sName'] = ''
                data['urladdress'] = ''
                data['save'] = ''
                p.AddCrontab(data)
                return public.returnMsg(True, public.lang('Setup successful!'))
            # else:
            #     Cut_maillog = public.M('crontab').where('id=?', c_id).find()
            #     if Cut_maillog['sBody'].find("pgrep -x") == -1:
            #         public.M('crontab').where('id=?', c_id).delete()
        except Exception as e:
            public.print_log(public.get_error_info())

    # 设置邮件取消订阅所用到的域名端口号
    def set_unsubscribe_info(self, args):
        path_info = {}
        if os.path.exists(self.unsubscribe_path):
            path_info = json.loads(public.readFile(self.unsubscribe_path))

        if 'url' in args and args.url != '':
            # 检查访问是否成功
            url =args.url
            td = "{}/userLang?action=get_language".format(url)

            try:
                testdata = public.httpGet(td)
                try:
                    testdata = json.loads(testdata)
                except:
                    pass
                if isinstance(testdata, dict):
                    # public.print_log(testdata['status'])
                    # public.print_log(testdata)

                    if testdata['status'] == 0:

                        path_info['url'] = url
                    else:
                        return public.returnMsg(False, public.lang('The current URL cannot be accessed, please set the reverse proxy correctly!'))
                else:
                    return public.returnMsg(False, public.lang('The current URL cannot be accessed, please set the reverse proxy correctly!'))
            except Exception as e:
                return public.returnMsg(False, e)
        public.writeFile(self.unsubscribe_path,json.dumps(path_info))
        public.set_module_logs('sys_mail', 'set_unsubscribe_info', 1)
        public.WriteLog('Mail Server', f'Set an unsubscribe URL: {url}')

        return public.returnMsg(True, public.lang('Setup successful!'))


    # 查看
    def get_unsubscribe_info(self, args):
        # 面板默认
        ssl_staus = public.readFile('/www/server/panel/data/ssl.pl')
        if ssl_staus:
            ssl = 'https'
        else:
            ssl = 'http'

        ip = public.readFile("/www/server/panel/data/iplist.txt")
        port = public.readFile('/www/server/panel/data/port.pl')
        panel_url = "{}://{}:{}".format(ssl, ip, port)


        if os.path.exists(self.unsubscribe_path):
            path_info = json.loads(public.readFile(self.unsubscribe_path))
            url = path_info.get('url', '')
        else:
            url = ''

        data = {
            "url": url,
            "panel_url": panel_url
        }

        return public.returnMsg(True, data)

    # 删除
    def del_unsubscribe_info(self, args):
        if os.path.exists(self.unsubscribe_path):
            os.remove(self.unsubscribe_path)
            public.WriteLog('Mail Server', f'Delete the unsubscribe URL')

        return public.returnMsg(True, public.lang('successfully delete'))

    def __check_auth(self):
        # 检测是否为专业pro版
        from plugin_auth_v2 import Plugin as Plugin
        plugin_obj = Plugin(False)
        plugin_list = plugin_obj.get_plugin_list()
        # 检测是否为专业永久版
        import PluginLoader
        self.__IS_PRO_MEMBER = PluginLoader.get_auth_state() > 0
        return int(plugin_list["pro"]) > time.time() or self.__IS_PRO_MEMBER

    def modify_domain_quota(self, args):
        if not hasattr(args, "path"):  # /www/vmail/kern123.top
            return public.return_message(-1, 0, public.lang("missing parameter! path"))
        if not hasattr(args, "quota_type"):  # mail
            return public.return_message(-1, 0, public.lang("missing parameter! quota_type"))
        if not hasattr(args, "quota_storage"):
            return public.return_message(-1, 0, public.lang("missing parameter! quota_storage"))

        quota_type = args.quota_type
        if not isinstance(args.quota_storage, dict):
            return public.return_message(-1, 0, public.lang("parameter error! quota_storage"))
        path = args.path
        path = str(path).rstrip("/")
        if not os.path.exists(path):
            return public.return_message(-1, 0, public.lang("The specified directory does not exist"))
        if os.path.isfile(path):
            return public.return_message(-1, 0, public.lang("this is not a valid directory!"))
        if os.path.islink(path):
            return public.return_message(-1, 0, public.lang("The specified directory is a soft link!"))
        if not os.path.isdir(path):
            return public.return_message(-1, 0, public.lang("this is not a valid directory!"))


    def modify_path_quota(self, args):
        # {"path":"/www/wwwroot/aa.dd.com","quota_type":"site",
        # "quota_push":{"module":"","status":false,"size":0,"push_count":0},
        # "quota_storage":{"size":1000}}
        # if not hasattr(args, "path"):  # /www/vmail/kern123.top
        #     return public.return_message(-1, 0, "missing parameter!path")
        # if not hasattr(args, "quota_type"): # mail
        #     return public.return_message(-1, 0, "missing parameter!quota_type")
        # # if not hasattr(args, "quota_push"):
        # #     return public.return_message(-1, 0, "missing parameter!quota_push")
        # if not hasattr(args, "quota_storage"):
        #     return public.return_message(-1, 0, "missing parameter!quota_storage")
        #
        # quota_type = args.quota_type
        # # if not isinstance(args.quota_push, dict):
        # #     return public.return_message(-1, 0, "parameter error! quota_push")
        # if not isinstance(args.quota_storage, dict):
        #     return public.return_message(-1, 0,
        #                                  "parameter error! quota_storage")
        # # if quota_type not in ["site", "ftp", "path"]:
        # #     return public.return_message(-1, 0, "parameter error!quota_type")
        # # if args.quota_push.get("status", False) is True:
        # #     args.quota_push["module"] = args.quota_push.get("module",
        # #                                                     "").strip(",")
        # #     if not args.quota_push["module"]:
        # #         return public.return_message(
        # #             -1, 0, "Please select a push message channel!")
        # path = args.path
        # path = str(path).rstrip("/")
        # public.print_log('path-- {}'.formar(path))
        # if not os.path.exists(path):
        #     return public.return_message(
        #         -1, 0, "The specified directory does not exist")
        # if os.path.isfile(path):
        #     return public.return_message(-1, 0,
        #                                  "this is not a valid directory!")
        # if os.path.islink(path):
        #     return public.return_message(
        #         -1, 0, "The specified directory is a soft link!")
        # if not os.path.isdir(path):
        #     return public.return_message(-1, 0,
        #                                  "this is not a valid directory!")
        path = args.path
        path = str(path).rstrip("/")
        quota_type = args.quota_type
        quota_dict = self.__get_quota_list()

        if quota_dict.get(path) is not None:
            # if quota_dict[path]["quota_type"] == "database":
            #     return public.return_message(
            #         -1, 0, "The path has been set with database quota!")
            quota = quota_dict[path]
            quota["quota_push"]["size"] = int(args.quota_push.get("size", 0))
            quota["quota_push"]["interval"] = int(
                args.quota_push.get("interval", 600))
            quota["quota_push"]["module"] = args.quota_push["module"]
            quota["quota_push"]["push_count"] = int(
                args.quota_push.get("push_count", 3))
            quota["quota_push"]["status"] = args.quota_push.get(
                "status", False)
            quota["quota_storage"]["size"] = int(
                args.quota_storage.get("size", 0))
        else:
            quota = {
                "id": self.__get_quota_id(quota_dict),
                "quota_type": quota_type,
                "quota_push": {
                    "size": int(args.quota_push.get("size", 0)),
                    "interval": int(args.quota_push.get("interval", 600)),
                    "module": args.quota_push.get("module", ""),
                    "push_count": int(args.quota_push.get("push_count", 3)),
                    "status": args.quota_push.get("status", False),
                },
                "quota_storage": {
                    "size": int(args.quota_storage.get("size", 0)),
                },
            }

        if quota["quota_storage"]["size"] > 0:
            disk = self.__get_path_dev_mountpoint(path)
            if disk is None:
                return public.return_message(
                    -1, 0,
                    "The partition where the specified directory is located is not an XFS partition and does not support directory quotas!"
                )

            if "prjquota" not in disk["opts"]:
                msg = '<div class="ftp-verify-disk">The specified xfs partition does not have directory quota enabled. Please add the prjquota parameter when mounting this partition<p>/etc/fstab Example file configuration：</p><pre>{device}       {mountpoint}           xfs             defaults,prjquota       0 0</pre><p>Note: After configuration, the partition needs to be re mounted or the server needs to be restarted to take effect</p></div>'.format(
                    device=disk["device"], mountpoint=disk["mountpoint"])
                return public.return_message(-1, 0, msg)

            if args.quota_storage.get("size", 0) * 1024 * 1024 > disk["free"]:
                return public.return_message(
                    -1, 0,
                    "The quota capacity available for the specified disk is insufficient!"
                )

            res = public.ExecShell(
                "xfs_quota -x -c 'project -s -p {path} {quota_id}'".format(
                    path=path, quota_id=quota["id"]))
            if res[1]:
                return public.return_message(
                    -1, 0, "Quota setting error!{}".format(res[1]))
            res = public.ExecShell(
                "xfs_quota -x -c 'limit -p bhard={size}m {quota_id}' {mountpoint}"
                .format(size=quota["quota_storage"]["size"],
                        quota_id=quota["id"],
                        mountpoint=disk["mountpoint"]))
            if res[1]:
                return public.return_message(
                    -1, 0, "Quota setting error!{}".format(res[1]))

        self.__set_push(quota)

        quota_dict[path] = quota
        public.WriteLog(
            "Quota",
            "Set the quota limit for directory [{path}] to: {size}MB".format(
                path=path, size=quota["quota_storage"]["size"]))
        public.writeFile(self.__SETTINGS_FILE, json.dumps(quota_dict))
        return public.return_message(0, 0, public.lang("Successfully modified"))

    # 处理计划任务重复
    def remove_old_cron(self):
        # 没初始化跳过
        if not os.path.exists('/www/vmail'):
            return
        # 判断删掉标记 如果不存在 就删掉就任务
        path = '/www/server/panel/data/remove_old_mail_cron.pl'
        if os.path.exists(path):
            return
        # 判断已经存在任务
        c_id = public.M('crontab').where('name=?', u'[Do not delete] Cut_maillog').getField('id')
        if not c_id:
            return
        target_list = ['cut_maillog.py', 'send_bulk_script.py', 'mail_error_logs.py']
        cron_jobs = public.ExecShell("crontab -l")
        #要删除的旧任务
        script_path_list = []
        if cron_jobs:
            # 提取cron任务中的所有脚本路径
            script_paths = self.find_script_paths(cron_jobs)

            # 查找每个脚本文件是否包含目标字符串
            for script_path in script_paths:
                if self.search_in_file(script_path, target_list):

                    script_path_list.append(script_path)

        import crontab
        p = crontab.crontab()
        try:
            # 删除多余任务
            for echo_path in script_path_list:
                echo = echo_path.split('/')[-1]

                p.remove_for_crond(echo)
                if os.path.exists(echo_path): os.remove(echo_path)
                sfile = echo_path + '.log'
                if os.path.exists(sfile): os.remove(sfile)
        except:
            pass
        try:
            # 删除
            c_id = public.M('crontab').where('name=?', u'[Do not delete] Checking the sent results').getField('id')
            if c_id:
                a = p.DelCrontab({"id": c_id})

            s_id = public.M('crontab').where('name=?', u'[Do not delete] Sending bulk emails').getField('id')
            if s_id:
                b = p.DelCrontab({"id": s_id})
                # public.print_log("b --{}".format(b))
            m_id = public.M('crontab').where('name=?', u'[Do not delete] Cut_maillog').getField('id')
            if m_id:
                c = p.DelCrontab({"id": m_id})
                # public.print_log("c --{}".format(c))
        except:
            public.print_log(public.get_error_info())

        # 记录删除标记
        public.writeFile(path, "")
        return

    def repair_broken_master_cf_simple(self):
        """
        简单修复：删除所有 '-o' 参数行末尾的 '# !pm' 注释
        仅用于兼容旧版本的一次性修复
        """

        # 没初始化跳过
        if not os.path.exists('/www/vmail'):
            return False

        flag_file = '/www/server/panel/data/repaired_master_cf.lock'
        if os.path.exists(flag_file):
            return False

        try:
            master_cf = '/etc/postfix/master.cf'
            if not os.path.exists(master_cf):
                return False
            with open(master_cf, 'r') as f:
                original_lines = f.readlines()

            new_lines = []
            repaired = False

            for line in original_lines:
                # 检查是否是 -o 开头的参数行，并且包含 # !pm
                if line.strip().startswith('-o ') and '# !pm' in line:
                    # 删除 # !pm 及其前后空格（保留前面的缩进）
                    cleaned_line = line.split('# !pm')[0].rstrip() + '\n'
                    new_lines.append(cleaned_line)
                    repaired = True
                else:
                    new_lines.append(line)

            # 如果有修改，则写回文件
            if repaired:
                with open(master_cf, 'w') as f:
                    f.writelines(new_lines)


                SendMailBulk = bulk.SendMailBulk
                try:
                    return SendMailBulk().apply_changes()
                except Exception as ex:
                    public.print_log(public.get_error_info())
                    return {}

            # else:
            #     public.print_log("master.cf No need to fix, no -o parameter with # !pm found")


            public.writeFile(flag_file, 'repaired at ' + public.format_date())

            return repaired

        except Exception as e:
            public.print_log(f"Fix master.cf failure: {str(e)}")
            return False

    def search_in_file(self, file_path, target_list):
        """检查脚本文件中是否包含目标字符串"""
        if not os.path.exists(file_path):
            return False
        if not os.path.isfile(file_path):  # 检查是否是文件
            return False
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        for target in target_list:
            if target in content:
                return True
        return False

    def find_script_paths(self, cron_jobs):
        """从cron任务中提取出所有的脚本路径"""
        script_paths = []
        lines = cron_jobs[0].split("\n")

        path_pattern = re.compile(r'(/\S+)(?=\s*(?:>>|\s*$))')
        for line in lines:
            if not line:
                continue
            match = path_pattern.search(line)
            if match:
                script_paths.append(match.group(1))

        return script_paths


    def _get_user_quota(self,):
        '''
        获取用户当前额度
        :return:
        '''
        
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk()._get_user_quota()
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}


    def import_contacts(self, args):
        '''
        导入收件人到联系人列表(新增分组)
        :param  file        str (收件人文件名)
        :param  etypes      str (联系人类型  多个逗号隔开)  多选分类  每个分类都导入
        :param  active      int (0 退订    1订阅)  暂不使用,默认订阅类型
        :return:
        '''
        
        
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().import_contacts(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}
    def import_contacts_etypes(self, args):
        '''
        导入收件人到联系人列表  (选择分组 导入文件)
        :param  file        str (收件人文件名)
        :param  etypes      str (联系人类型  多个逗号隔开)  多选分类  每个分类都导入
        :param  active      int (0 退订    1订阅)  暂不使用,默认订阅类型
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().import_contacts_etypes(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}
    def import_contacts_from_content(self, args):
        '''
        导入收件人到联系人列表
        :param  file        str (收件人文件名)
        :param  etypes      str (联系人类型  多个逗号隔开)  多选分类  每个分类都导入
        :param  active      int (0 退订    1订阅)  暂不使用,默认订阅类型
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().import_contacts_from_content(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}
    def get_email_temp_list(self, args):
        '''
        邮件模版列表
        :param
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().get_email_temp_list(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}

    def get_email_temp_render(self, args):
        '''
        邮件模版列表
        :param
        :return:
        '''

        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().get_email_temp_render(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}
    def get_email_temp(self, args):
        '''
        邮件模版
        :param
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().get_email_temp(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}
    def add_email_temp(self, args):
        '''
        添加邮件模版
        :param
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().add_email_temp(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}

    def del_email_temp(self, args):
        '''
        删除邮件模版
        :param
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().del_email_temp(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}

    def edit_email_temp(self, args):
        '''
        编辑邮件模版
        :param
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().edit_email_temp(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}


    # 检测域名是否在黑名单
    def check_blacklists(self, args):
        '''
        检测域名是否在黑名单
        :param
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().check_blacklists(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}


    # 设置忽略提示
    def Blacklist_tips(self, args):
        '''
        操作黑名单提示横幅
        :param operation  (-1 忽略   >0 已处理)
        :return:
        '''
        path = self.blacklist_tips
        operation = str(args.operation)

        # 测试用
        if operation == '0':
            if os.path.exists(path):
                # public.print_log('删除标记')
                os.remove(path)
                return public.returnMsg(True, public.lang("The operation succeeded"))

        if operation == '-1':
            oper = -1
        else:
            oper = int(time.time())
        public.writeFile(path, str(oper))
        return public.returnMsg(True, public.lang("The operation succeeded"))

    # 获取忽略提示设置
    def get_blacklist_tips(self, args):
        '''
        获取操作黑名单提示横幅处理状态 -1 忽略  0 未操作   >0 已处理
        :param
        :return:
        '''
        path = self.blacklist_tips
        if os.path.exists(path):
            data = public.readFile(path)
            if not data:
                data = 0
        else:
            data = 0


        blcheck_count = f'/www/server/panel/plugin/mail_sys/data/blcheck.json'  # 统计各个域名黑名单情况

        if os.path.exists(blcheck_count):
            blcheck_ = public.readFile(blcheck_count)
            try:
                blcheck_ = json.loads(blcheck_)
            except:
                pass
            count = sum(info["blacklisted"] for info in blcheck_.values())
        else:
            count = 0

        res = {
            'status' : data,
            'count': count,
        }

        return res

    def _get_alarm_black_switch(self):
        '''
        获取自动检测黑名单告警开关
        :param
        :return:
        '''

        endtime = public.get_pd()[1]
        curtime = int(time.time())
        if endtime != 0 and endtime < curtime:
            # 无专业版或永久版
            return False
        else:
            path = self.blacklist_alarm_switch
            if os.path.exists(path):
                return False
            else:
                return True

    def _get_abnormal_mail_check_switch(self):
        '''
        获取自动检测异常邮箱开关
        :param
        :return:
        '''

        endtime = public.get_pd()[1]
        curtime = int(time.time())
        if endtime != 0 and endtime < curtime:
            # 无专业版或永久版
            return False
        else:
            path = self.abnormal_mail_check_switch
            if os.path.exists(path):
                return False
            else:
                return True


    def set_alarm_black_switch(self, args):
        '''
        设置自动检测黑名单告警开关
        :param  type str     'black'
        :return:
        '''
        operation = str(args.operation)

        endtime = public.get_pd()[1]
        curtime = int(time.time())
        if endtime != 0 and endtime < curtime:
            return public.returnMsg(False, public.lang('This feature is exclusive to the Pro version'))

        # 检查文件(存在关)
        path = self.blacklist_alarm_switch
        if operation == '1':
            if os.path.exists(path):
                os.remove(path)
        # 关
        else:
            public.writeFile(path, '1')
        operation_str = 'Open' if operation == '1' else 'Close'
        public.set_module_logs('sys_mail', 'set_alarm_black_switch', 1)
        public.WriteLog('Mail Server', f'{operation_str} Blacklist alerts')
        return public.returnMsg(True, public.lang("The operation succeeded"))


    def set_abnormal_mail_check_switch(self, args):
        '''
        设置异常邮箱检查开关
        :param  operation
        :return:
        '''
        operation = str(args.operation)

        endtime = public.get_pd()[1]
        curtime = int(time.time())
        if endtime != 0 and endtime < curtime:
            return public.returnMsg(False, public.lang('This feature is exclusive to the Pro version'))

        # 检查文件(存在关)
        path = self.abnormal_mail_check_switch
        if operation == '1':  # 开启
            if os.path.exists(path):
                os.remove(path)
        # 关
        else:
            public.writeFile(path, '1')
        operation_str = 'Open' if operation == '1' else 'Close'
        public.WriteLog('Mail Server', f'{operation_str} Abnormal mailbox checks')
        public.set_module_logs('sys_mail', 'set_abnormal_mail_check_switch', 1)
        return public.returnMsg(True, public.lang("The operation succeeded"))


    def get_alarm_send(self, args):
        '''
        获取服务掉线监控告警任务
        :param
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().get_alarm_send(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}

    # 导出 邮件模版
    def export_email_template(self, args):
        '''
        导出邮件模版
        :param
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().export_email_template(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}


    # 导入 邮件模版
    def import_email_template(self, args):
        '''
        导入邮件模版
        :param
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().import_email_template(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}
    def copy_template(self, args):
        '''
        复制邮件模版
        :param
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().copy_template(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}

    # ---------------------------------------- 订阅 合并分组-------------------------------------------------------

    # 联系人分组导出
    def export_contact_group(self, args):
        '''
        导出联系人分组
        :param
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().export_contact_group(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}

    def import_contact_group(self, args):
        '''
        导入联系人分组
        :param
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().import_contact_group(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}

    def merge_groups(self, args):
        '''
        合并联系人分组
        :param
        :return:
        '''
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().merge_groups(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}
    def read_blacklist_scan_log(self, args):
        '''
        读取黑名单扫描日志
        :param
        :return:
        '''
        if not os.path.exists(args.path):
                return public.return_message(-1, 0, public.lang("Configuration file not exist"))
        if os.path.isdir(args.path):
            return public.return_message(-1, 0, public.lang("Writing verification file failed: {}"))

        import files
        f = files.files()
        public.set_module_logs('sys_mail', 'read_blacklist_scan_log', 1)
        return f.GetFileBody(args)

    def get_contact_number(self, args):
        '''
        获取多个分组下的收件人数量
        :param   str  etypes  分组类型   1,3,4
        :return: int  数量
        '''
        if not hasattr(args, 'etypes') or args.get('etypes', '') == '':
            return 0
        else:
            etypes = args.etypes

        etype_list = etypes.split(',')

        with public.S("mail_unsubscribe", '/www/vmail/mail_unsubscribe.db') as obj:
            email_list = obj.where_in('etype', etype_list).where('active', 1).select()
        emails = [i['recipient'] for i in email_list]
        # 不同组有相同邮件 去重
        count = len(list(set(emails)))

        return count

    def get_task_unsubscribe_list(self,args):
        """ 获取营销任务 退订详情列表 """
        p = int(args.p) if 'p' in args else 1
        rows = int(args.size) if 'size' in args else 12

        task_id = args.get('task_id', '')
        if not task_id:
            return public.return_message(-1, 0, public.lang("The required id parameter is missing"))
        with public.S("mail_unsubscribe", '/www/vmail/mail_unsubscribe.db') as obj:
            count = obj.where('task_id', task_id).select()
            # 获取不重复数据
            data1 = obj.order('created', 'DESC').where('active', 0).limit(rows, (p - 1) * rows).where('task_id', task_id).group('recipient').select()
            # 获取最新时间
            data2 = obj.order('created', 'DESC').where('active', 0).limit(rows, (p - 1) * rows).where('task_id', task_id).select()
            result = {}

            data = data1 + data2
            # 遍历合并后的数据
            for entry in data:
                recipient = entry['recipient']
                created = entry['created']

                # 如果该 recipient 不在结果中，或者当前的 created 更大，则更新
                if recipient not in result or created > result[recipient]['created']:
                    result[recipient] = entry

            # 将结果转换为列表
            data = list(result.values())

        return {'data': data, 'total': len(count)}

    # --------------------------------------------- 域名专属ip -----------------------------------------------------
    def _get_domainIP_conf(self,):
        '''
        获取域名专属ip配置
        '''
        
        
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk()._get_domainIP_conf()
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}
    def remove_domain(self, domain):
        '''
        删除域名专属ip配置
        '''
        
        
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().remove_domain(domain)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}
    def add_domainIP_conf(self, args):
        '''
        添加域名专属ip配置
        '''

        # 校验参数
        try:
            args.validate([
                Param('ip').Require().String().Ip(),
                Param('domain').Require().String().Host(),
            ], [
                public.validate.trim_filter(),
            ])
        except Exception as ex:
            public.print_log("error info: {}".format(ex))
            return public.return_message(-1, 0, str(ex))

        
        
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().add_domainIP_conf(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}


#  ----------------------------------------------- 自动回复 -------------------------------------------------------
    def get_auto_reply_email(self, args):
        """ 获取自动回复邮箱  """

        p = int(args.p) if 'p' in args else 1
        rows = int(args.size) if 'size' in args else 12
        where_conditions = []
        where_args = []
        
        # 搜索条件
        if "search" in args and args.search != "":
            where_conditions.append("username LIKE ?")
            where_args.append(f"%{args.search.strip()}%")
        
        # 域名筛选
        if "domain" in args and args.domain:
            where_conditions.append("domain = ?")
            where_args.append(args.domain.strip())
        # 组合 where 条件
        where_str = " AND ".join(where_conditions) if where_conditions else "1=1"
        with public.S("auto_reply", self.db_files['auto_reply']) as obj:
            count = obj.where(where_str, tuple(where_args)).select()
            data_list = obj.order('created', 'DESC').limit(rows, (p - 1) * rows).where(where_str, tuple(where_args)).select()
        # 返回邮件内容
        for i in data_list:
            i['content'] = public.readFile(i['content'])

        return {'data': data_list, 'total': len(count)}

   
    def create_auto_reply_email(self, args):
        """ 创建自动回复邮箱  """

        username = args.username    # 必须存在   后续不存在创建
        full_name = args.full_name  # 用户名
        # domain = args.domain        # 必须存在
        subject = args.subject
        content_info = args.content  # 回复内容 路径 必须存在

        active = int(args.get('active', 1))  # 活跃账号
        interval = int(args.get('interval', 36400))  # 间隔时间
        start_time = int(args.get('start_time', 0))  # 开始时间
        end_time = int(args.get('end_time', -1))  # 结束时间
        local_part, domain = username.split('@')


        # 判断域名
        domain_list = self.get_domain_name(None)
        if domain not in domain_list:
            return public.returnMsg(False, public.lang('The domain name is not in the MailServer {}',domain))

        # 判断用户
        with self.M('mailbox') as obj_mailbox:
            count = obj_mailbox.where('username=?', (username,)).count()
        if not count:
            return public.returnMsg(False, public.lang('The email account already exists'))

        # 存放正文
        content = f'/www/server/panel/data/mail/auto_reply/{domain}/{local_part}_content'
        if not os.path.exists(f'{self.auto_reply_path}/{domain}'):
            os.makedirs(f'{self.auto_reply_path}/{domain}')
        public.writeFile(content, content_info)

        cur_time = int(time.time())
        insert_data = {}
        insert_data["username"] = username
        insert_data["full_name"] = full_name
        insert_data["domain"] = domain
        insert_data["subject"] = subject
        insert_data["content"] = content
        insert_data["active"] = active
        insert_data["interval"] = interval
        insert_data["start_time"] = start_time
        insert_data["end_time"] = end_time
        insert_data["html"] = 1
        insert_data["created"] = cur_time
        insert_data["modified"] = cur_time
        # 检测是否存在
        with public.S("auto_reply", self.db_files['auto_reply']) as obj:
            count = obj.where('username', username).count()
            if count:
                return public.returnMsg(False, public.lang('The email account already exists'))
            else:
                count = obj.insert(insert_data)
        public.WriteLog('Mail Server', f'Create an autoresponder mailbox: [{username}] ')
        return public.returnMsg(True, public.lang('Create successfully'))

    # 修改自动回复
    def update_auto_reply_email(self, args):
        public.exists_args('username', args)

        username = args.username
        local_part, domain = username.split('@')

        # 更新回复内容
        if args.get('content', "") != "":
            content_info = args.content  # 回复内容
            content = f'/www/server/panel/data/mail/auto_reply/{domain}/{local_part}_content'
            public.writeFile(content, content_info)
            public.WriteLog('Mail Server', f'Change autoreply email: [{username}] reply content successful')

        cur_time = int(time.time())
        upd_data = {}

        if args.get('full_name', "") != "":
            upd_data["full_name"] = args.full_name
        if args.get('subject', "") != "":
            upd_data["subject"] = args.subject

        if args.get('active', "") != "":
            upd_data["active"] = int(args.active)
        if args.get('interval', "") != "":
            upd_data["interval"] = int(args.interval)
        if args.get('start_time', "") != "":
            upd_data["start_time"] = int(args.start_time)
        if args.get('end_time', "") != "":
            upd_data["end_time"] = int(args.end_time)

        upd_data["modified"] = cur_time

        with public.S("auto_reply", self.db_files['auto_reply']) as obj:
            obj.where('username', username).update(upd_data)
        public.WriteLog('Mail Server', f'Modify the auto-reply email address: [{username}]')
        return public.returnMsg(True, public.lang('Edit successful'))

    # 删除自动回复
    def delete_auto_reply_email(self, args):

        username = args.username
        local_part, domain = username.split('@')
        content = f'/www/server/panel/data/mail/auto_reply/{domain}/{local_part}_content'
        if os.path.exists(content):
            os.remove(content)

        with public.S("auto_reply", self.db_files['auto_reply']) as obj:
            obj.where('username', username).delete()
        public.WriteLog('Mail Server', f'Delete the autoresponder mailbox: [{username}]')
        return public.returnMsg(True, public.lang('Delete successful'))

    # 查看回复记录
    def get_auto_reply_logs(self, args):
        """ 获取自动回复的记录  """

        p = int(args.p) if 'p' in args else 1
        rows = int(args.size) if 'size' in args else 12

        if "search" in args and args.search != "":
            where_str = "username LIKE ? OR addressee LIKE ?"
            where_args = (f"%{args.search.strip()}%", f"%{args.search.strip()}%")
        else:
            # 避免空条件报错
            where_str = "1 =?"
            where_args = (1,)

        with public.S("auto_reply_logs", self.db_files['auto_reply']) as obj:
            count = obj.where(where_str, where_args).select()
            data_list = obj.order('last_time', 'DESC').limit(rows, (p - 1) * rows).where(where_str, where_args).select()

            return {'data': data_list, 'total': len(count)}

    # 获取生效期内的自动回复邮箱[ 邮箱 主题 内容 间隔时间] (启用状态  生效时间内 )
    def _get_auto_reply_email(self,):
        """ 获取生效期内的自动回复邮箱  """
        cur_time = int(time.time())
        query = public.S('auto_reply', self.db_files['auto_reply'])

        query.where('active', 1)
        query.where('start_time < ?', cur_time)
        query.where('end_time > ? OR  end_time =?', (cur_time, -1))  # -1 永不结束
        data = query.order('created', 'DESC').select()
        return data

    # 获取最新回复时间  作为上次时间
    def _get_reply_log(self):
        """ 获取最新回复时间  """
        cur_time = int(time.time())

        query = public.S('auto_reply_logs', self.db_files['auto_reply'])

        data = query.order('last_time', 'DESC').find()

        if data:
            last_time = data['last_time']
        else:
            # public.print_log("数据库没数据 选一天前的")
            return cur_time-36400  # 数据库没数据 选一天前的

        # # 距离上次回复超过一小时  从一小时前开始查
        # timing = 60 * 60
        # if cur_time-last_time > timing:
        #     last_time = cur_time-timing
        # public.print_log(f"上次回复时间--{last_time}")
        return last_time

    # 获取最近收件信息 (时间范围内 成功收件 收件符合自动回复的邮箱)
    def _get_Receiving_information(self):
        """ 获取最新收件信息  """

        start_time = self._get_reply_log()
        # public.print_log(f'start_time  取开始 --{start_time}')
        end_time = int(time.time())
        # 获取
        query = public.S('receive_mails').alias('rm').prefix('')
        query.inner_join('senders s', 'rm.postfix_message_id=s.postfix_message_id')
        query.where('s.postfix_message_id is not null')


        if start_time > 0:
            query.where('rm.log_time > ?', start_time - 1)

        if end_time > 0:
            query.where('rm.log_time < ?', end_time + 1)
        query.where('rm.status  =?', 'sent')
        query.field('recipient,sender,rm.log_time')
        from power_mta.maillog_stat import query_maillog_with_time_section
        ret = query_maillog_with_time_section(query, start_time, end_time)
        if not ret:
            # public.print_log(f'自动回复    最近没有收件数据')
            return {}
        recipient_dict = {}

        # 遍历原始邮件日志数据并按收件人分组
        for log_entry in ret:
            recipient = log_entry["recipient"]

            # 如果收件人已经在字典中，添加新的日志条目
            if recipient in recipient_dict:
                recipient_dict[recipient].append(log_entry)
            else:
                # 如果收件人不在字典中，创建一个新的列表并添加第一个日志条目
                recipient_dict[recipient] = [log_entry]
        return recipient_dict

    # 查询是否满足发送间隔
    def _allow_to_send(self, recipient_list, interval, from_email):
        """查询满足收件间隔的邮件
            @recipient_list: 收件人列表（字典列表）
            @interval: 间隔时间
            @from_email: 发件人
            @return: list 可以发送的收件人列表
        """
        try:
            # 从字典列表中提取sender
            recipient_emails = [item['sender'] for item in recipient_list]
            
            # 查询数据库是否发送
            cur_time = int(time.time())
            times = cur_time - interval
            
            query = public.S('auto_reply_logs', self.db_files['auto_reply'])
            
            # 查询不满足时间的
            query.where('username', from_email)
            query.where_in('addressee', recipient_emails)  # 使用提取的邮箱列表
            query.where('last_time > ?', times)
            data = query.select()
            
            # 获取不符合条件的收件人列表
            un_recipient_emails = [i['addressee'] for i in data]
            
            # 过滤出符合条件的收件人
            allowed_emails = [email for email in recipient_emails if email not in un_recipient_emails]
            
            return allowed_emails
            
        except Exception as e:
            public.print_log(f"检查发送间隔失败: {str(e)}")
            public.print_log(public.get_error_info())
            return []

    # 记录回复日志
    def record_reply_log(self, to_email, from_email):
        """记录回复日志"""
        cur_time = int(time.time())
        
        insert = {}
        insert['username'] = from_email
        insert['addressee'] = to_email
        insert['last_time'] = cur_time

        query = public.S('auto_reply_logs', self.db_files['auto_reply'])

        if query.where('username', from_email).where('addressee', to_email).count():
            # 更新
            aa = query.where('username', from_email).where('addressee', to_email).update({"last_time":cur_time})
            # public.print_log(f'更新成功--{aa}')

        else:
            # 增加
            try:
                query = public.S('auto_reply_logs', self.db_files['auto_reply'])
                data = query.insert(insert, option='IGNORE')
            
            except:
                public.print_log(public.get_error_info())



    def extract_and_decode_subject(self, raw_string):
        """从原始字符串中提取并解码主题"""
        raw_string = raw_string.strip()

        if raw_string.startswith("hdr.subject:"):
            subject = raw_string[len("hdr.subject:"):].strip()
        else:
            subject = raw_string

        decoded_parts = decode_header(subject)
        decoded_str = ''
        for decoded_part, encoding in decoded_parts:
            if isinstance(decoded_part, bytes):
                if encoding:
                    decoded_str += decoded_part.decode(encoding)
                else:
                    decoded_str += decoded_part.decode('utf-8', 'ignore')
            else:
                decoded_str += decoded_part

        return decoded_str


    def get_original_subject(self, args):
        """通过系统命令获取邮件主题和时间
        @args.from_email: 收件邮箱
        @args.sender_email: 发件人
        @args.all: 是否获取全部主题
        @return: list/str 邮件主题列表或单个主题
        """
        try:
            from_email = args.from_email
            sender_email = args.sender_email
            all = args.all

            # 获取上次回复时间
            last_reply_time = 0
            with public.S('auto_reply_logs', self.db_files['auto_reply']) as obj:
                last_log = obj.where('username=? AND addressee=?', 
                    (from_email, sender_email)).order('last_time', 'desc').find()
                if last_log:
                    last_reply_time = last_log['last_time']
                        

            # 先获取所有邮件的UID
            cmd = f'doveadm search -u {from_email} mailbox inbox from "{sender_email}"'
            email_str = public.ExecShell(cmd)[0].replace("\n", " ")
            ids = [x.strip() for x in email_str.split() if x.isdigit()]
            
            if not ids:
                # public.print_log(f'自动回复 没有邮件 0')
                return []

            # 获取每封邮件的时间和主题
            emails = []
            for uid in ids:
                # 获取日期
                cmd_date = f'doveadm fetch -u {from_email} hdr.Date mailbox inbox uid {uid}'
                date_str = public.ExecShell(cmd_date)[0].strip()
                # public.print_log(f'自动回复 date_str--{date_str}')
                if date_str.startswith('hdr.date:'):
                    date_str = date_str[9:].strip()
                    email_time = int(time.mktime(email.utils.parsedate(date_str)))
                    # public.print_log(f'自动回复 email_time--{email_time}')
                    # 只处理未回复的邮件
                    if email_time > last_reply_time:

                        # 获取主题
                        cmd_subject = f'doveadm fetch -u {from_email} hdr.Subject mailbox inbox uid {uid}'
                        subject_str = public.ExecShell(cmd_subject)[0]
                        subject = self.extract_and_decode_subject(subject_str)
                        if subject:
                            emails.append((uid, email_time, subject))
            # public.print_log(f'自动回复 emails--{emails}')
            if not emails:
                # public.print_log(f'自动回复 没有邮件 1')
                return []

            # 按时间排序
            emails.sort(key=lambda x: x[1])

            if all:
                # 返回所有未回复邮件的主题
                return [email[2] for email in emails]
            else:
                # 只返回最新未回复邮件的主题
                return emails[-1][2]

        except Exception as e:
            public.print_log(f"Error occurred: {public.get_error_info()}")
            return []

    # 查询需要发件的邮箱 如果有收件就回复   无间隔就每封邮件都回复   有间隔,一小时内的邮件只回复最新的那一封
    def auto_reply_tasks(self):

        try:
            recipient_dict = self._get_Receiving_information()  # 最新收件
            if not recipient_dict:
                return
           

            auto_list = self._get_auto_reply_email()  # 生效的回复邮箱
           

            # 每个设置分开处理
            for i in auto_list:
                from_email = i['username']
                if from_email in recipient_dict.keys():
                    recipient_l = recipient_dict[from_email]  # 列表内是字典
                    if recipient_l:
                        # public.print_log(f'06')
                        interval = i['interval']
                        full_name = i['full_name']
                        content = public.readFile(i['content'])
                        subject = i['subject']  # 回复主题  需要再拼接上对方发送邮件的主题
                        # 获取所有发件人
                        senders = {email_info['sender'] for email_info in recipient_l}
                        for sender_email in senders:
                            args = public.dict_obj()
                            args.sender_email = sender_email
                            args.from_email = from_email
                            args.all = (interval == 0)  # 无间隔时获取所有邮件，有间隔只获取最新

                            subject_list = self.get_original_subject(args)
                            if isinstance(subject_list, list):  # 无间隔，返回列表
                                for original_subject in subject_list:
                                    new_subject = f"{subject} - Re: {original_subject}"
                                    is_success = self.send_auto_reply(sender_email, from_email, new_subject, content, full_name)
                                    # public.print_log(f'自动回复 无间隔 is_success--{is_success}')
                                    if is_success:
                                        self.record_reply_log(sender_email, from_email)
                            elif subject_list:  # 有间隔，返回单个主题
                                new_subject = f"{subject} - Re: {subject_list}"
                                is_success = self.send_auto_reply(sender_email, from_email, new_subject, content, full_name)
                                if is_success:
                                    self.record_reply_log(sender_email, from_email)

        except Exception as e:
            public.print_log(public.get_error_info())

        return


    def send_auto_reply(self,to_email, from_email, subject, html_content,full_name):
        import email
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        try:

            
            from_email = from_email.strip() if from_email else ''

            if not from_email or not to_email:
                return False

            msg = MIMEMultipart()
            sender = formataddr((full_name, from_email))
            msg['From'] = sender
            msg['To'] = from_email
            msg['Subject'] = subject
            msg.attach(MIMEText(html_content, 'html'))

            try:
                with smtplib.SMTP('localhost', 25) as server:
                    aa = server.sendmail(from_email, to_email, msg.as_string())
                    # public.print_log(f'aaa {aa}')
                    return True
            except Exception as e:
                public.print_log(public.get_error_info())
                return False
        except Exception as e:
            public.print_log(public.get_error_info())


    # 导出错误邮件日志
    def export_task_errlog_to_csv(self, args):
        task_id = args.get('task_id',0)
        if not task_id:
            return public.returnMsg(False, 'task_id is required')
        database_path = f'/www/vmail/bulk/task_{task_id}.db'
        if not os.path.exists(database_path):
            return public.returnMsg(False, 'database_path not exists')
        with public.S("task_count", database_path) as obj:
            ret = obj.where('status !=?', 'sent').select()
            # return ret
        
        import csv
        file_path = f'/tmp/a_task_{task_id}_errlog.csv'
        
        # 表头
        fieldnames = [
            'id',
            'created',
            'recipient',
            'queue_id',
            'message_id',
            'delay',
            'delays',
            'dsn',
            'relay',
            'domain',
            'status',
            'code',
            'err_info',
        ]
        
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
              
                writer.writeheader()

                for row in ret:
                    row_data = {}
                    for field in fieldnames:
                        if field == 'created':
                            # 转换时间戳为日期时间字符串
                            row_data[field] = datetime.fromtimestamp(row[field]).strftime('%Y-%m-%d %H:%M:%S')
                        else:
                           
                            row_data[field] = row.get(field, '')
                    
                    writer.writerow(row_data)
        
            # print(f"Data successfully written to {file_path}")
            return public.returnMsg(True, file_path)
        
        except Exception as e:
            print(f"Error writing CSV: {str(e)}")
            return public.returnMsg(False, f'Export failed: {str(e)}')


    def check_email_valid(self, args):
        """
        检查组内异常邮箱
        :param args: etype  类型
        :param args: oper   1 无操作   2 加入阻止列表  3 组内删除异常邮箱
        :return: str
        """
        
        SendMailBulk = bulk.SendMailBulk
        try:
            return SendMailBulk().check_email_valid(args)
        except Exception as ex:
            public.print_log(public.get_error_info())
            return {}
        
    # 获取手动扫描异常邮箱结果
    def get_check_email_result(self,args):
        path = f'/www/server/panel/plugin/mail_sys/data/check_email_valid1.json'
        data = public.readFile(path)
        if data:
            return json.loads(data)
        else:
            return {}

    # 开启域名ssl过期告警  字段改状态  调方法
    def open_domain_ssl_alarm(self, args):
        domain = args.get('domain', '')
        if not domain:
            return public.returnMsg(False, public.lang('Please specify the main domain'))
        try:
            open = int(args.get('open', 0))
            if open == 1:

                try:
                    # 判断任务
                    from ssl_domainModelV2.service import make_suer_alarm_task
                    res, msg = make_suer_alarm_task()
                    if not res:
                        return public.returnMsg(False, msg)
                except:
                    # 报错需更新面板
                    return public.returnMsg(False, public.lang('Available after updating the panel'))

                public.S("domain", self.db_files['postfixadmin']).where("domain=?", (domain,)).update(
                    {"ssl_alarm": 1})

            else:
                public.S("domain", self.db_files['postfixadmin']).where("domain=?", (domain,)).update({"ssl_alarm": 0})
        except:
            public.print_log(public.get_error_info())

        operation_str = 'Open' if open == 1 else 'Close'
        public.WriteLog('Mail Server', f'{operation_str} SSL alarms for domain names')
        return public.returnMsg(True, public.lang('The setup was successful'))

    def update_mailbox_quota_status(self, args):
        """
        更新邮箱配额状态
        :param username: 邮箱地址
        :param active: 1启用配额，0取消配额
        """
        username = args.get('username', '')
        active = int(args.get('quota_active/d', 0))

        if not username:
            return public.returnMsg(False, public.lang('Please specify the username'))


        try:
            # 1. 更新数据库状态
            with self.M('mailbox') as obj:
                obj.where('username=?', username).save('quota_active', (1 if active else 0,))

            # 2. 获取邮箱路径
            domain = username.split('@')[1]
            local_part = username.split('@')[0]
            maildir_path = os.path.join('/www/vmail', domain, local_part)
            maildirsize_path = os.path.join(maildir_path, 'maildirsize')

            if not active:  # 取消配额
                # 删除现有的maildirsize文件
                if os.path.exists(maildirsize_path):
                    os.remove(maildirsize_path)

                # 创建无限制的maildirsize文件
                with open(maildirsize_path, 'w') as f:
                    f.write("0S\n")  # 0表示无限制
                    f.write("0 0\n")  # 初始使用量计数
            else:  # 启用配额
                # 获取配额设置
                mailbox_info = obj.where('username=?', username).find()
                quota = mailbox_info.get('quota', 0)

                # 删除现有的maildirsize文件
                if os.path.exists(maildirsize_path):
                    os.remove(maildirsize_path)

                # 创建新的maildirsize文件
                with open(maildirsize_path, 'w') as f:
                    f.write(f"{quota}S\n")
                    f.write("0 0\n")

            # 设置正确的权限
            public.ExecShell(f"chown vmail:mail {maildirsize_path}")
            public.ExecShell(f"chmod 644 {maildirsize_path}")

            # 重新计算配额
            public.ExecShell(f'doveadm quota recalc -u {username}')

            status = "Enable" if args.active else "Disable"
            public.WriteLog('Mail Server', f'Quota limit for {status} mailbox [{username}]')

            return public.returnMsg(True, public.lang('The quota status is updated successfully'))

        except Exception as e:
            public.print_log(public.get_error_info())
            public.WriteLog('Mail Server', f'Failed to update mailbox [{username}] quota status: {str(e)}')
            return public.returnMsg(False, public.lang('Quota status update failed'))


    # 获取是否发邮件给用户的状态
    def get_quota_alert_status(self, args):
        '''
        获取是否发邮件给用户的状态
        '''
        conf_file = "/www/server/panel/plugin/mail_sys/data/quota_alert_conf.json"
        data = {"send_email_to_user": True}
        try:

            if os.path.exists(conf_file):
                conf_data = public.readFile(conf_file)
                if conf_data:
                    conf = json.loads(conf_data)
                    send_email_to_user = conf["send_email_to_user"] if "send_email_to_user" in conf else True
                    data["send_email_to_user"] = send_email_to_user

                    return public.returnMsg(True, data)
                return public.returnMsg(True, data)
            else:
                return public.returnMsg(True, data)
        except:
            return public.returnMsg(True, data)

    # 设置邮箱配额告警是否发邮件给用户
    def set_send_email_to_user(self, args):
        '''
        设置邮箱配额告警是否发邮件给用户
        args.status:0 关闭 1 开启
        '''
        conf_file = "/www/server/panel/plugin/mail_sys/data/quota_alert_conf.json"
        try:
            send_email_to_user = True
            if 'status' not in args:
                return public.returnMsg(False, public.lang('Missing status'))

            status = args.status
            if int(status) == 0:
                send_email_to_user = False

            conf = {"send_email_to_user": send_email_to_user}
            public.writeFile(conf_file, json.dumps(conf))

            return public.returnMsg(True, 'Setup successfully')
        except Exception as e:
            # return public.returnMsg(False, str(e))
            return public.returnMsg(False, 'Setup failed')


    # # 处理postfix参数   最大并发数
    # def check_param(self, args) -> bool:
    #     # param = args.get('param', '')
    #     param = 'default_destination_concurrency_limit'
    #     ddcl= self.check_postfix_param(param)
    #     # # 值不存在或值不为10  增加配置
    #     if not ddcl or ddcl != 20:
    #         exc = 'postconf -e "default_destination_concurrency_limit = 20"'
    #         aa = public.ExecShell(exc)
    #         public.print_log(f'aa--{aa}')
    #         # public.ExecShell('systemctl reload postfix')
    #
    #     # smtpd_client_message_rate_limit
    #     param = 'smtpd_client_message_rate_limit'
    #     ddcl= self.check_postfix_param(param)
    #     if not ddcl or ddcl != 500:
    #         exc = 'postconf -e "smtpd_client_message_rate_limit = 500"'
    #         aa = public.ExecShell(exc)
    #         public.print_log(f'bb--{aa}')
    #
    #     # anvil_rate_time_unit
    #     param = 'anvil_rate_time_unit'
    #     ddcl= self.check_postfix_param(param)
    #     if not ddcl or ddcl != '60s':
    #         exc = 'postconf -e "anvil_rate_time_unit = 60s"'
    #         aa = public.ExecShell(exc)
    #         public.print_log(f'cc--{aa}')
    #
    #    # smtpd_client_connection_rate_limit = 5
    #     param = 'smtpd_client_connection_rate_limit'
    #     ddcl= self.check_postfix_param(param)
    #     if not ddcl or ddcl != 1000:
    #         exc = 'postconf -e "smtpd_client_connection_rate_limit = 1000"'
    #         aa = public.ExecShell(exc)
    #         public.print_log(f'dd--{aa}')
    #
    #     public.ExecShell('systemctl reload postfix')
    #
    #     return
    #
    #
    # # 检查 Postfix 参数配置
    # def check_postfix_param(self, param: str) -> bool:
    #     """
    #     检查 Postfix 参数配置
    #     Args:
    #         param: str  要检查的 Postfix 参数名称
    #             例如：default_destination_concurrency_limit
    #     Returns:
    #         bool: True 表示参数存在且有值，False 表示参数不存在或无值
    #     """
    #     try:
    #         # 执行 postconf 命令查询指定参数
    #         result = public.ExecShell(f'postconf {param}')[0].strip()
    #
    #         # 检查是否有输出且包含等号
    #         if '=' not in result:
    #             return False
    #
    #         # 获取参数值
    #         param_value = result.split('=')[1].strip()
    #
    #         # 检查参数值是否存在
    #         public.print_log(f'param_value{param}--{param_value}')
    #         return bool(param_value)
    #
    #     except Exception as e:
    #         print(f"check Postfix param {param} error: {str(e)}")
    #         return False




    # # 设置全局每分钟发送频率限制 # todo xyz
    # def set_send_limit_minute(self, args):
    #     limit = args.get('limit', 150)
    #     public.writeFile(self.send_limit_path, str(limit))
    #     return public.returnMsg(True, public.lang('The setup was successful'))


    # def get_send_task_db_count(self, args):
    #     """
    #     查询专属数据库  收件总数据 收件失败数据;  收件人总数
    #
    #     :param task_id: 任务id
    #     :return: { total_sent , err_sent}   int
    #     """
    #
    #     database_path = f'/www/vmail/bulk/task_{args.task_id}.db'
    #     with public.S("task_count", database_path) as obj:
    #         total_sent = obj.count()
    #         error_count = obj.where('status !=?', 'sent').count()
    #         public.print_log(f"{args.task_id}total_sent 记录已发送数量--{total_sent}")
    #
    #
    #     total_recipient = 0
    #     try:
    #         with public.S("", database_path) as obj:
    #             tables = obj.query("SELECT name FROM sqlite_master WHERE type='table' AND name='recipient_info'")
    #             if tables and len(tables) > 0:
    #
    #                 with public.S("recipient_info", database_path) as robj:
    #                     total_recipient = robj.count()
    #                     public.print_log(f"{args.task_id}total_recipient 记录收件人数量--{total_recipient}")
    #     except Exception as e:
    #         # public.print_log(f"get_send_task_db_count: {str(e)}")
    #         pass
    #
    #     data = {"total_sent": total_sent, "error_count":error_count, "total_recipient":total_recipient}
    #     # public.cache_set(cache_key, data, 10)
    #     return data



    # 设置域名ip池发件ip
    def ddd_domain_ip(self, args):
        # domain = args.get('domain', '')
        # ip = args.get('ip', '')
        # if not domain or not ip:
        #     return public.returnMsg(False, public.lang('Please specify the domain and ip'))
    
        from multipleip import IPPool
        ip_pool = IPPool()


        # # 添加ip到池中
        result4 = ip_pool.add_ip('lootk.cn', '103.179.242.28')
        # result4 = ip_pool.add_ip('lotkfc.cn', '128.1.164.197')
        public.print_log(f"添加ip到池中结果: {result4}")
        # # 绑定发件ip
        result5 = ip_pool.bind_sending_ip('lootk.cn', '103.179.242.28')
        public.print_log(f"绑定IPv4结果: {result5}")

        # # 测试添加重复IP
        # result3 = ip_pool.add_ip('lotkfc.cn', '103.179.242.28')
        # public.print_log(f"添加重复IP结果: {result3}")

        # public.print_log("配置文件内容:")
        # with open('/etc/postfix/sender_maps/lotkfc.cn.map', 'r') as f:
        #     public.print_log(f.read())

        # 记录IP使用日志
        # ip_pool._log_ip_usage('lootk.cn', '103.179.242.28', True, '977935501@qq.com')

        # # 获取下一个可用IP
        # next_ip = ip_pool.get_next_ip('lotkfc.cn')
        # public.print_log(f"下一个可用IP: {next_ip}")

        # # 检查postfix配置
        result5 = ip_pool.check_postfix_config()
        public.print_log(f"Postfix配置检查结果: {result5}")

        # # 重新加载postfix配置 不用
        # result6 = ip_pool.reload_postfix()
        # public.print_log(f"Postfix重载结果: {result6}")

        # # 清除IP绑定(清楚配置文件 数据库不受影响)
        # ip_pool._clear_ip_binding('lotkfc.cn')

        # # 验证清理结果
        # binding_info = ip_pool.get_domain_binding('lotkfc.cn')
        # public.print_log(f"清理后的绑定信息: {binding_info}")


        return public.returnMsg(True, public.lang('The setup was successful'))
    


    def asd(self,args):
        """ 查看指定数据库 task_id   发件情况 """
        task_id = int(args.task_id)


        database_path = f'/www/vmail/bulk/task_{task_id}.db'
        with public.S("recipient_info", database_path) as obj:
            total = obj.count()
            total_r = obj.select()
            is_sent = obj.where('is_sent',1).count()
            is0_sent = obj.where('is_sent',0).count()

        with public.S("task_count", database_path) as obj:
            total_sent = obj.count()
            error_count = obj.where('status !=?', 'sent').count()
            send_r = obj.select()
        all = [i['recipient'] for i in send_r]

        # 任务发送状态
        task_info = self.M('email_task').where('type !=?', 1).where('id=?', task_id).find()
        public.print_log(f'fffff {task_info}')
        task_process= task_info['task_process']
        # message_ids = set()
        message_ids = []
        sent_recipient_path = '/www/server/panel/data/mail/in_bulk/recipient/sent_recipient'
        task_file_path = f"{sent_recipient_path}/msgid_{task_id}.log" # 读
        if os.path.exists(task_file_path):
            data = public.readFile(task_file_path)
            for line in data.splitlines():
                msgid = line.strip()
                msgid = msgid.strip('<>')
                # 去掉msgid两边的<> <173224082931.4191130.12787570563193919720@mail.aapanel.store>
                message_ids.append(msgid)
        # else:
        #     public.print_log("文件不存在{}  ".format(task_file_path))
        message_idss = len(message_ids)
        messs = len(set(message_ids))




        not_send = [i for i in total_r if i['recipient'] not in all]



        data = {
            'total':total,
            'is_sent':is_sent,
            'is0_sent':is0_sent,
            'total_sent1':total_sent,
            'error_count1':error_count,
            'msg_count':message_idss,
            'msg_count_only':messs,
            'task_process':task_process,

            'not_send':not_send,

        }
        return data
