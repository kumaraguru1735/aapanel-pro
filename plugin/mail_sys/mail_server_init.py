#!/usr/bin/python
#coding: utf-8
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
import sys,re,os,json
sys.path.append("class/")
import public
main_cf = "/etc/postfix/main.cf"
# download_url = public.get_url()
download_url = "https://raw.githubusercontent.com/kumaraguru1735/aapanel-pro/main/plugin/mail_sys/mail_conf"


def get_postconf():
    if os.path.exists("/usr/sbin/postconf"):
        return "/usr/sbin/postconf"
    elif os.path.exists("/sbin/postconf"):
        return "/sbin/postconf"
    else:
        return "postconf"

class change_to_rspamd:

    def change_dkim_server(self):
        # 更换dkim服务器，从opendkim切换到rspamd
        pass

    def change_postfix_conf(self):
        # postfix配置修改为支持rspamd
        shell = """
    {postconf} -e "myhostname = $(hostname)"
    {postconf} -e "smtpd_milters = inet:127.0.0.1:11332"
    {postconf} -e "non_smtpd_milters = inet:127.0.0.1:11332"
    {postconf} -e "milter_mail_macros = i {{mail_addr}} {{client_addr}} {{client_name}} {{auth_authen}}"
    {postconf} -e "milter_protocol = 6"
    {postconf} -e "milter_default_action = accept"
    """.format(postconf=get_postconf())
        public.ExecShell(shell)

    def comment_old_spam(self):
        conf = public.readFile(main_cf)
        if not conf:
            return
        rep = "##BT-ANTISPAM-BEGIN(.|\n)+##BT-ANTISPAM-END"
        conf = re.sub(rep, "", conf)
        public.writeFile(main_cf, conf)

    def change_dovecot_conf(self):
        # dovecot配置修改为支持rspamd
        shell = """
    wget "{download_conf_url}/mail_sys/dovecot/90-sieve_rspamd.conf" -O /etc/dovecot/conf.d/90-sieve.conf -T 30
    wget "{download_conf_url}/mail_sys/dovecot/20-lmtp.conf" -O /etc/dovecot/conf.d/20-lmtp.conf -T 30
    wget "{download_conf_url}/mail_sys/dovecot/20-imap.conf" -O /etc/dovecot/conf.d/20-imap.conf -T 30
    wget "{download_conf_url}/mail_sys/dovecot/15-mailboxes.conf" -O /etc/dovecot/conf.d/15-mailboxes.conf -T 30
    """.format(download_conf_url=download_url)
        public.ExecShell(shell)

    def main(self):
        self.comment_old_spam()
        self.change_postfix_conf()
        self.change_dovecot_conf()
        mail_server_init().setup_rspamd()

class mail_server_init:

    def __init__(self):
        self.sys_v = public.get_linux_distribution().lower()
        self.logfile = '/tmp/mail_init.log'
        self.db_files = {
            'postfixadmin': '/www/vmail/postfixadmin.db',
            'postfixmaillog': '/www/vmail/postfixmaillog.db',
            'mail_unsubscribe': '/www/vmail/mail_unsubscribe.db',
            'abnormal_recipient': '/www/vmail/abnormal_recipient.db',
            'auto_reply': '/www/vmail/auto_reply.db'
        }
    def write_logs(self,content,emtpy=None):
        if emtpy:
            public.writeFile(self.logfile, '')
        if '\n' not in content:
            content += '\n'
        public.writeFile(self.logfile,content,'a+')

    def check_env(self):
        data = {}
        data['HostName'] = self.check_hostname()
        data['Postfix-install'] = {"status":True,"msg":"Postfix has been installed"} if os.path.exists('/usr/sbin/postfix') else {"status":False,"msg":"Postfix not install,Please click the Fix button"}
        data['Dovecot-install'] = {"status":True,"msg":"Deovecot has been installed"} if os.path.exists('/usr/sbin/dovecot') else {"status":False,"msg":"Deovecot not install,Please click the Fix button"}
        data['Postfix-Version'] = self.check_postfix_ver()
        data['Redis-install'] = {"status":True,"msg":"Redis has been installed"} if os.path.exists('/www/server/redis/src/redis-server') else {"status":False,"msg":"Please install Redis in the APP Store"}
        data['Redis-Passwd'] = self.check_redis_passwd(data['Redis-install'])
        data['Rspamd-install'] = {"status":True,"msg":"Rspamd has been installed"} if os.path.exists('/usr/bin/rspamd') else {"status":False,"msg":"Rspamd not install,Please click the Fix button"}
        data['Sqlite-support'] = self.check_sqlite()
        data['SElinux'] ={"status":True,"msg":"SElinux is disabled"} if not 'enforcing' in public.ExecShell('getenforce')[0].lower() else {"status":False,"msg":"Please disable SElinux First!"}
        return data

    # 安装并配置postfix, dovecot
    def setup_mail_sys(self, args):
        '''
        安装邮局系统主函数
        :param args:
        :return:
        '''
        self.write_logs('|-Set up the postfix service to listen to all network cards...')
        public.ExecShell('{postconf} -e "inet_interfaces = all"'.format(postconf=get_postconf()))
        self.write_logs('|-Checking system key directory permissions...')
        if self._check_syssafe():
            self.write_logs('|-Check system key directory permissions: failed')
            return public.returnMsg(False, 'Please close the aapanel system reinforcement first')
        self.write_logs('|-Initializing...')
        if not self.prepare_work():
            return public.returnMsg(False, 'Preparation failed')
        if not self.conf_postfix()['status']:
            return public.returnMsg(False, 'Failed to configure postfix')
        if not self.conf_dovecot():
            return public.returnMsg(False, 'Failed to configure dovecot')
        if not self.setup_rspamd():
            return public.returnMsg(False, 'Failed to configure rspamd')
        # if not self.setup_opendkim():
        #     return public.returnMsg(False, 'Failed to configure opendkim 0')
        self.write_logs('|{}'.format("-"*60))
        self.write_logs('|-Initialized successfully!')
        return public.returnMsg(True, 'SUCCESS_INSTALL')

    # 检查系统加固是否开启
    def _check_syssafe(self, args=None):
        if not os.path.exists('/www/server/panel/plugin/syssafe/'):
            return False
        data = json.loads(public.readFile('/www/server/panel/plugin/syssafe/config.json'))
        return data['open']

    def check_hostname(self):
        import socket
        rep = '^(?!:\/\/)(?=.{1,255}$)((.{1,63}\.){1,127}(?![0-9]*$)[a-z0-9-]+\.?)$'
        hostname = socket.gethostname()
        if re.search(rep,hostname):
            return public.returnMsg(True,'success')
        return public.returnMsg(False, "Your hostname ({}) is invalid, and must be set to a fully qualified domain"
                                       " name before initialization mail server. You can update your hostname by "
                                       "running 'hostnamectl set-hostname --static mail.aapanel.com'".format(hostname))

    def M(self, table_name):
        import db
        sql = db.Sql()
        sql._Sql__DB_FILE = '/www/vmail/postfixadmin.db'
        return sql.table(table_name)
    def MD(self, table_name, db_key):
        if db_key not in self.db_files:
            raise ValueError(f"Unknown database key: {db_key}")
        import db
        sql = db.Sql()
        sql._Sql__DB_FILE = self.db_files[db_key]
        sql._Sql__encrypt_keys = []
        return sql.table(table_name)

    # 放行端口
    def _release_port(self, port):
        from collections import namedtuple
        try:
            import firewalls
            get = namedtuple("get", ["port", "ps", "type"])
            get.port = port
            get.ps = 'Mail-Server'
            get.type = "port"
            firewalls.firewalls().AddAcceptPort(get)
            # return get.port
            return port
        except Exception as e:
            return "Release failed {}".format(e)

    def prepare_work(self):
        '''
        安装前的准备工作
        :return:
        '''
        shell_str = '''
useradd -r -u 150 -g mail -d /www/vmail -s /sbin/nologin -c "Virtual Mail User" vmail
mkdir -p /www/vmail
chmod -R 770 /www/vmail
chown -R vmail:mail /www/vmail

if [ ! -f "/www/vmail/postfixadmin.db" ]; then
    touch /www/vmail/postfixadmin.db
    chown vmail:mail /www/vmail/postfixadmin.db
    chmod 660 /www/vmail/postfixadmin.db
fi'''
        self.write_logs('',emtpy=True)
        self.write_logs('|-Adding user: vmail')
        self.write_logs('|-Create mail storage directory: /www/vmail')
        self.write_logs('|-Set directory permissions: 770')
        self.write_logs('|-Set directory owner: vmail:mail')
        if "centos" in self.sys_v:
            public.ExecShell(shell_str)
        elif "ubuntu" in self.sys_v:
            public.ExecShell(shell_str)
            # copy证书
            if not os.path.exists("/etc/pki/dovecot/certs/dovecot.pem"):
                self.write_logs('|-Generate dovecot certificate: /etc/pki/dovecot/certs/dovecot.pem')
                shell_str = """
                sudo mkdir -p /etc/pki/dovecot/certs/
                sudo mkdir -p /etc/pki/dovecot/private/
                sudo cp /etc/ssl/certs/ssl-cert-snakeoil.pem /etc/pki/dovecot/certs/dovecot.pem
                sudo mv /etc/ssl/private/ssl-cert-snakeoil.key /etc/pki/dovecot/private/dovecot.pem
                """
                public.ExecShell(shell_str)
        else:
            return public.returnMsg(False, "Only supports Centos and Ubuntu systems at the moment")
        # 配置防火墙
        for i in ["25", "110", "143", "465", "995", "993", "587"]:
            self.write_logs('|-Releasing port: {}'.format(i))
            self._release_port(i)
            # 调用防火墙开放端口
            from safeModel.firewallModel import main as firewall
            firewall_obj = firewall()
            # protocol port type address brief
            new_get = public.dict_obj()
            new_get.protocol = "tcp"
            new_get.ports = str(i)
            new_get.choose = "all"
            new_get.address = ""
            new_get.domain = ""
            new_get.types = "accept"
            new_get.brief = "Mail-Server"
            new_get.source = ""
            firewall_obj.create_rules(new_get)
        # 创建数据表
        # 域名表  moyumao.top 目录: /www/vmail/moyumao.top
        self.write_logs('|-Initializing database...')
        sql = '''CREATE TABLE IF NOT EXISTS `domain` (
          `domain` varchar(255) NOT NULL,                   -- 域名
          `a_record` TEXT DEFAULT "",
          `mailboxes` int DEFAULT 50,                       -- 创建邮箱数量
          `mailbox_quota` bigint(20) NOT NULL DEFAULT 5368709120,    -- 邮箱默认空间大小
          `quota` bigint(20) NOT NULL DEFAULT 10737418240,            -- 域名配额
          `current_usage ` bigint(20) NOT NULL DEFAULT 0,    -- 域名当前使用量
          `rate_limit` int DEFAULT 12,                       -- 每秒几个邮件
          `created` datetime NOT NULL,
          `active` tinyint(1) NOT NULL DEFAULT 1,
          PRIMARY KEY (`domain`));'''

        with self.M("") as obj:
            obj.execute(sql, ())

        # self.M('').execute(sql, ())


        # 邮箱账号  awe_0_ivt@moyumao.top 目录:  /www/vmail/moyumao.top/awe_0_ivt
        sql = '''CREATE TABLE IF NOT EXISTS `mailbox` (
          `username` varchar(255) NOT NULL,             -- 邮箱
          `password` varchar(255) NOT NULL,
          `password_encode` varchar(255) NOT NULL,
          `full_name` varchar(255) NOT NULL,
          `is_admin` tinyint(1) NOT NULL DEFAULT 0,
          `maildir` varchar(255) NOT NULL,
          `quota` bigint(20) NOT NULL DEFAULT 0,             -- 邮箱配额
          `current_usage ` bigint(20) NOT NULL DEFAULT 0,    -- 邮箱当前使用量
          `quota_active` tinyint(1) NOT NULL DEFAULT 1,     -- 是否使用配额
          `local_part` varchar(255) NOT NULL,
          `domain` varchar(255) NOT NULL,               -- 域名
          `created` datetime NOT NULL,
          `modified` datetime NOT NULL,
          `active` tinyint(1) NOT NULL DEFAULT 1,
          PRIMARY KEY (`username`));'''
        with self.M("") as obj:
            obj.execute(sql, ())
        # self.M('').execute(sql, ())

        # 邮件转发
        sql = '''CREATE TABLE IF NOT EXISTS `alias` (
          `address` varchar(255) NOT NULL,
          `goto` text NOT NULL,
          `domain` varchar(255) NOT NULL,
          `created` datetime NOT NULL,
          `modified` datetime NOT NULL,
          `active` tinyint(1) NOT NULL DEFAULT 1,
          PRIMARY KEY (`address`));'''
        with self.M("") as obj:
            obj.execute(sql, ())
        # self.M('').execute(sql, ())
        # 系统内用表 没看到使用
        sql = '''CREATE TABLE IF NOT EXISTS `alias_domain` (
          `alias_domain` varchar(255) NOT NULL, 
          `target_domain` varchar(255) NOT NULL,
          `created` datetime NOT NULL,
          `modified` datetime NOT NULL,
          `active` tinyint(1) NOT NULL DEFAULT 1,
          PRIMARY KEY (`alias_domain`));'''
        with self.M("") as obj:
            obj.execute(sql, ())
        # self.M('').execute(sql, ())
        # 新增3个表  批量发件用
        # 邮件模版表
        sql = '''CREATE TABLE IF NOT EXISTS `temp_email` (
          `id` INTEGER  PRIMARY KEY AUTOINCREMENT,        
          `name` varchar(255) NULL,         -- 邮件名 有模版时为模版名
          `type` tinyint(1) NOT NULL DEFAULT 0,  --上传html 0   拖拽html 1
          `content` text NOT NULL,          -- 邮件正文 路径
          `render` text NOT NULL,   -- html渲染数据
          `created` INTEGER NOT NULL,  
          `modified` INTEGER NOT NULL,
          `is_temp` tinyint(1) NOT NULL DEFAULT 0  -- 是否是模版
          );'''
        with self.M("") as obj:
            obj.execute(sql, ())
        # self.M('').execute(sql, ())

        # 任务表
        sql = '''CREATE TABLE IF NOT EXISTS `email_task` (
          `id` INTEGER  PRIMARY KEY AUTOINCREMENT,    
          `task_name` varchar(255) NOT NULL,        -- 任务名
          `addresser` varchar(320) NOT NULL,        -- 发件人
          `recipient_count` int NOT NULL,           -- 收件人数量
          `task_process` tinyint NOT NULL,     -- 任务进程  0待执行   1执行中  2 已完成
          `pause` tinyint NOT NULL,      -- 暂停状态  1 暂停中     0 未暂停     执行中的任务才能暂停
          `temp_id` INTEGER NOT NULL,          -- 邮件对应id
          `is_record` INTEGER NOT NULL DEFAULT 0,          -- 是否记录到发件箱
          `unsubscribe` INTEGER NOT NULL DEFAULT 0,      -- 是否增加退订按钮   0 没有   1 增加退订按钮
          `threads` INTEGER NOT NULL DEFAULT 0,          -- 线程数量 控制发送线程数 0时自动控制线程   0~10
          `created` INTEGER NOT NULL,
          `modified` INTEGER NOT NULL,
          `remark` text,           -- 备注
          `etypes` varchar(320) NOT NULL DEFAULT '1',         -- 邮件类型id 默认为1  多类型 1,2,3
          `start_time` INTEGER NOT NULL DEFAULT 0,            -- 任务开始时间
          `subject` text NULL,          -- 邮件主题   改task存  可空
          `full_name` varchar(255),  -- 新发件人名    改task存  可空
          `recipient` text NOT NULL,        -- 收件人路径 改task存
          `track_open` INTEGER NOT NULL DEFAULT 0,    --  追踪邮件打开
          `track_click` INTEGER NOT NULL DEFAULT 0,    --  链接点击
          `active` tinyint(1) NOT NULL DEFAULT 0    --  预留字段
          );'''
        with self.M("") as obj:
            obj.execute(sql, ())
        # self.M('').execute(sql, ())

        # 发送统计表 改 错误详情表  task_id与recipient 联合唯一  避免重试邮件重复记录

        sql = '''CREATE TABLE IF NOT EXISTS `task_count` (
          `id` INTEGER  PRIMARY KEY AUTOINCREMENT,    
          `task_id` INTEGER NOT NULL,                   -- 所属任务编号
          `recipient` varchar(320) NOT NULL,            -- 收件人
          `delay` varchar(320) NOT NULL,            -- 延时
          `delays` varchar(320) NOT NULL,            -- 各阶段延时
          `dsn` varchar(320) NOT NULL,            -- dsn
          `relay` text NOT NULL,            -- 中继服务器
          `domain` varchar(320) NOT NULL,               -- 域名
          `status` varchar(255) NOT NULL,               -- 错误状态
          `err_info` text NOT NULL,                      -- 错误详情
          `created` INTEGER NOT NULL DEFAULT 0,
           UNIQUE (`task_id`, `recipient`)  -- 联合唯一约束
          );'''
        with self.M("") as obj:
            obj.execute(sql, ())

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

        with self.MD("", "mail_unsubscribe") as obj3:
            aa = obj3.execute(sql, ())
            # public.print_log("更新退订表 mail_unsubscribe --{}".format(aa))


        # 统计日志 收件人和日志时间联合唯一
        sql = '''CREATE TABLE IF NOT EXISTS `mail_errlog` (
          `id` INTEGER  PRIMARY KEY AUTOINCREMENT,
          `created` INTEGER NOT NULL,
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
        # self.M2('').execute(sql, ())



        # 邮件日志分析统计表  接收 received, 发送 delivered, 转发 forwarded, 延迟 deferred, 退回 bounced, 拒绝 rejected
        sql = '''CREATE TABLE IF NOT EXISTS `log_analysis` (
          `id` INTEGER  PRIMARY KEY AUTOINCREMENT,
          `received` INTEGER NOT NULL DEFAULT 0,        -- 接收
          `delivered` INTEGER NOT NULL DEFAULT 0,       -- 发送
          `forwarded` INTEGER NOT NULL DEFAULT 0,       -- 转发
          `deferred` INTEGER NOT NULL DEFAULT 0,        -- 延迟
          `bounced` INTEGER NOT NULL DEFAULT 0,         -- 退回
          `rejected` INTEGER NOT NULL DEFAULT 0,        -- 拒绝
          `time` INTEGER NOT NULL,                    -- 时间  每小时时间戳
           UNIQUE(`created`)    
          );'''
        with self.M("") as obj:
            obj.execute(sql, ())

        # 异常用户表
        sql = '''CREATE TABLE IF NOT EXISTS `abnormal_recipient` (
        `id` INTEGER  PRIMARY KEY AUTOINCREMENT,
        `created` INTEGER NOT NULL,               -- 邮件时间 时间戳
        `recipient` varchar(320) NOT NULL,        -- 收件人
        `count` INTEGER NOT NULL,                 -- 次数
        `status` varchar(255) NOT NULL,           -- 状态
        `task_name` varchar(255) NOT NULL,      -- 任务名
        UNIQUE(recipient)
        );'''

        with self.MD("", "abnormal_recipient") as obj4:
            obj4.execute(sql, ())

        # 邮件自动回复
        sql = """CREATE TABLE IF NOT EXISTS `auto_reply` (
            `id` INTEGER  PRIMARY KEY AUTOINCREMENT,
            `username` varchar(255)  NOT NULL,    -- 邮箱
            `domain` varchar(255) NOT NULL, -- 域名
            `active` tinyint(1) NOT NULL DEFAULT 1, --启用   
            `maildir` varchar(255) NOT NULL, -- 用户目录
            `subject` TEXT,  --主题
            `content` TEXT,  --正文
            `full_name` varchar(255) NOT NULL,  --发件人名称
            `interval` INTEGER,  --间隔时间
            `start_time` DATETIME,  --生效开始时间
            `end_time` DATETIME , --结束时间
            UNIQUE(username)
        );"""

        with self.M("") as obj:
            obj.execute(sql, ())

        # 自动回复记录
        sql = '''CREATE TABLE IF NOT EXISTS `auto_reply_logs` (
            `id` INTEGER  PRIMARY KEY AUTOINCREMENT,
            `username` varchar(255)  NOT NULL,      -- 发件人
            `addressee` varchar(255)  NOT NULL,      -- 收件人
            `last_time` DATETIME ,                   --上次回复时间
            UNIQUE (`addressee`, `username`)  -- 联合唯一约束
        );'''

        with self.MD("", "auto_reply") as obj4:
            obj4.execute(sql, ())
        # # 邮件日志分析统计表
        # sql = '''CREATE TABLE IF NOT EXISTS `email_log` (
        #   --`id` INTEGER  PRIMARY KEY AUTOINCREMENT,
        #   `hostname` varchar(320) NOT NULL,            -- 主机名 hello-mail
        #   `process` varchar(320) NOT NULL,            -- 进程 postfix/smtp[3033510]
        #   `email_id` varchar(320) NOT NULL,            -- 邮件id  17C2A38062F
        #   `recipient` varchar(320) NOT NULL,            -- 收件人
        #   `relay` text NOT NULL,            -- 中继服务器
        #   `delay` varchar(320) NOT NULL,            -- 延时
        #   `delays` varchar(320) NOT NULL,            -- 各阶段延时  连接建立，发送数据，等待响应，传输完成
        #   `dsn` varchar(320) NOT NULL,            -- dsn
        #   `status` varchar(255) NOT NULL,               -- 错误状态
        #   `domain` varchar(320) NOT NULL,               -- 域名
        #   `err_info` text NOT NULL,                      -- 错误详情
        #   `created` INTEGER NOT NULL,                   -- 时间戳
        #    PRIMARY KEY (`email_id`));
        #   '''
        # self.M('').execute(sql, ())

        # 判断/www/vmail/postfixadmin.db文件是否存在
        if os.path.exists('/www/vmail/postfixadmin.db'):
            self.write_logs('|-The database is initialized successfully...')
            return True
        else:
            self.write_logs('|-Database initialization failed...')
            return False

    def _check_sendmail(self):
        pid = '/run/sendmail/mta/sendmail.pid'
        if os.path.exists(pid):
            self.write_logs('|-Check that there is an additional mail service aaa, which is stopping')
            public.ExecShell('systemctl stop sendmail && systemctl disable sendmail')

    def conf_postfix(self):
        '''
        安装，配置postfix服务, postfix提供发信功能
        :return:
        '''
        # 检查sendmail服务，如果有则停止
        self._check_sendmail()
        # 修改postfix配置
        self.write_logs('|-Initializing postfix...')
        edit_postfix_conf_shell = '''
{postconf} -e "myhostname = $(hostname)"
{postconf} -e "inet_interfaces = all"
{postconf} -e "mydestination ="

{postconf} -e "virtual_mailbox_domains = sqlite:/etc/postfix/sqlite_virtual_domains_maps.cf"
{postconf} -e "virtual_alias_maps =  sqlite:/etc/postfix/sqlite_virtual_alias_maps.cf, sqlite:/etc/postfix/sqlite_virtual_alias_domain_maps.cf, sqlite:/etc/postfix/sqlite_virtual_alias_domain_catchall_maps.cf"
{postconf} -e "virtual_mailbox_maps = sqlite:/etc/postfix/sqlite_virtual_mailbox_maps.cf, sqlite:/etc/postfix/sqlite_virtual_alias_domain_mailbox_maps.cf"

{postconf} -e "smtpd_sasl_type = dovecot"
{postconf} -e "smtpd_sasl_path = private/auth"
{postconf} -e "smtpd_sasl_auth_enable = yes"
{postconf} -e "smtpd_recipient_restrictions = permit_sasl_authenticated, permit_mynetworks, reject_unauth_destination"

{postconf} -e "smtpd_use_tls = yes"
{postconf} -e "smtp_tls_security_level = may"
{postconf} -e "smtpd_tls_security_level = may"
{postconf} -e "smtpd_tls_cert_file = /etc/pki/dovecot/certs/dovecot.pem"
{postconf} -e "smtpd_tls_key_file = /etc/pki/dovecot/private/dovecot.pem"
{postconf} -e "virtual_transport = lmtp:unix:private/dovecot-lmtp"
{postconf} -e "smtpd_milters = inet:127.0.0.1:11332"
{postconf} -e "non_smtpd_milters = inet:127.0.0.1:11332"
{postconf} -e "milter_mail_macros = i {{mail_addr}} {{client_addr}} {{client_name}} {{auth_authen}}"
{postconf} -e "milter_protocol = 6"
{postconf} -e "milter_default_action = accept"
{postconf} -e "message_size_limit = 102400000"
'''.format(postconf=get_postconf())
        public.ExecShell(edit_postfix_conf_shell)
        self.write_logs('|-Downloading additional configuration files...')
        download_sql_conf_shell = '''
wget "{download_conf_url}/mail_sys/postfix/master.cf" -O /etc/postfix/master.cf -T 30 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/postfix/sqlite_virtual_alias_domain_catchall_maps.cf" -O /etc/postfix/sqlite_virtual_alias_domain_catchall_maps.cf -T 30 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/postfix/sqlite_virtual_alias_domain_mailbox_maps.cf" -O /etc/postfix/sqlite_virtual_alias_domain_mailbox_maps.cf -T 30 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/postfix/sqlite_virtual_alias_domain_maps.cf" -O /etc/postfix/sqlite_virtual_alias_domain_maps.cf -T 30 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/postfix/sqlite_virtual_alias_maps.cf" -O /etc/postfix/sqlite_virtual_alias_maps.cf -T 30 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/postfix/sqlite_virtual_domains_maps.cf" -O /etc/postfix/sqlite_virtual_domains_maps.cf -T 30 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/postfix/sqlite_virtual_mailbox_maps.cf" -O /etc/postfix/sqlite_virtual_mailbox_maps.cf -T 30 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/postfix/btrule.cf" -O /etc/postfix/btrule.cf -T 30 >> {logfile} 2>&1
'''.format(download_conf_url=download_url,logfile=self.logfile)
        aaa = public.ExecShell(download_sql_conf_shell)
        # public.print_log("执行命令后返回 --{}".format(aaa))

        result = public.readFile("/etc/postfix/sqlite_virtual_mailbox_maps.cf")
        if not result or not re.search(r"\n*query\s*=\s*", result):
            self.write_logs('|- Read file content {}: Failed'.format("/etc/postfix/sqlite_virtual_mailbox_maps.cf"))
            return public.returnMsg(False,"Get the mail server conf error!")

        restart_service_shell = 'systemctl enable postfix && systemctl restart postfix'
        self.write_logs('|-Restarting postfix service...')
        public.ExecShell(restart_service_shell)
        return public.returnMsg(True,"Setup successfully!")

    def conf_dovecot(self):
        '''
        安装，配置dovecot服务, dovecot提供收信功能
        :return:
        '''
        self.write_logs('|-Initializing dovecot...')
        self.write_logs('|-Downloading additional configuration files...')
        download_conf_shell = '''
wget "{download_conf_url}/mail_sys/dovecot/dovecot-sql.conf.ext" -O /etc/dovecot/dovecot-sql.conf.ext -T 30 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/dovecot/dovecot.conf" -O /etc/dovecot/dovecot.conf -T 30 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/dovecot/90-quota.conf" -O /etc/dovecot/90-quota.conf -T 30 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/dovecot/10-mail.conf" -O /etc/dovecot/conf.d/10-mail.conf -T 30 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/dovecot/10-ssl.conf" -O /etc/dovecot/conf.d/10-ssl.conf -T 30 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/dovecot/10-master.conf" -O /etc/dovecot/conf.d/10-master.conf -T 30 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/dovecot/10-auth.conf" -O /etc/dovecot/conf.d/10-auth.conf -T 30 >> {logfile} 2>&1

wget "{download_conf_url}/mail_sys/dovecot/90-sieve_rspamd.conf" -O /etc/dovecot/conf.d/90-sieve.conf -T 30 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/dovecot/20-lmtp.conf" -O /etc/dovecot/conf.d/20-lmtp.conf -T 30 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/dovecot/20-imap.conf" -O /etc/dovecot/conf.d/20-imap.conf -T 30 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/dovecot/20-pop3.conf" -O /etc/dovecot/conf.d/20-pop3.conf -T 30 >> {logfile} 2>&1
wget "{download_conf_url}/mail_sys/dovecot/15-mailboxes.conf" -O /etc/dovecot/conf.d/15-mailboxes.conf -T 30 >> {logfile} 2>&1
'''.format(download_conf_url=download_url,logfile=self.logfile)
        public.ExecShell(download_conf_shell)
        result = public.readFile("/etc/dovecot/dovecot.conf")
        if not result or not re.search(r"\n*protocol\s+imap", result):
            self.write_logs('|-Read file content {}: Failed'.format("/etc/dovecot/dovecot.conf"))
            return False

        # 关闭protocols注释
        dovecot_conf = public.readFile("/etc/dovecot/dovecot.conf")
        dovecot_conf = re.sub(r"#protocols\s*=\s*imap\s*pop3\s*lmtp", "protocols = imap pop3 lmtp", dovecot_conf)
        public.writeFile("/etc/dovecot/dovecot.conf", dovecot_conf)

        if 'centos8' in self.sys_v:
            if not self.create_ssl():
                self.write_logs('|-Generate self-signed certificate: Failed')
                return False
        if not os.path.exists('/etc/pki/dovecot/private/dovecot.pem') or not os.path.exists(
                '/etc/pki/dovecot/certs/dovecot.pem'):
            self.create_ssl()
        restart_service_shell = '''
chown -R vmail:dovecot /etc/dovecot
chmod -R o-rwx /etc/dovecot

systemctl enable dovecot
systemctl restart  dovecot
'''
        self.write_logs('|-Restarting dovecot...')
        public.ExecShell(restart_service_shell)
        return True

    # 自签证书
    def create_ssl(self, get=None):
        import OpenSSL
        self.write_logs('|-Generating self-signed certificate...')
        public.back_file('/etc/pki/dovecot/certs/dovecot.pem')
        public.back_file('/etc/pki/dovecot/private/dovecot.pem')
        key = OpenSSL.crypto.PKey()
        key.generate_key(OpenSSL.crypto.TYPE_RSA, 2048)
        cert = OpenSSL.crypto.X509()
        cert.set_serial_number(0)
        cert.get_subject().CN = public.GetLocalIp()
        cert.set_issuer(cert.get_subject())
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)
        cert.set_pubkey(key)
        cert.sign(key, 'md5')
        cert_ca = OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)
        private_key = OpenSSL.crypto.dump_privatekey(OpenSSL.crypto.FILETYPE_PEM, key)
        if not isinstance(cert_ca, str):
            cert_ca = cert_ca.decode()
        if not isinstance(private_key, str):
            private_key = private_key.decode()
        if len(cert_ca) > 100 and len(private_key) > 100:
            public.writeFile('/etc/pki/dovecot/certs/dovecot.pem', cert_ca)
            public.writeFile('/etc/pki/dovecot/private/dovecot.pem', private_key)
            return True
        else:
            public.restore_file('/etc/pki/dovecot/certs/dovecot.pem')
            public.restore_file('/etc/pki/dovecot/private/dovecot.pem')
            return False

    def check_postfix_ver(self):
        postfix_version = public.ExecShell(r"{postconf} mail_version|sed -r 's/.* ([0-9\.]+)$/\1/'".format(
            postconf=get_postconf()))[0].strip()
        if postfix_version.startswith('3'):
            return public.returnMsg(True,postfix_version)
        else:
            return public.returnMsg(False,"The current version is not supported or Postfix is not installed successfully：{}".format(postfix_version))

    def check_redis_passwd(self,redis_install):
        redis_conf = public.readFile('/www/server/redis/redis.conf')
        if redis_install['status']:
            if re.search('\n\s*requirepass',redis_conf):
                return public.returnMsg(True,"Redis has been set password")
        return public.returnMsg(False,"Please go to the Redis manager --> Performance tuning to setup password")

    def check_sqlite(self):
        if not public.ExecShell('{postconf} -m | grep sqlite'.format(postconf=get_postconf()))[0].strip():
            return public.returnMsg(False,"Postfix has been support sqlite")
        return public.returnMsg(True,"Postfix not support sqlite")

    def setup_rspamd(self):
        # public.print_log("进入修复文件1")
        # 修改postfix配置
        self.write_logs('|-Initializing rspamd...')
        edit_postfix_conf_shell = '''
{postconf} -e "smtpd_milters = inet:127.0.0.1:11332"
{postconf} -e "non_smtpd_milters = inet:127.0.0.1:11332"
{postconf} -e "milter_mail_macros = i {{mail_addr}} {{client_addr}} {{client_name}} {{auth_authen}}"
{postconf} -e "milter_protocol = 6"
{postconf} -e "milter_default_action = accept"
'''.format(postconf=get_postconf())
        public.ExecShell(edit_postfix_conf_shell)
        self.write_logs('|-Downloading additional configuration files...')
        get_rspamd_conf_shell = """
mkdir -p /usr/lib/dovecot/sieve
wget -O /etc/rspamd/worker-normal.inc {download_conf_url}/mail_sys/rspamd/worker-normal.inc -T 30 --no-check-certificate >> {logfile} 2>&1
wget -O /etc/rspamd/worker-fuzzy.inc {download_conf_url}/mail_sys/rspamd/worker-fuzzy.inc -T 30 --no-check-certificate >> {logfile} 2>&1
wget -O /etc/rspamd/statistic.conf {download_conf_url}/mail_sys/rspamd/statistic.conf -T 30 --no-check-certificate >> {logfile} 2>&1
wget -O /etc/rspamd/local.d/worker-controller.inc {download_conf_url}/mail_sys/rspamd/worker-controller.inc -T 30 --no-check-certificate >> {logfile} 2>&1
wget -O /etc/rspamd/worker-proxy.inc {download_conf_url}/mail_sys/rspamd/worker-proxy.inc -T 30 --no-check-certificate >> {logfile} 2>&1
wget -O /etc/rspamd/local.d/dkim_signing.conf {download_conf_url}/mail_sys/rspamd/modules.d/dkim_signing_bt.conf -T 30 --no-check-certificate >> {logfile} 2>&1
wget -O /etc/rspamd/local.d/milter_headers.conf {download_conf_url}/mail_sys/rspamd/modules.d/milter_headers_bt.conf -T 30 --no-check-certificate >> {logfile} 2>&1
wget -O /etc/rspamd/local.d/redis.conf {download_conf_url}/mail_sys/rspamd/modules.d/redis_bt.conf -T 30 --no-check-certificate >> {logfile} 2>&1

wget -O /usr/lib/dovecot/sieve/report-ham.sieve {download_conf_url}/mail_sys/dovecot/lib/report-ham.sieve -T 30 --no-check-certificate >> {logfile} 2>&1
wget -O /usr/lib/dovecot/sieve/report-spam.sieve {download_conf_url}/mail_sys/dovecot/lib/report-spam.sieve -T 30 --no-check-certificate >> {logfile} 2>&1
wget -O /usr/lib/dovecot/sieve/spam-to-folder.sieve {download_conf_url}/mail_sys/dovecot/lib/spam-to-folder.sieve -T 30 --no-check-certificate >> {logfile} 2>&1
wget -O /usr/lib/dovecot/sieve/sa-learn-spam.sh {download_conf_url}/mail_sys/dovecot/lib/sa-learn-spam.sh -T 30 --no-check-certificate >> {logfile} 2>&1
wget -O /usr/lib/dovecot/sieve/sa-learn-ham.sh {download_conf_url}/mail_sys/dovecot/lib/sa-learn-ham.sh -T 30 --no-check-certificate >> {logfile} 2>&1
sievec /usr/lib/dovecot/sieve/spam-to-folder.sieve
sievec /usr/lib/dovecot/sieve/report-spam.sieve
sievec /usr/lib/dovecot/sieve/report-ham.sieve
chmod +x /usr/lib/dovecot/sieve/sa-learn-spam.sh
chmod +x /usr/lib/dovecot/sieve/sa-learn-ham.sh
""".format(download_conf_url=download_url,logfile=self.logfile)
        public.ExecShell(get_rspamd_conf_shell)
        # 生成web端管理密码
        self.write_logs('|-Generating rspamd management password...')
        passwd = public.GetRandomString(8)
        passwd_en = public.ExecShell('rspamadm pw -p "{}"'.format(passwd))[0].strip('\n')
        public.writeFile('/etc/rspamd/passwd', passwd)
        worker_controller_path = '/etc/rspamd/local.d/worker-controller.inc'
        worker_controller = public.readFile(worker_controller_path)
        if worker_controller:
            if 'BT_PASSWORD' in worker_controller:
                worker_controller = worker_controller.replace('password = "BT_PASSWORD";',
                                                              'password = "{}";'.format(passwd_en))
                public.writeFile(worker_controller_path, worker_controller)
        # 设置rspamd redis密码
        rspamd_redis_path = '/etc/rspamd/local.d/redis.conf'
        rspamd_redis = public.readFile(rspamd_redis_path)
        if rspamd_redis:
            if 'BT_REDIS_PASSWD' in rspamd_redis:
                rspamd_redis = rspamd_redis.replace('password = "BT_REDIS_PASSWD";',
                                                    'password = "{}";'.format(self.get_redis_passwd()))
                public.writeFile(rspamd_redis_path, rspamd_redis)
        self.write_logs('|-Restarting rspamd...')
        public.ExecShell('systemctl restart rspamd postfix dovecot')
        return True

    def get_redis_passwd(self):
        redis_path = '/www/server/redis/redis.conf'
        redis_conf = public.readFile(redis_path)
        passwd = re.search('\n\s*requirepass\s+(.*)',redis_conf)
        if passwd:
            return passwd.groups(0)[0]
        return False

    def install_dovecot_on_ubuntu(self):
        install_shell = """
sudo apt remove dovecot-core dovecot-imapd dovecot-lmtpd dovecot-pop3d dovecot-sqlite dovecot-sieve -y
dpkg -P dovecot-core dovecot-imapd dovecot-lmtpd dovecot-pop3d dovecot-sqlite dovecot-sieve
sudo apt install dovecot-core dovecot-pop3d dovecot-imapd dovecot-lmtpd dovecot-sqlite dovecot-sieve -y
"""
        public.ExecShell(install_shell)
        shell_str = """
sudo rm -f /etc/pki/dovecot/certs/dovecot.pem
sudo rm -f /etc/pki/dovecot/private/dovecot.pem
sudo mkdir -p /etc/pki/dovecot/certs/
sudo mkdir -p /etc/pki/dovecot/private/
sudo cp /etc/ssl/certs/ssl-cert-snakeoil.pem /etc/pki/dovecot/certs/dovecot.pem
sudo mv /etc/ssl/private/ssl-cert-snakeoil.key /etc/pki/dovecot/private/dovecot.pem
"""
        public.ExecShell(shell_str)
        return self.conf_dovecot()

    def install_dovecot_on_centos7(self):
        install_shell = """
yum remove dovecot -y
yum install dovecot-pigeonhole -y
yum install dovecot -y
"""
        public.ExecShell(install_shell)
        return self.conf_dovecot()

    def install_dovecot_on_centos8(self):
        install_shell = """
yum remove dovecot -y
yum install dovecot-pigeonhole -y
yum install dovecot -y
"""
        public.ExecShell(install_shell)
        return self.conf_dovecot()

    def install_postfix_on_ubuntu(self):
        back_shell = ""
        restore_shell = ""
        if os.path.exists("/etc/postfix/main.cf"):
            back_shell = "mv /etc/postfix /etc/postfix_aap_bak"
            restore_shell = """
sudo rm -rf /etc/postfix
mv /etc/postfix_aap_bak /etc/postfix
"""
        install_shell = """
%s
sudo apt remove postfix postfix-sqlite -y
sudo dpkg -P postfix postfix-sqlite
sudo debconf-set-selections <<< "postfix postfix/mailname string ${hostname}"
sudo debconf-set-selections <<< "postfix postfix/main_mailer_type string 'Internet Site'"
sudo apt install postfix -y
sudo apt install postfix-sqlite -y
sudo apt install sqlite -y
%s
""" % (back_shell,restore_shell)
        public.ExecShell(install_shell)

    def install_postfix_on_centos7(self):
        back_shell = ""
        restore_shell = ""
        if os.path.exists("/etc/postfix/main.cf"):
            back_shell = "mv /etc/postfix /etc/postfix_aap_bak"
            restore_shell = """
sudo rm -rf /etc/postfix
mv /etc/postfix_aap_bak /etc/postfix
"""
        install_shell = """
{b}
yum remove postfix -y
wget -O /tmp/postfix3-3.4.7-1.gf.el7.x86_64.rpm {download_conf_url}/install/plugin/mail_sys/rpm/postfix3-3.4.7-1.gf.el7.x86_64.rpm
yum localinstall /tmp/postfix3-3.4.7-1.gf.el7.x86_64.rpm -y
rm -f /tmp/postfix3-3.4.7-1.gf.el7.x86_64.rpm
wget -O /tmp/postfix3-sqlite-3.4.7-1.gf.el7.x86_64.rpm {download_conf_url}/install/plugin/mail_sys/rpm/postfix3-sqlite-3.4.7-1.gf.el7.x86_64.rpm
yum localinstall /tmp/postfix3-sqlite-3.4.7-1.gf.el7.x86_64.rpm -y
/tmp/postfix3-sqlite-3.4.7-1.gf.el7.x86_64.rpm
{r}
""".format(download_conf_url=download_url,b=back_shell,r=restore_shell)
        public.ExecShell(install_shell)

    def install_postfix_on_centos8(self):
        back_shell = ""
        restore_shell = ""
        if os.path.exists("/etc/postfix/main.cf"):
            back_shell = "mv /etc/postfix /etc/postfix_aap_bak"
            restore_shell = """
sudo rm -rf /etc/postfix
mv /etc/postfix_aap_bak /etc/postfix
"""
        install_shell = """
{b}
yum remove postfix -y
wget -O /tmp/postfix3-3.4.9-1.gf.el8.x86_64.rpm {download_conf_url}/install/plugin/mail_sys/rpm/postfix3-3.4.9-1.gf.el8.x86_64.rpm
yum localinstall /tmp/postfix3-3.4.9-1.gf.el8.x86_64.rpm -y
rm -f /tmp/postfix3-3.4.9-1.gf.el8.x86_64.rpm
wget -O /tmp/postfix3-sqlite-3.4.9-1.gf.el8.x86_64.rpm {download_conf_url}/install/plugin/mail_sys/rpm/postfix3-sqlite-3.4.9-1.gf.el8.x86_64.rpm
yum localinstall /tmp/postfix3-sqlite-3.4.9-1.gf.el8.x86_64.rpm -y
rm -f /tmp/postfix3-sqlite-3.4.9-1.gf.el8.x86_64.rpm
{r}
""".format(download_conf_url=download_url,b=back_shell,r=restore_shell)
        public.ExecShell(install_shell)
