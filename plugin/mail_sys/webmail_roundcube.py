# -*- coding: utf-8 -*-
# 部署每个域名下的 webmail-Roundcube

import json
import sys
import time
import os

sys.path.append("class/")
sys.path.append("plugin/mail_sys/")
import public

new_config_path = "/www/server/panel/plugin/mail_sys/roundcube_domains.json"
old_config_path = "/www/server/panel/plugin/mail_sys/roundcube.json"
db_files = {
    'postfixadmin': '/www/vmail/postfixadmin.db',
    'postfixmaillog': '/www/vmail/postfixmaillog.db',
    'mail_unsubscribe': '/www/vmail/mail_unsubscribe.db',
    'abnormal_recipient': '/www/vmail/abnormal_recipient.db',
    'auto_reply': '/www/vmail/auto_reply.db'
}
class Roundcube_main():


    def __init__(self):
        super().__init__()
        # 同步roundcube配置
        self._sync_roundcube_config()
        # 更新roundcube ssl状态
        self._roundcube_ssl_status()


    # 同步旧配置到新配置 mail_sys/roundcube.json -->mail_sys/roundcube_domains.json
    def _sync_roundcube_config(self):
        # 旧配置 格式
        #         {
        #   "status": true,
        #   "id": 2,
        #   "site_name": "webmail.aapanel.com",
        #   "php_version": "80",
        #   "ssl_status": true,
        #   "timestimp": 1733541781
        # }

        # 新配置格式
        #     {
        #   "lootk.cn": {
        #     "status": true,
        #     "id": 124,
        #     "site_name": "webmail.lootk.cn",
        #     "php_version": "74",
        #     "ssl_status": false,
        #     "timestamp": 1741752958,
        #     "mail_domain": "lootk.cn",
        #     "config_file": "/www/wwwroot/webmail.lootk.cn/config/config.inc.php"
        #   }
        # }

        # 检查是否同步过
        mark = "/www/server/panel/plugin/mail_sys/data/check_roundcube_sync.txt"
        if os.path.exists(mark):
            return True

        # 读取旧配置
        if not os.path.exists(old_config_path):
            return True

        old_data = public.readFile(old_config_path)
        if not old_data:
            return True

        old_config = json.loads(old_data)
        if not isinstance(old_config, dict):
            return True
        # 获取webmail域名
        site_name = old_config.get('site_name', '')
        if not site_name:
            return True
        main_domain = '.'.join(site_name.split('.')[-2:])  # 从 webmail.domain.com 获取 domain.com

        # 新配置
        new_config = {
            main_domain: {
                "status": old_config.get('status', True),
                "id": old_config.get('id', 0),
                "site_name": site_name,
                "php_version": old_config.get('php_version', '74'),
                "ssl_status": old_config.get('ssl_status', False),
                "timestamp": old_config.get('timestimp', int(time.time())),
                "mail_domain": main_domain,
                "config_file": f"/www/wwwroot/{site_name}/config/config.inc.php"
            }
        }

        # 写入新配置 如果文件已存在,合并
        if os.path.exists(new_config_path):
            existing_config = json.loads(public.readFile(new_config_path) or '{}')
            existing_config.update(new_config)
            new_config = existing_config

        public.writeFile(new_config_path, json.dumps(new_config, indent=2))

        # # 备份并删除旧配置
        # backup_path = old_config_path + '.bak'
        # public.writeFile(backup_path, old_data)
        # os.remove(old_config_path)
        # 写入标记
        public.writeFile(mark, '1')
        return True


    def _get_multiple_certificate_domain_status(self, domain):
        path = '/www/server/panel/plugin/mail_sys/cert/{}/fullchain.pem'.format(domain)
        ssl_conf = public.readFile('/etc/postfix/vmail_ssl.map')
        if not os.path.exists(path):
            return False
        if not ssl_conf or domain not in ssl_conf:
            return False
        return True

    def _get_roundcube_ssl(self, site_name):
        from data import data
        has_ssl = data().get_site_ssl_info(site_name)
        if has_ssl != -1:
            return True
        else:
            return False
    # 初始化时更新ssl状态
    def _roundcube_ssl_status(self):

        if os.path.exists(old_config_path):
            data = public.readFile(old_config_path)
            if data != '':
                public_data = json.loads(data)

                site_name = public_data['site_name']

                public_data['ssl_status'] = True if self._get_multiple_certificate_domain_status(
                    site_name) or self._get_roundcube_ssl(site_name) else False
                public.writeFile(old_config_path, json.dumps(public_data))

        # 更新多域名多webmail的ssl状态
        if os.path.exists(new_config_path):
            data_all = public.readFile(new_config_path)
            if data_all != '':
                public_data_all = json.loads(data_all)
                # public.print_log(f'public_data_all--{public_data_all}')
                for domain, info in public_data_all.items():
                    site_name = info['site_name']
                    # 更新ssl状态
                    info['ssl_status'] = True if self._get_roundcube_ssl(site_name) else False
                    # public.print_log(f'更新ssl状态--{info}')
                public.writeFile(new_config_path, json.dumps(public_data_all))

    # 一键登录
    def login_roundcube_multiple(self, args):
        '''
        一键登录 roundcube webmail  适用于多webmail
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
        with public.S("mailbox", db_files['postfixadmin']) as obj:
            un = obj.where('username', rc_user).find()
        if not un:
            return public.returnMsg(False, public.lang('User does not exist'))
        # 域名
        domain = un['domain']

        # 获取部署信息
        info = self._get_roundcube_config()
        if not info:
            return public.returnMsg(False, public.lang('Please install roundcube first'))
        # 获取域名配置
        webmail_config = info.get(domain, {})
        if not webmail_config:
            return public.returnMsg(False, public.lang('Please install roundcube first'))

        site_name = webmail_config['site_name']
        # 拼接 ssl与webmail
        protocol = 'https://' if webmail_config.get('ssl_status', False) else 'http://'
        site_url = f"{protocol}{site_name}"

        token = public.GetRandomString(16)
        # 生成文件
        login_name = public.GetRandomString(5) + '.php'
        roundcube_path = '/www/wwwroot/' + site_name + '/'
        file = roundcube_path + login_name
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
        url = "{}/{}?_aap_token={}".format(site_url, login_name, token)
        return url

    # 获取roundcube新配置
    def _get_roundcube_config(self, ):
        # 首先检查新格式配置

        if os.path.exists(new_config_path):
            configs = json.loads(public.readFile(new_config_path) or '{}')
            return configs
        else:
            return {}

    # 获取roundcube新配置
    def get_roundcube_config(self, args):
        # 首先检查新格式配置
        domain = args.get('domain', '')

        if os.path.exists(new_config_path):
            configs = json.loads(public.readFile(new_config_path) or '{}')

            if domain and domain != '':
                # 返回指定域名的配置
                if domain in configs:
                    config = configs[domain]
                    return config
                return False
            else:

                return configs
        else:
            return False

    # 查看是否有 roundcube  旧配置 修复网站误删后数据库残余
    def get_roundcube_status(self,):

        # 版本 "5.1"
        versions = public.get_plugin_info("mail_sys")['versions']
        if versions < "5.1":
            return public.returnMsg(False, public.lang(
                'Please update the plugin to 5.1 or later in "App Store  > Mail Server"'))


        if os.path.exists(old_config_path):
            data = public.readFile(old_config_path)
            public_data = {}
            if data != '':
                public_data = json.loads(data)
                site_name = public_data['site_name']

                # 判断网站是否存在
                panel_domain = public.M('sites').field('id,name,path').select()
                panel_domain_name = [i['name'] for i in panel_domain]
                if site_name not in panel_domain_name:
                    # 删除关联数据库
                    id = public_data['id']
                    find = public.M('databases').where("pid=?", (id,)).field('id,name').find()
                    if find:
                        # public.print_log(f'删除关联数据库 {find}')
                        import database
                        get = public.dict_obj()
                        get.name = find['name']
                        get.id = find['id']
                        database.database().DeleteDatabase(get)
                    return {"status": False}

            return public_data
        else:
            return {"status": False}

    def uninstall_roundcube(self, args):

        if not hasattr(args, 'site_name') or args.get('site_name/s', "") == "":
            return public.returnMsg(False, public.lang('Parameter site_name error'))
        if not hasattr(args, 'id') or args.get('id/s', "") == "":
            return public.returnMsg(False, public.lang('Parameter id error'))
        if not hasattr(args, 'force') or args.get('force/d', 0) == 0:
            args.force = 0
        site_name = args.site_name
        id = args.id
        force = args.force
        from panelSite import panelSite
        if force:
            data = panelSite().DeleteSite(public.to_dict_obj({
                'id': id,
                'webname': site_name,
                'ftp': '1',
                'path': '1',
                'database': '1',
            }))
        else:
            data = panelSite().DeleteSite(public.to_dict_obj({
                'id': id,
                'webname': site_name,
            }))

        if os.path.exists(old_config_path):
            os.remove(old_config_path)
        # 删除另一个配置里的域名数据
        if os.path.exists(new_config_path):
            data_new = public.readFile(new_config_path)
            if data_new != '':
                data_new = json.loads(data_new)
                for domain, info in data_new.items():
                    if info['site_name'] == site_name:
                        del data_new[domain]
                        break
                public.writeFile(new_config_path, json.dumps(data_new))
        public.WriteLog('Mail Server', f'Uninstall webmail: [{site_name}]')
        return data

    # 部署 roundcube  域名分开管理
    def deploy_roundcube(self, args):
        """
        为每个域名添加独立的Roundcube实例
        Args:
            args.domain: 主域名
            args.php_version: PHP版本
        """
        domain = args.get('domain', '')
        if not domain:
            return public.returnMsg(False, public.lang('Please specify the main domain'))

        webmail_domain = args.get('webmail_domain', '')
        # 检查是否有同名网站
        sql = public.M('sites')
        if sql.where("name=?", (webmail_domain,)).count():
            return public.returnMsg(False, public.lang('The site with the same name [{}] already exists, please modify it before creating it',webmail_domain))

        if webmail_domain:
            args.site_name = webmail_domain
        else:
            webmail_domain = f'webmail.{domain}'
            args.site_name = webmail_domain
        args.php_version = args.get('php_version', '74')
        args.dname = 'roundcube'

        # 检查该域名是否已有Roundcube
        if self._check_domain_roundcube(domain):
            return public.returnMsg(False, public.lang(f'{domain} already exists Webmail configuration'))

        # 基础检查（MySQL和Web服务器）
        if not self._check_requirements()['status']:
            return self._check_requirements()

        # 创建网站和数据库
        site_data = self._create_webmail_site(args)
        if not site_data['status']:
            # 清理已创建的资源
            self._cleanup_installation(args.site_name)
            return site_data

        # 部署 roundcube
        import plugin_deployment_v2
        sysObject = plugin_deployment_v2.plugin_deployment()
        deployment = sysObject.SetupPackage_roundcube(args)
        if not deployment['status']:
            # 清理已创建的资源
            self._cleanup_installation(args.site_name)
            return deployment

        # 保存域名特定的配置
        self._save_domain_config(domain, site_data['data'], args)
        public.WriteLog('Mail Server', f'Department Webmail: [{args.site_name}]')

        return public.returnMsg(True, public.lang('Installation successful'))

    def _cleanup_installation(self, site_name):
        """
        清理安装失败的资源
        @param site_name: 网站名称
        """
        try:
            # 使用 DeleteSite 方法一次性清理所有资源
            from panel_site_v2 import panelSite
            get = public.dict_obj()
            get.webname = site_name
            get.id = public.M('sites').where('name=?', (site_name,)).getField('id')
            if get.id:
                # 设置删除参数
                get.ftp = 1  # 删除关联FTP
                get.database = 1  # 删除关联数据库
                get.path = 1  # 删除网站目录

                # 执行删除
                panelSite().DeleteSite(get)

            # 只需要额外删除 Roundcube 特有的配置文件
            self._remove_config_record(site_name)

            public.WriteLog('Roundcube deployment', f'Cleanup installation: {site_name}')

        except Exception as e:
            public.WriteLog('Roundcube deployment', f'Cleanup failed, installation error: {str(e)}')

    def _remove_config_record(self, site_name):
        """删除 Roundcube 配置文件中的记录"""
        try:
            if os.path.exists(new_config_path):
                configs = json.loads(public.readFile(new_config_path) or '{}')
                # 查找并删除对应的域名记录
                for domain, config in list(configs.items()):
                    if config.get('site_name') == site_name:
                        del configs[domain]
                        break
                public.writeFile(new_config_path, json.dumps(configs))
        except:
            pass

    # 检查安装要求 web
    def _check_requirements(self, ):
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
        return public.returnMsg(True, 'True')

    # 检查域名是否已有Roundcube配置
    def _check_domain_roundcube(self, domain):
        """检查域名是否已有Roundcube配置"""
        if os.path.exists(new_config_path):
            configs = json.loads(public.readFile(new_config_path) or '{}')
            if domain in configs:
                # 网站是否存在
                panel_domain = public.M('sites').field('id,name,path').select()
                panel_domain_name = [i['name'] for i in panel_domain]

                if configs[domain]["site_name"] not in panel_domain_name:
                    return False
                # 判断是否部署
                if not os.path.exists(f'/www/wwwroot/{configs[domain]["site_name"]}'):
                    return False
                return True
        return False

    # 创建网站和数据库
    def _create_webmail_site(self, args):
        """创建网站和数据库"""
        from panel_site_v2 import panelSite
        ps = args.site_name.replace('.', '_').replace('-', '_')

        site_config = {
            'webname': json.dumps({
                'domain': args.site_name,
                'domainlist': [],
                'count': 0,
            }),
            'type': 'PHP',
            'version': args.php_version,
            'port': '80',
            'path': f'/www/wwwroot/{args.site_name}',
            'sql': 'MySQL',
            'datauser': f'sql_{ps}',
            'datapassword': public.GetRandomString(16).lower(),
            'codeing': 'utf8mb4',
            'ps': ps,
            'set_ssl': 0,
            'force_ssl': 0,
            'ftp': False,
        }
        # 避免回收站文件影响数据库创建
        site_config['datauser'] = public.ensure_unique_db_name2(site_config['datauser'])

        result = panelSite().AddSite(public.to_dict_obj(site_config))
        # public.print_log(f'创建网站和数据库 result--{result}')
        if int(result.get('status', 0)) != 0:
            return {'status': False, 'msg': result.get('msg', public.lang('Failed to create a site'))}
        return {'status': True, 'data': result.get('message', {})}

    # 保存域名特定的Roundcube配置
    def _save_domain_config(self, domain, site_data, args):
        """保存域名特定的Roundcube配置"""
        configs = {}
        if os.path.exists(new_config_path):
            configs = json.loads(public.readFile(new_config_path) or '{}')

        # 添加新域名配置
        configs[domain] = {
            "status": True,
            "id": site_data['siteId'],
            "site_name": args.site_name,
            "php_version": args.php_version,
            "ssl_status": False,
            "timestamp": int(time.time()),
            "mail_domain": domain,
            "config_file": f"/www/wwwroot/{args.site_name}/config/config.inc.php"
        }

        public.writeFile(new_config_path, json.dumps(configs))
