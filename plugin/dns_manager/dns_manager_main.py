#coding: utf-8
# +-------------------------------------------------------------------
# | aapanel
# +-------------------------------------------------------------------
# | Copyright (c) 2015-2019 宝塔软件(http://bt.cn) All rights reserved.
# +-------------------------------------------------------------------
# | Author: 邹浩文 <627622230@qq.com>
# +-------------------------------------------------------------------

#--------------------------------
# Dns管理器
#--------------------------------

import os
os.chdir("/www/server/panel")
import public, re, psutil, json, time
try:
    import urllib2
except:
    import urllib as urllib2
    urllib2 = urllib2.request
class dns_manager_main(object):
    def __init__(self):
        self.net_path = "/etc/sysconfig/network-scripts/"
        self.config = "/www/server/panel/plugin/dns_manager/config.json"
        self.path = "/www/server/panel/plugin/dns_manager/"
        self.dns_conf_path = "/var/named/chroot"
        self.zone_file = self.dns_conf_path + "/etc/named.rfc1912.zones"
        if self.dns_server_check() == "pdns":
            self._pdns_compatible()


    # # 获取公网ip
    def __check_pubilc_ip(self):
        """
            @name 获取服务器公网IP
            @author zhwen<zhw@bt.cn>
            @param ip_address 获取到的IP公网地址
            @return string IP地址
        """
        try:
            url = 'http://pv.sohu.com/cityjson?ie=utf-8'
            opener = urllib2.urlopen(url,timeout=3)
            m_str = opener.read()
            if isinstance(m_str,bytes):
                ip_address = re.search('\d+.\d+.\d+.\d+', m_str.decode('utf-8')).group(0)
            else:
                ip_address = re.search('\d+.\d+.\d+.\d+', m_str).group(0)
            c_ip = public.check_ip(ip_address)
            if not c_ip:
                a, e = public.ExecShell("curl ifconfig.me")
                return a
            return ip_address
        except:
            filename = '/www/server/panel/data/iplist.txt'
            ip_address = public.readFile(filename).strip()
            if ip_address:
                return ip_address
            else:
                return False
    # 获取公网网卡
    def __check_card(self,ip):
        """
            @name 检查ip是否在存在的网卡中
            @author zhwen<zhw@bt.cn>
            @param net_info 所有网卡信息
            @return dict 返回公网网卡状态
        """
        net_info = psutil.net_if_addrs()
        if net_info:
            for card in net_info.values():
                if ip == card[0].address:
                    return {"ip": True}

    # 构造子网卡名和获取网卡
    def __get_sub_card_name(self):
        """
            @name 构造子网卡名和获取网卡
            @author zhwen<zhw@bt.cn>
            @param net_info 所有网卡信息
            @param net_card 构造的子网卡信息
            @return dict 返回构造的子网卡信息
        """
        net_card = {}
        net_info = psutil.net_if_addrs()
        for card in net_info.keys():
            card_name_list = ["eth","ens","em"]
            for i in card_name_list:
                if i in card:
                    sub_card = "{}:0".format(card)
                    net_card["sub_card"] = sub_card
                    net_card["card"] = card
                    return net_card

    # 备份网卡配置
    def __back_card(self):
        """
            @name 备份网卡配置
            @author zhwen<zhw@bt.cn>
            @param net_card 子网卡名
            @param source 网卡名称
        """
        net_card = self.__get_sub_card_name()
        source = self.net_path + "ifcfg-" + net_card["card"]
        target = source + "_bak"
        public.ExecShell("cp {0} {1}".format(source, target))

    # 还原所有网卡配置
    def __restore_card(self):
        """
            @name 还原所有网卡配置
            @author zhwen<zhw@bt.cn>
            @param net_card 子网卡名
            @param sub_card 子网卡完整路径
        """
        net_card = self.__get_sub_card_name()
        sub_card = self.net_path + "ifcfg-" + net_card["sub_card"]
        source = self.net_path + "ifcfg-" + net_card["card"]
        target = source + "_bak"
        public.ExecShell("rm -f {0} && ifdown {1}".format(sub_card, net_card["sub_card"]))
        public.ExecShell("rm -f {0} && mv {1} {0}".format(source, target))
        public.ExecShell("ifdown {0} && ifup {0}".format(net_card["card"]))

    # 创建子网卡
    def __create_subcard(self,ip):
        """
            @name 创建子网卡
            @author zhwen<zhw@bt.cn>
            @param sub_card 子网卡名
            @param sub_card_path 子网卡完整路径
        """
        self.__back_card()
        net_card = self.__get_sub_card_name()
        sub_card = net_card["sub_card"]
        if sub_card:
            content = """DEVICE={0}
IPADDR={1}
NETMASK=255.255.255.0
ONBOOT=yes
"""
            content = content.format(sub_card, ip)
            sub_card_path = self.net_path + "ifcfg-" + sub_card
            public.writeFile(sub_card_path, content)
            public.ExecShell("ifup {}".format(sub_card))
        if not self.__check_net_work():
            self.__restore_card()
            return public.ReturnMsg(False, "Failed to create a self-network card, please contact the official staff")
        return public.ReturnMsg(True, "Success")

    # 获取可以监听的IP
    def get_can_listen_ip(self,get):
        """
            @name 获取可以监听的IP
            @author zhwen<zhw@bt.cn>
            @param sub_card 子网卡名
            @param sub_card_path 子网卡完整路径
        """
        public_ip = self.__check_pubilc_ip()
        net_info = psutil.net_if_addrs()
        addr = []
        for i in net_info.values():
            if i[0].address == "127.0.0.1":
                continue
            addr.append(i[0].address)
        if not public_ip in addr:
            addr.append(public_ip)
        addr.append('any')
        return addr

    # 选择监听地址
    def set_listen_ip(self,get):
        """
            @name 选择监听地址
            @author zhwen<zhw@bt.cn>
            @param ip 需要设置监听的ip
            @param conffile bind9的主配置文件
            只有dnsserver为bind9的时候才需要设置
        """
        values = self.__check_give_vaule(get)
        if "listen_ip" not in values:
            return public.ReturnMsg(False, "Please enter listen ip")
        ip = values["listen_ip"]
        if ip != "any" and not self.__check_card(ip):
            result = self.__create_subcard(ip)
            if not result["status"]:
                return result
        conffile = self.dns_conf_path+"/etc/named.conf"
        self.__back_file(conffile)
        conf = public.readFile(conffile)
        rep = "\d+\s+\{\s*([\w\.]+)"
        if ":" in ip:
            rep = "\d+\s+\{\s*([\w\:]+)"
        new_conf = re.sub(rep,"53 { "+values["listen_ip"],conf)
        public.writeFile(conffile,new_conf)
        cc = self.__check_conf()
        if cc:
            self.__restore_file(conffile)
            return public.ReturnMsg(False, "Configuration failed "+ str(cc))
        config = self.__read_config(self.config)
        config["listen_ip"] = ip
        self.__write_config(self.config,config)
        public.ExecShell("systemctl restart named-chroot")
        return public.ReturnMsg(True, "Configuration successful")

    # 获取监听ip
    def __get_listen_ip(self):
        """
            @name 获取监听ip
            @author zhwen<zhw@bt.cn>
            @param config bind9的主配置文件
        """
        config = self.__read_config(self.config)
        if not config["listen_ip"]:
            return self.__check_pubilc_ip()
        return config["listen_ip"]

    # 检测网络连接
    def __check_net_work(self):
        """
            @name 检测网络连接
            @author zhwen<zhw@bt.cn>
        """
        urlList = ["http://www.baidu.com", "http://www.google.com"]
        for url in urlList:
            try:
                if os.path.exists('/www/server/panel/pyenv'):
            	    import requests
            	    opener = requests.get(url)
            	    opener.text()
                else:
                    opener = urllib2.urlopen(url)
                    opener.read()
                return True
            except:
                return False

    def get_my_ip(self,values):
        ip = values['domain_ip']
        if not ip:
            ip = self.__get_listen_ip()
            if str(ip) == "any":
                ip = self.__check_pubilc_ip()
            type = "A"
            if ":" in ip:
                type = "AAAA"
                ip = ip.replace('[', '').replace(']', '')
        else:
            type = "A"
            if ":" in ip:type = "AAAA"
        return ip,type

    # 创建默认域名解析配置
    def __create_dns_resolve(self, values):
        """
            @name 创建默认域名解析配置
            @author zhwen<zhw@bt.cn>
            @param domain 需要添加解析的域名
            @param ip 获取到的服务器公网IP
            @param resolve_file zone文件路径
        """
        domain = values["domain"]
        ip,type = self.get_my_ip(values)
        if not values['soa']:
            values['soa'] = "ns1." + domain + '.'
            nsconf = self.__read_config(self.config)
            if 'NS' in nsconf:
                values['soa'] = nsconf['NS']['NS1']
        serial = time.strftime("%Y%m%d", time.localtime())+'01'
        resolve_file = "{0}/var/named/{1}.zone".format(self.dns_conf_path, domain)
        resolve_conf = """$TTL 86400
{0}.      IN SOA  {4}     admin.{0}. (
                                        {5}       ; serial
                                        7200      ; refresh
                                        3600      ; retry
                                        1209600      ; expire
                                        180 )    ; minimum
{3}
{0}.            600     IN      {2}        {1}
{0}.            600     IN      MX 10      mail.{0}.
{0}.            600     IN      CAA        0 issue "letsencrypt.org"
www             600     IN      {2}        {1}
mail            600     IN      {2}        {1}
ns1             600     IN      {2}        {1}
ns2             600     IN      {2}        {1}
""".format(domain, ip, type,values["nsservers"],values['soa'],serial)
        public.writeFile(resolve_file, resolve_conf)
        self.__back_file(resolve_file, act="def")
        return type

    # 测试域名解析
    def __check_domain_resolve(self, domain, host="",type="A",value=None):
        """
            @name 测试域名解析是否正常
            @author zhwen<zhw@bt.cn>
            @param domain 需要添加解析的域名
            @param ip 获取到的服务器公网IP
            @param host 主机名
        """
        try:
            import dns.resolver
        except:
            public.ExecShell("/usr/bin/pip install dnspython")
            try:
                import dns.resolver
            except:
                return public.ReturnMsg(False,'Please manually execute the following command to install dnspython before attempting again:/usr/bin/pip install dnspython')
        ip = self.__get_listen_ip()
        if str(ip) == "any":
            ip = self.__check_pubilc_ip()
        if self.dns_server_check() == "pdns":
            ip = "127.0.0.1"
        my_resolver = dns.resolver.Resolver()
        my_resolver.nameservers = [ip]
        if host:
            domain = host+"."+domain
        try:
            l = []
            a = my_resolver.query(domain, type)
            for i in a.response.answer:
                for j in i.items:
                    l.append(str(j))
            if not value:
                return l
            for i in l:
                if type == 'CAA':
                    if value['ca_domain_name'] in i:
                        return l
                    l.pop()
                    if not l:
                        return False
                if type == 'HINFO':
                    if re.search('{}\s+{}'.format(value['cpu'],value['operatingsystem']),i):
                        return l
                if type == 'SRV':
                    if re.search('{}\s+{}\s+{}\s+{}'.format(value['priority'],value['weight'],value['port'],value['target']),i):
                        return l
                if type == 'AFSDB':
                    if re.search('{}\s+{}'.format(value['subtype'],value['hostname']),i):
                        return l
                if type == 'RP':
                    if re.search('{}\s+{}'.format(value['mboxdname'],value['txtdname']),i):
                        return l
                if type == 'TXT':
                    i = i.replace('" "','')
                if value['value'] in i:
                    return l
        except:
            return False

    # 检查域名是否已经存在
    def __check_domain_exist(self,domain):
        """
            @name 检查域名是否已经存在
            @author zhwen<zhw@bt.cn>
            @param config dns管理配置文件
        """
        config = self.__read_config(self.config)
        for i in config["domain"]:
            if i == domain:
                return True

    # 读配置
    def __read_config(self, path):
        """
            @name 读配置
            @author zhwen<zhw@bt.cn>
            @param path 配置路径
        """
        if not os.path.exists(path) or not public.readFile(path):
                public.writeFile(path, json.dumps({"domain":[],"listen_ip":""}))
        upBody = public.readFile(path)
        return json.loads(upBody)

    # 写配置
    def __write_config(self ,path, data):
        """
            @name 写配置
            @author zhwen<zhw@bt.cn>
            @param path 配置路径
            @param data 配置内容
        """
        public.writeFile(path, json.dumps(data))

    def set_default_ns(self,args):
        """
            @name 设置默认NS服务器
            @author zhwen<zhw@bt.cn>
            @param ns1 服务器1
            @param ns2 服务器2
        """
        vaules = self.__check_give_vaule(args)
        ns = self.__read_config(self.config)
        if 'ns1' not in vaules and 'ns2' not in vaules:
            ns['NS'] = {'NS1': '', 'NS2': ''}
        elif 'ns1' not in vaules or 'ns2' not in vaules:
            return public.ReturnMsg(False, 'You must setup NS1 NS2 as the same time')
        elif 'NS' in ns:
            ns['NS']['NS1'] = vaules['ns1']
            ns['NS']['NS2'] = vaules['ns2']
        else:
            ns['NS'] = {'NS1':vaules['ns1'],'NS2':vaules['ns2']}
        self.__write_config(self.config, ns)
        return public.ReturnMsg(True,'Setup successfully')

    def get_default_ns(self,args):
        ns = self.__read_config(self.config)
        if 'NS' in ns:
            return ns['NS']
        return {'NS1':'','NS2':''}

    # 构造ns记录
    def _make_ns_record(self,values):
        """
            @name 构造ns记录
            @author zhwen<zhw@bt.cn>
            @param values ns服务器域名
        """

        if not (values["ns1domain"] or values["ns2domain"]):
            values["nsservers"] = """
{0}.            86400   IN      NS         ns1.{0}.
{0}.            86400   IN      NS         ns2.{0}.""".format(values["domain"])
            config = self.__read_config(self.config)
            if "NS" in config and config['NS']['NS1'] and config['NS']['NS1']:
                values["nsservers"] = """
{0}.            86400   IN      NS         {1}
{0}.            86400   IN      NS         {2}""".format(values["domain"],
                                                                              config['NS']['NS1'],
                                                                              config['NS']['NS2'])
        else:
            values["nsservers"] = """
{0}.            86400   IN      NS         {1}.
{0}.            86400   IN      NS         {2}.""".format(values["domain"], values["ns1domain"],
                                                                  values["ns2domain"])
        return values

    def _check_bind_conf(self,domain):
        """
            @name 检查bind服务的配置
            @author zhwen<zhw@bt.cn>
            @param domain 域名
            只有dns服务为bind时才需要检查
        """
        cc = self.__check_conf()
        if cc:
            self.__restore_file(self.zone_file)
            resolve_file = "{0}/var/named/{1}.zone".format(self.dns_conf_path, domain)
            if os.path.exists(resolve_file):
                os.remove(resolve_file)
            return public.ReturnMsg(False, "Add domain name failed2 " + str(cc))
        public.ExecShell("systemctl restart named-chroot")

    # 添加二级域
    def add_domain(self, get):
        """
            @name 添加二级域
            @author zhwen<zhw@bt.cn>
            @param values 验证后的参数
            @param domain 需要添加的域名
            @param IP 需要设置IP
            @param zone_config 需要添加的域名 zone
        """
        self.__release_port(get)
        values = self.__check_give_vaule(get)
        if "status" in values.keys():
            return values
        values = self._make_ns_record(values)
        domain = values["domain"]
        if self.__check_domain_exist(domain):
            return public.ReturnMsg(False, "Domain name already exists")
        zone_config = """
zone "%s" IN {
        type master;
        file "/var/named/chroot/var/named/%s.zone";
        allow-update { none; };
};
""" % (domain, domain)
        self.__back_file(self.zone_file)
        public.writeFile(self.zone_file,zone_config,"a+")
        dns_type = self.__create_dns_resolve(values)
        if dns_type:
            if self.dns_server_check() == 'bind':
                self._check_bind_conf(domain)
            else:
                public.ExecShell('systemctl restart pdns')

            check_result= self.__check_domain_resolve(domain,type=dns_type)
            if check_result:
                if 'status' in check_result:return check_result
                config = self.__read_config(self.config)
                config["domain"].append(domain)
                self.__write_config(self.config, config)
                public.WriteLog('DNS', 'Add domain name [' + domain + '] successful')
                return public.ReturnMsg(True, "Add domain name successfully")
        public.WriteLog('DNS', 'Add domain name [' + domain + '] failed')
        self.__restore_file(self.zone_file)
        return public.ReturnMsg(False, "Add domain name failed1")

    # 获取域名列表
    def get_domain_list(self, get):
        """
            @name 获取域名列表
            @author zhwen<zhw@bt.cn>
            @param config dns管理器数据文件
        """
        config = self.__read_config(self.config)
        if config["domain"]:
            return public.ReturnMsg(True, config["domain"])
        if not self.__get_listen_ip():
            return "0"
        return public.ReturnMsg(True, config["domain"])

    # 删除区域配置
    def __delete_zone(self,domain):
        """
            @name 删除区域配置
            @author zhwen<zhw@bt.cn>
            @param domain 需要删除的域名
            @param reg 匹配需要删除的域名正则
        """
        zone_conf = public.readFile(self.zone_file)
        # reg = '\n*zone\s+"%s"(.|\n)+"%s.+\n\s+allow.+\n};\n*' % (domain,domain)
        reg = '\n*zone\s+"%s"(.|\n)+%s\.zone";\n\s+allow.+\n};\n*' % (domain,domain)
        zone_conf = re.sub(reg,"",zone_conf)
        public.writeFile(self.zone_file,zone_conf)

    # 删除域名
    def delete_domain(self, get):
        """
            @name 删除域名
            @author zhwen<zhw@bt.cn>
            @param domain 需要删除的域名
            @param resolve_file 该域名的区域文件
        """
        values = self.__check_give_vaule(get)
        if "status" in values.keys():
            return values
        domain = values["domain"]
        config = self.__read_config(self.config)
        if domain in config["domain"]:
            config["domain"].remove(domain)
            self.__write_config(self.config,config)
            resolve_file = "{0}/var/named/{1}.zone".format(self.dns_conf_path, domain)
            r_l = [resolve_file,resolve_file+"_bak",resolve_file + "_def"]
            for i in r_l:
                if os.path.exists(i):
                    os.remove(i)
            self.__delete_zone(domain)
            public.ExecShell("systemctl restart named-chroot")
            public.WriteLog('DNS', 'Delete domain name [' + domain + '] successful')
            return public.ReturnMsg(True, "Delete domain name successful")

    # 判断解析是否存在
    def __check_resolve_exist(self,zone_file,values):
        """
            @name 判断解析是否存在
            @author zhwen<zhw@bt.cn>
            @param values 相应参数
            @param zone_file 该域名的解析文件
        """
        v = values.copy()
        if "id" in v:
            id = str(v["id"])
        else:
            id = ""
        if v["act"] == "modify" and id:
            old_conf = self.__read_config(self.path+"tmp")
            old_conf = old_conf[id]
            v["host"] = old_conf["host"]
            v["ttl"] = old_conf["ttl"]
            v["type"] = old_conf["type"]
            if "MX" == old_conf['type']:
                v["mx_priority"] = old_conf["mx_priority"]
                v["value"] = old_conf["value"]
            elif "CAA" == old_conf['type']:
                v["flags"] = old_conf["flags"]
                v["tag"] = old_conf["tag"]
                v["ca_domain_name"] = old_conf["ca_domain_name"]
            elif "AFSDB" == old_conf['type']:
                v["subtype"] = old_conf["subtype"]
                v["hostname"] = old_conf["hostname"]
            elif "DS" == old_conf['type']:
                v["keytag"] = old_conf["keytag"]
                v["algorithm"] = old_conf["algorithm"]
                v["digesttype"] = old_conf["digesttype"]
                v["digest"] = old_conf["digest"]
            elif "HINFO" == old_conf['type']:
                v["cpu"] = old_conf["cpu"]
                v["operatingsystem"] = old_conf["operatingsystem"]
            elif "LOC" == old_conf['type']:
                v["latitude"] = old_conf["latitude"]
                v["longitude"] = old_conf["longitude"]
                v["altitude"] = old_conf["altitude"]
                v["size"] = old_conf["size"]
                v["horizontal"] = old_conf["horizontal"]
                v["vertical"] = old_conf["vertical"]
            elif "NAPTR" == old_conf['type']:
                v["order"] = old_conf["order"]
                v["preference"] = old_conf["preference"]
                v["service"] = old_conf["service"]
                v["regexp"] = old_conf["regexp"]
                v["replacement"] = old_conf["replacement"]
            elif "RP" == old_conf['type']:
                v["mboxdname"] = old_conf["mboxdname"]
                v["txtdname"] = old_conf["txtdname"]
            elif "SRV" == old_conf['type']:
                v["priority"] = old_conf["priority"]
                v["weight"] = old_conf["weight"]
                v["port"] = old_conf["port"]
                v["target"] = old_conf["target"]
            else:
                if "value" in old_conf:
                    v["value"] = old_conf["value"]
        if v["act"] != "add" and "value" in v:
            if '"' in v["value"]:
                v["value"] = '"{}"'.format(v["value"].replace('"',""))
        if v["host"] == "*":
            v["host"] = "\*"
        with open(zone_file) as f:
            for i in f.readlines():
                if "value" in v:
                    value=v['value']
                    for f in ["$","?","+","^","*","(",")"]:
                        value = value.replace(f,'\\'+f)

                if v["type"] == "MX":
                    rep = "{host}\s+{ttl}\s+IN\s+{type}\s+{mx_priority}\s+{value}".format(host=v["host"], type=v["type"],
                                                                                          mx_priority=v["mx_priority"],
                                                                                          ttl=v["ttl"], value=v["value"])
                elif v['type'] == 'CAA':
                    rep = "{host}\s+{ttl}\s+IN\s+{type}\s+{flags}\s+{tag}\s+\"?{ca_domain_name}\"?".format(host=v["host"],
                        type=v["type"],ttl=v["ttl"],flags=v["flags"],tag=v['tag'],ca_domain_name=v['ca_domain_name'])
                elif v["type"] == "AFSDB":
                    rep = "{host}\s+{ttl}\s+IN\s+{type}\s+{subtype}\s+{hostname}.*".format(host=v["host"],
                                                                                              type=v["type"],
                                                                                              subtype=v["subtype"],
                                                                                              ttl=v["ttl"],
                                                                                              hostname=v[
                                                                                                  "hostname"])

                elif v['type'] == "DS":
                    rep = "{host}\s+{ttl}\s+IN\s+{type}\s+{keytag}\s+{algorithm}\s+{digesttype}\s+{digest}.*".format(
                        host=v["host"],
                        type=v["type"],
                        keytag=v["keytag"],
                        ttl=v["ttl"],
                        algorithm=v["algorithm"],
                        digesttype=v['digesttype'],
                        digest=v['digest'])
                elif v["type"] == "HINFO":
                    rep = "{host}\s+{ttl}\s+IN\s+{type}\s+\"?{cpu}\"?\s+\"?{operatingsystem}\"?.*".format(host=v["host"],
                                                                                                 type=v["type"],
                                                                                                 cpu=v["cpu"],
                                                                                                 ttl=v["ttl"],
                                                                                                 operatingsystem=v[
                                                                                                     "operatingsystem"])
                elif v["type"] == "LOC":
                    rep = "{host}\s+{ttl}\s+IN\s+{type}\s+{latitude}\s+{longitude}\s+{altitude}\s+{size}\s+{horizontal}\s+{vertical}.*".format(
                        host=v["host"],
                        type=v["type"],
                        latitude=v["latitude"],
                        ttl=v["ttl"],
                        longitude=v["longitude"],
                        altitude=v["altitude"],
                        size=v["size"],
                        horizontal=v['horizontal'],
                        vertical=v['vertical'])

                elif v["type"] == "NAPTR":
                    rep = '{host}\s+{ttl}\s+IN\s+{type}\s+{order}\s+{preference}\s+{flags}\s+{service}\s+{regexp}\s+{replacement}.*'.format(
                        host=v["host"],
                        type=v["type"],
                        order=v["order"],
                        ttl=v["ttl"],
                        preference=v["preference"],
                        flags=v["flags"],
                        service=v["service"],
                        regexp=v['regexp'],
                        replacement=v['replacement'])
                elif v["type"] == "RP":
                    rep = "{host}\s+{ttl}\s+IN\s+{type}\s+{mboxdname}\s+{txtdname}.*".format(host=v["host"],
                                                                                                type=v["type"],
                                                                                                mboxdname=v[
                                                                                                    "mboxdname"],
                                                                                                ttl=v["ttl"],
                                                                                                txtdname=v[
                                                                                                    "txtdname"])
                elif v["type"] == "SRV":
                    rep = "{host}\s+{ttl}\s+IN\s+{type}\s+{priority}\s+{weight}\s+{port}\s+{target}.*".format(
                        host=v["host"],
                        type=v["type"],
                        priority=v["priority"],
                        ttl=v["ttl"],
                        weight=v["weight"],
                        port=v["port"],
                        target=v["target"])
                else:
                    rep = "{host}\s+{ttl}\s+IN\s+{type}\s+\"?{value}\"?.*".format(host=v["host"], type=v["type"],
                                                                                ttl=v["ttl"],
                                                                                value=value)
                result = re.search(rep, i)
                if result:
                    return result

    # 备份配置文件
    def __back_file(self, file, act=None):
        """
            @name 备份配置文件
            @author zhwen<zhw@bt.cn>
            @param file 需要备份的文件
            @param act 如果存在，则备份一份作为默认配置
        """
        file_type = "_bak"
        if act:
            file_type = "_def"
        public.ExecShell("/usr/bin/cp -p {0} {1}".format(file, file + file_type))

    # 还原配置文件
    def __restore_file(self, file, act=None):
        """
            @name 还原配置文件
            @author zhwen<zhw@bt.cn>
            @param file 需要还原的文件
            @param act 如果存在，则还原默认配置
        """
        file_type = "_bak"
        if act:
            file_type = "_def"
        public.ExecShell("/usr/bin/cp -p {1} {0}".format(file, file + file_type))

    # 测试配置文件
    def __check_conf(self):
        """
            @name 测试配置文件
            @author zhwen<zhw@bt.cn>
            只有dnsserver为bind9时才需要
        """
        a, e = public.ExecShell("/usr/sbin/named-checkconf -t /var/named/chroot -z")
        c = re.search("(error|failed|missing)", a)
        if c or e:
            return [a,e]

    # 解析域名文件
    def __edit_resolve_file(self, zone_file, act, values):
        """
            @name 编辑解析域名文件
            @author zhwen<zhw@bt.cn>
            @parma zone_file 解析文件的路径
            @parma act 操作方法 添加/删除/修改
            @parma values 相应参数
        """
        if values["type"] == "MX":
            add_resolve = "\n{host}\t{ttl}\tIN\t{type}\t{mx_priority}\t{value}\n".format(host=values["host"],
                                                                                       type=values["type"],
                                                                                       mx_priority=values["mx_priority"],
                                                                                       ttl=values["ttl"],
                                                                                       value=values["value"])
        elif values["type"] == "CAA":
            add_resolve = "\n{host}\t{ttl}\tIN\t{type}\t{flags} {tag} {ca_domain_name}\n".format(host=values["host"],
                                                                                                type=values["type"],
                                                                                                ttl=values["ttl"],
                                                                                                flags=values["flags"],
                                                                                                tag=values['tag'],
                                                                                                ca_domain_name =values['ca_domain_name'])
        elif values["type"] == "AFSDB":
            add_resolve = "\n{host}\t{ttl}\tIN\t{type}\t{subtype}\t{hostname}\n".format(host=values["host"],
                                                                                      type=values["type"],
                                                                                      subtype=values["subtype"],
                                                                                      ttl=values["ttl"],
                                                                                      hostname=values["hostname"])

        elif values['type'] == "DS":
            add_resolve = "\n{host}\t{ttl}\tIN\t{type}\t{keytag}\t{algorithm}\t{digesttype}\t{digest}\n".format(host=values["host"],
                                                                                                              type=values["type"],
                                                                                                              keytag=values["keytag"],
                                                                                                              ttl=values["ttl"],
                                                                                                              algorithm=values["algorithm"],
                                                                                                              digesttype=values['digesttype'],
                                                                                                              digest=values['digest'])
        elif values["type"] == "HINFO":
            add_resolve = "\n{host}\t{ttl}\tIN\t{type}\t{cpu}\t{operatingsystem}\n".format(host=values["host"],
                                                                                      type=values["type"],
                                                                                      cpu=values["cpu"],
                                                                                      ttl=values["ttl"],
                                                                                      operatingsystem=values["operatingsystem"])
        elif values["type"] == "LOC":
            add_resolve = "\n{host}\t{ttl}\tIN\t{type}\t{latitude}\t{longitude}\t{altitude}\t{size}\t{horizontal}\t{vertical}\n".format(
                                                                                        host=values["host"],
                                                                                        type=values["type"],
                                                                                        latitude=values["latitude"],
                                                                                        ttl=values["ttl"],
                                                                                        longitude=values["longitude"],
                                                                                        altitude=values["altitude"],
                                                                                        size=values["size"],
                                                                                        horizontal=values['horizontal'],
                                                                                        vertical=values['vertical'])
        elif values["type"] == "NAPTR":
            add_resolve = '\n{host}\t{ttl}\tIN\t{type}\t{order}\t{preference}\t{flags}\t{service}\t{regexp}\t{replacement}\n'.format(
                                                                                        host=values["host"],
                                                                                        type=values["type"],
                                                                                        order=values["order"],
                                                                                        ttl=values["ttl"],
                                                                                        preference=values["preference"],
                                                                                        flags=values["flags"],
                                                                                        service=values["service"],
                                                                                        regexp=values['regexp'],
                                                                                        replacement=values['replacement'])
        elif values["type"] == "RP":
            add_resolve = "\n{host}\t{ttl}\tIN\t{type}\t{mboxdname}\t{txtdname}\n".format(host=values["host"],
                                                                                      type=values["type"],
                                                                                      mboxdname=values["mboxdname"],
                                                                                      ttl=values["ttl"],
                                                                                      txtdname=values["txtdname"])
        elif values["type"] == "SRV":
            add_resolve = "\n{host}\t{ttl}\tIN\t{type}\t{priority}\t{weight}\t{port}\t{target}\n".format(
                                                                                        host=values["host"],
                                                                                        type=values["type"],
                                                                                        priority=values["priority"],
                                                                                        ttl=values["ttl"],
                                                                                        weight=values["weight"],
                                                                                        port=values["port"],
                                                                                        target=values["target"])
        else:
            add_resolve = "\n{host}\t{ttl}\tIN\t{type}\t{value}\n".format(host=values["host"],
                                                                        type=values["type"],
                                                                        ttl=values["ttl"],
                                                                        value=values["value"])
        result = self.__check_resolve_exist(zone_file, values)
        zone_conf = public.readFile(zone_file)
        if act == "add" and result:
            return True
        self.__back_file(zone_file)
        if act == "add" and not result:
            public.writeFile(zone_file, add_resolve, "a+")
        if act == "delete" and result:
            tmp = zone_conf.replace(result.group(0),"")
            new_conf = ""
            for i in tmp.splitlines():
                if i:
                    new_conf += i+"\n"
            public.writeFile(zone_file, new_conf)
        if act == "modify" and result:
            tmp = zone_conf.replace(result.group(0), add_resolve[:-1])
            public.writeFile(zone_file, tmp)
        if self.__check_conf() and self.dns_server_check() != "pdns":
            self.__restore_file(zone_file)
            return True

    # 操作解析
    def act_resolve(self, get):
        """
            @name 操作解析
            @author zhwen<zhw@bt.cn>
            @parma domain 需要操作的
            @parma act 操作方法 添加/删除/修改
            @parma values 验证过后的参数
        """
        values = self.__check_give_vaule(get)
        if "status" in values.keys():
            return values
        domain = values["domain"]
        act = values["act"]
        d = {"delete":"Delete","add":"Add","modify":"Modify"}
        zone_dir = "/var/named/chroot/var/named/"
        get_file = domain + ".zone"
        zone_file = zone_dir+get_file
        if not self.__edit_resolve_file(zone_file, act, values):
            self._dnssever_restart()
            v = values["host"]
            if v == "@" or v == domain + ".":
                v = ""
            if values["type"] not in ["NS","LOC","NAPTR"]:
                check_result= self.__check_domain_resolve(domain, host=v,type=values["type"],value=values)
                if check_result and 'status' in check_result:
                    return check_result
                if not check_result and values["act"] == "delete":
                    public.WriteLog('DNS', '{0} resolve {1} successful'.format(domain, d[act]))
                    return public.ReturnMsg(True, '{0} successful'.format(d[act]))
                elif check_result and values["act"] != "delete":
                    public.WriteLog('DNS', '{0} resolve {1} successful'.format(domain, d[act]))
                    return public.ReturnMsg(True, '{0} successful'.format(d[act]))
                else:
                    return public.ReturnMsg(False, '{0} Fail'.format(d[act]))
            else:
                public.WriteLog('DNS', '{0} resolve {1} successful'.format(domain, d[act]))
                return public.ReturnMsg(True, '{0} successful'.format(d[act]))
        public.WriteLog('DNS', 'resolve {0} failed, please check if the hostname already exists'.format(domain,d[act]))
        return public.ReturnMsg(False, '{0} failed, please check if the hostname already exists'.format(d[act]))

    # 配置转换json
    def __change_json(self, data):
        """
            @name bind文件配置转换json
            @author zhwen<zhw@bt.cn>
            @param data bind配置内容
            @parma values 验证过后的参数
        """
        conf_json = {}
        n = 0
        for i in data.splitlines():
            try:
                tmp = i.split()
                if "MX" == tmp[3]:
                    rep = "([\w\.\*\-\_]+|@)\s+(\d+)\s+\w+\s+(\w+)\s+(\w+)\s+([\w\.\"]+.*)"
                elif 'CAA' == tmp[3]:
                    rep = "([\w\.\*\-\_]+|@)\s+(\d+)\s+\w+\s+(\w+)\s+(\d+)\s+(\w+)\s+\"([\w\.\"]+.*)\""
                elif 'AFSDB' == tmp[3]:
                    rep = "([\w\.\*\-\_]+|@)\s+(\d+)\s+\w+\s+(\w+)\s+(\d+)\s+([\w\.\"]+.*)"
                elif 'DS' == tmp[3]:
                    rep = "([\w\.\*\-\_]+|@)\s+(\d+)\s+\w+\s+(\w+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\da-fA-F]+)"
                elif 'HINFO' == tmp[3]:
                    rep = "([\w\.\*\-\_]+|@)\s+(\d+)\s+\w+\s+(\w+)\s+\"([A-Z]+[-/A-Z\d]+[\dA-Z])\"\s+\"([A-Z]+[\/\.\-A-Z\d]+[\dA-Z])\""
                elif 'LOC' == tmp[3]:
                    rep = "([\w\.\*\-\_]+|@)\s+(\d+)\s+\w+\s+(\w+)\s+(\d{1,2}\s+\d{1,2}\s+\d{1,2}\.\d{3}\s+[NS])\s+(\d{1,2}\s+\d{1,2}\s+\d{1,2}\.\d{3}\s+[EW])\s+([-\d\.]+m)\s+([-\d\.]+m)\s+([-\d\.]+m)\s+([-\d\.]+m)"
                elif 'NAPTR' == tmp[3]:
                    rep = "([\w\.\*\-\_]+|@)\s+(\d+)\s+\w+\s+(\w+)\s+(\d{1,5})\s+(\d{1,5})\s+\"(\d{1,5})\"\s+\"(\w{1,32})\"\s+\"(!.*!.*!)\"\s+(.*)"
                elif 'RP' == tmp[3]:
                    rep = "([\w\.\*\-\_]+|@)\s+(\d+)\s+\w+\s+(\w+)\s+([\w\.\-\_]+)\s+([\w\.\-\_]+)"
                elif 'SRV' == tmp[3]:
                    rep = "([\w\.\*\-\_]+|@)\s+(\d+)\s+\w+\s+(\w+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(.*)"
                else:
                    rep = "([\w\.\*\-\_]+|@)\s+(\d+)\s+\w+\s+(\w+)\s+([\w\.\"]+.*)"

                result = re.search(rep, i)
                if result:
                    if "MX" == tmp[3]:
                        result_list = {'host': result.group(1), 'ttl': result.group(2), 'type': result.group(3),
                                       'mx_priority': result.group(4), 'value': result.group(5)}
                    elif 'CAA' == tmp[3]:
                        result_list = {'host': result.group(1), 'ttl': result.group(2), 'type': result.group(3),
                                       'flags': result.group(4), 'tag': result.group(5),
                                       'ca_domain_name': result.group(6)}
                    elif 'AFSDB' == tmp[3]:
                        result_list = {'host': result.group(1), 'ttl': result.group(2), 'type': result.group(3),
                                       'subtype': result.group(4), 'hostname': result.group(5)}
                    elif 'DS' == tmp[3]:
                        result_list = {'host': result.group(1), 'ttl': result.group(2), 'type': result.group(3),
                                       'keytag': result.group(4), 'algorithm': result.group(5),
                                       'digesttype': result.group(6),
                                       'digest': result.group(7)}
                    elif 'HINFO' == tmp[3]:
                        result_list = {'host': result.group(1), 'ttl': result.group(2), 'type': result.group(3),
                                       'cpu': result.group(4), 'operatingsystem': result.group(5)}
                    elif 'LOC' == tmp[3]:
                        result_list = {'host': result.group(1), 'ttl': result.group(2), 'type': result.group(3),
                                       'latitude': result.group(4), 'longitude': result.group(5),
                                       'altitude': result.group(6),
                                       'size': result.group(7), 'horizontal': result.group(8),
                                       'vertical': result.group(9)}
                    elif 'NAPTR' == tmp[3]:
                        result_list = {'host': result.group(1), 'ttl': result.group(2), 'type': result.group(3),
                                       'order': result.group(4), 'preference': result.group(5),
                                       'flags': result.group(6),
                                       'service': result.group(7), 'regexp': result.group(8),
                                       'replacement': result.group(9)}
                    elif 'RP' == tmp[3]:
                        result_list = {'host': result.group(1), 'ttl': result.group(2), 'type': result.group(3),
                                       'mboxdname': result.group(4), 'txtdname': result.group(5)}
                    elif 'SRV' == tmp[3]:
                        result_list = {'host': result.group(1), 'ttl': result.group(2), 'type': result.group(3),
                                       'priority': result.group(4), 'weight': result.group(5), 'port': result.group(6),
                                       'target': result.group(7)}

                    else:
                        result_list = {'host':result.group(1),'ttl':result.group(2),'type':result.group(3),
                                       'value':result.group(4)}
                    conf_json[str(n)] = result_list
                    n += 1
            except:
                pass
        public.writeFile(self.path+"tmp",json.dumps(conf_json))
        return conf_json

    # 取域名解析
    def get_resolve(self,get):
        """
            @name 获取某个域名的解析
            @author zhwen<zhw@bt.cn>
            @parma values 验证过后的参数
        """
        values = self.__check_give_vaule(get)
        if "status" in values.keys():
            return values
        domain = values["domain"]
        zone_dir = "/var/named/chroot/var/named/"
        get_file = domain + ".zone"
        zone_file = zone_dir+get_file
        if os.path.exists(zone_file):
            zone_conf = public.readFile(zone_file)
            return self.__change_json(zone_conf)

    # 恢复默认配置解析
    def restore_def_resolve(self, get):
        """
            @name 恢复默认配置解析
            @author zhwen<zhw@bt.cn>
            @parma values 验证过后的参数
        """
        values = self.__check_give_vaule(get)
        domain = values["domain"]
        resolve_file = "{0}/var/named/{1}.zone".format(self.dns_conf_path, domain)
        self.__restore_file(resolve_file, act="def")
        public.WriteLog('DNS', 'Restore default parsing success')
        public.ExecShell("systemctl restart named-chroot")
        return public.ReturnMsg(True, "Successful recovery")

    # 获取日志
    def get_logs(self, get):
        """
            @name 获取操作日志
            @author zhwen<zhw@bt.cn>
        """
        import page
        page = page.Page()
        count = public.M('logs').where('type=?', (u'DNS',)).count()
        limit = 10
        info = {}
        info['count'] = count
        info['row'] = limit
        info['p'] = 1
        if hasattr(get, 'p'):
            info['p'] = int(get['p'])
        info['uri'] = get
        info['return_js'] = ''
        if hasattr(get, 'tojs'):
            info['return_js'] = get.tojs
        data = {}

        # 获取分页数据
        data['page'] = page.GetPage(info, '1,2,3,4,5,8')
        data['data'] = public.M('logs').where('type=?', (u'DNS',)).order('id desc').limit(
            str(page.SHIFT) + ',' + str(page.ROW)).field('log,addtime').select()
        return data

    def clearup_logs(self,get):
        """
            @name 清理操作日志
            @author zhwen<zhw@bt.cn>
        """
        public.M('logs').where('type=?', (u'DNS',)).delete()
        return public.ReturnMsg(True, "Clean up successfully")

    # 获取服务状态
    def get_service_status(self,get):
        """
            @name 获取服务状态
            @author zhwen<zhw@bt.cn>
        """
        sh = "ps aux|grep named|grep -v 'grep'"
        if self.dns_server_check() == 'pdns':
            sh = 'ps aux|grep pdns|grep -v "grep"'
        a,e = public.ExecShell(sh)
        if (a):
            return True
        else:
            return False

    # 停止服务
    def stop_service(self,get):
        services = 'named-chroot'
        if self.dns_server_check() == 'pdns':
            services = 'pdns'
        public.ExecShell("systemctl stop {}".format(services))
        time.sleep(1)
        if self.get_service_status(get):
            public.ExecShell("pkill -9 named")
        if self.get_service_status(get):
            return public.ReturnMsg(False, "Stop service failed")
        return public.ReturnMsg(True, "Stop service successfully")

    # 启动服务
    def start_service(self,get):
        if not self.get_service_status(get):
            services = 'named-chroot'
            if self.dns_server_check() == 'pdns':
                services = 'pdns'
            public.ExecShell("systemctl start {}".format(services))
            if not self.get_service_status(get):
                return public.ReturnMsg(False, "Stop service failed")
            return public.ReturnMsg(True, "Start service successfully")
        return public.ReturnMsg(False, "Service has started, no need to start")

    def __first_check(self):
        if public.readFile(self.path+"first.txt"):
            return True
        public.writeFile(self.path+"first.txt","1")

    #放行dns端口
    def __release_port(self,get):
        try:
            import firewalls
            port = ["53", "953"]
            for p in port:
                access_port = public.M('firewall').where("port=?", (p,)).count()
                if int(access_port) > 0:
                    continue
                get.port = p
                get.ps = 'DNS'
                firewalls.firewalls().AddAcceptPort(get)
            return port
        except:
            return False

    # 导出域名配置
    def export_data(self,get):
        """
        e_type        all/specific domain
        :param get:
        :return:
        """
        export_time = time.strftime("%Y%m%d%H%M", time.localtime())
        file_name = "{}export_{}.json".format(self.path,export_time)
        if get.e_type == "all":
            data = json.dumps(self._get_all_domain_data(get))
        else:
            data = json.dumps(self._get_specific_domain_data(get))
        public.writeFile(file_name, data)
        return public.returnMsg(True,file_name)

    # 获取所有域名数据
    def _get_all_domain_data(self,get):
        domain_list = self.get_domain_list(get)["msg"]
        data = {}
        for d in domain_list:
            get.domain = d
            soa_record = self.get_soa_record(get)
            data[d] = {'record':self.get_resolve(get),'soa_record':soa_record}
        return data

    # 获取某个域名数据
    def _get_specific_domain_data(self,get):
        domain = get.e_type
        get.domain = domain
        soa_record = self.get_soa_record(get)
        return {get.domain:{'record':self.get_resolve(get),'soa_record':soa_record}}

    # 导入数据
    def import_data(self,get):
        import files

        f = files.files()
        get.f_path = self.path
        result = f.upload(get)
        return result

    def import_data2(self,get):
        config = self.__read_config(self.config)
        domain_list = self.get_domain_list(get)["msg"]
        data = public.readFile(self.path + get.f_name)
        if not data:
            return public.returnMsg(False, "Import file is empty or import failed")
        data = json.loads(data)
        logfile = "{}import.log".format(self.path)
        public.writeFile(logfile,"")
        for i in data:
            if i in domain_list:
                public.writeFile(logfile,"Domain name already exists, skip {} import\n".format(i),"a+")
                continue
            # 导入记录
            self._make_resolve_content(i,data[i]['record'])
            # 导入soa记录
            self.set_soa_record('',i,data[i]['soa_record'])
            config["domain"].append(i)
            public.writeFile(logfile, "Successfully imported {}\n".format(i), "a+")
        self.__write_config(self.config,config)
        self._dnssever_restart()
        return public.returnMsg(True,"Successfully imported")

    # 构造解析内容
    def _make_resolve_content(self,domain,data):
        resolve_file = "{0}/var/named/{1}.zone".format(self.dns_conf_path, domain)
        # resolve_file = "/tmp/{}.zone".format(i)
        resolve_conf = """$TTL 1D
{0}.      IN SOA  f1g1ns1.dnspod.net.     admin.{0}. (
                                        0       ; serial
                                        1D      ; refresh
                                        1H      ; retry
                                        1W      ; expire
                                        3H )    ; minimum
""".format(domain)
        for d in data.values():
            # add_resolve = "{host}\t{ttl}\tIN\t{type}\t{value}\n".format(host=d['host'], type=d['ttl'], ttl=d['type'],value=d['value'])
            # if "MX" in d:
            #     add_resolve = "{host}\t{ttl}\tIN\t{type}\t{mx_priority}\t{value}\n".format(host=d['host'], type=d['type'],mx_priority=d['mx_priority'],ttl=d['ttl'], value=d['value'])
            if d["type"] == "MX":
                add_resolve = "{host}\t{ttl}\tIN\t{type}\t{mx_priority}\t{value}\n".format(host=d["host"],
                                                                                             type=d["type"],
                                                                                             mx_priority=d[
                                                                                                 "mx_priority"],
                                                                                             ttl=d["ttl"],
                                                                                             value=d["value"])
            elif d["type"] == "CAA":
                add_resolve = "{host}\t{ttl}\tIN\t{type}\t{flags} {tag} {ca_domain_name}\n".format(
                    host=d["host"],
                    type=d["type"],
                    ttl=d["ttl"],
                    flags=d["flags"],
                    tag=d['tag'],
                    ca_domain_name=d['ca_domain_name'])
            elif d["type"] == "AFSDB":
                add_resolve = "{host}\t{ttl}\tIN\t{type}\t{subtype}\t{hostname}\n".format(host=d["host"],
                                                                                            type=d["type"],
                                                                                            subtype=d["subtype"],
                                                                                            ttl=d["ttl"],
                                                                                            hostname=d["hostname"])

            elif d['type'] == "DS":
                add_resolve = "{host}\t{ttl}\tIN\t{type}\t{keytag}\t{algorithm}\t{digesttype}\t{digest}\n".format(
                    host=d["host"],
                    type=d["type"],
                    keytag=d["keytag"],
                    ttl=d["ttl"],
                    algorithm=d["algorithm"],
                    digesttype=d['digesttype'],
                    digest=d['digest'])
            elif d["type"] == "HINFO":
                add_resolve = "{host}\t{ttl}\tIN\t{type}\t{cpu}\t{operatingsystem}\n".format(host=d["host"],
                                                                                               type=d["type"],
                                                                                               cpu=d["cpu"],
                                                                                               ttl=d["ttl"],
                                                                                               operatingsystem=d[
                                                                                                   "operatingsystem"])
            elif d["type"] == "LOC":
                add_resolve = "{host}\t{ttl}\tIN\t{type}\t{latitude}\t{longitude}\t{altitude}\t{size}\t{horizontal}\t{vertical}\n".format(
                    host=d["host"],
                    type=d["type"],
                    latitude=d["latitude"],
                    ttl=d["ttl"],
                    longitude=d["longitude"],
                    altitude=d["altitude"],
                    size=d["size"],
                    horizontal=d['horizontal'],
                    vertical=d['vertical'])
            elif d["type"] == "NAPTR":
                add_resolve = '{host}\t{ttl}\tIN\t{type}\t{order}\t{preference}\t{flags}\t{service}\t{regexp}\t{replacement}\n'.format(
                    host=d["host"],
                    type=d["type"],
                    order=d["order"],
                    ttl=d["ttl"],
                    preference=d["preference"],
                    flags=d["flags"],
                    service=d["service"],
                    regexp=d['regexp'],
                    replacement=d['replacement'])
            elif d["type"] == "RP":
                add_resolve = "{host}\t{ttl}\tIN\t{type}\t{mboxdname}\t{txtdname}\n".format(host=d["host"],
                                                                                              type=d["type"],
                                                                                              mboxdname=d[
                                                                                                  "mboxdname"],
                                                                                              ttl=d["ttl"],
                                                                                              txtdname=d[
                                                                                                  "txtdname"])
            elif d["type"] == "SRV":
                add_resolve = "{host}\t{ttl}\tIN\t{type}\t{priority}\t{weight}\t{port}\t{target}\n".format(
                    host=d["host"],
                    type=d["type"],
                    priority=d["priority"],
                    ttl=d["ttl"],
                    weight=d["weight"],
                    port=d["port"],
                    target=d["target"])
            else:
                add_resolve = "{host}\t{ttl}\tIN\t{type}\t{value}\n".format(host=d["host"],
                                                                              type=d["type"],
                                                                              ttl=d["ttl"],
                                                                              value=d["value"])
            resolve_conf += add_resolve

        named_strs = """

zone "%s" IN {
        type master;
        file "%s.zone";
        allow-update { none; };
};""" % (domain, domain)
        public.writeFile(resolve_file,resolve_conf)
        public.writeFile(self.zone_file,named_strs,"a+")


    def dns_server_check(self,get=None):
        conf = public.readFile(self.zone_file)
        if not conf:
            public.writeFile(self.zone_file,'')
        server = 'bind'
        if os.path.exists('/usr/sbin/pdns_server'):
            server = 'pdns'
        return server

    def _pdns_compatible(self):
        reg = 'file\s+"/var.*'
        conf = public.readFile(self.zone_file)
        if re.search(reg,conf):
            return
        conf = conf.replace('file "','file "/var/named/chroot/var/named/')
        public.writeFile(self.zone_file,conf)
        public.ExecShell('systemctl restart pdns')

    def _dnssever_restart(self):
        services = 'named-chroot'
        if self.dns_server_check() == 'pdns':
            services = 'pdns'
        public.ExecShell("systemctl restart {}".format(services))

    def get_soa_record(self,get):
        """
            @name 获取某个域名的SOA记录
            @author zhwen<zhw@bt.cn>
            @parma values 验证过后的参数
            @parma get.domain 需要获取的SOA域名
        """
        values = self.__check_give_vaule(get)
        if "status" in values.keys():
            return values
        domain = values["domain"]
        zone_dir = "/var/named/chroot/var/named/"
        get_file = domain + ".zone"
        zone_file = zone_dir+get_file
        zone_conf = public.readFile(zone_file)
        return self._soa_process(zone_conf)

    def _soa_process(self,conf):
        data = []
        soa_reg = '[\w\.]+\s+IN\s+SOA\s+([\w\.]+)\s+([\w\.]+)'
        soa_tmp = re.search(soa_reg,conf)
        if not soa_tmp:
            return False
        result = soa_tmp.groups()
        data.append({'name':'ns_server','tips':'name server','content':result[0]})
        data.append({'name':'admin_mail','tips':'model admin email','content':result[1]})
        serial = {'name':'serial','reg':'\s+(\d+)\s*;\s*serial','tips':'zone file version'}
        refresh = {'name':'refresh','reg':'\s+(\w+)\s*;\s*refresh','tips':'How often to check the serial number on the master server'}
        retry = {'name':'retry','reg':'\s+(\w+)\s*;\s*retry','tips':'The interval time when the slave server reconnects to the master server'}
        expire = {'name':'expire','reg':'\s+(\w+)\s*;\s*expire','tips':'When the time exceeds the number of seconds set by Expire and the slave server cannot get in touch with the master, the slave will delete its copy.'}
        minimum = {'name':'minimum','reg':'\s+(\w+)\s*\)\s*;\s*minimum','tips':'Represents the default TTL value of all records in this zone file'}
        for i in [serial,refresh,retry,expire,minimum]:
            tmp = re.search(i['reg'],conf)
            if not tmp:
                return False
            i['content'] = tmp.group(1)
            data.append(i)
        return data

    def set_soa_record(self,get,domain=None,data=None):
        """
            @name 设置某个域名的SOA记录
            @author zhwen<zhw@bt.cn>
            @parma values 验证过后的参数
            @parma get.domain 需要设置的SOA域名
            @parma get.ns_server dnsserver
            @parma get.admin_mail dns管理员邮箱
            @parma get.serial
            @parma get.refresh
            @parma get.retry
            @parma get.expire
            @parma get.minimum
        """
        if get and not data:
            values = self.__check_give_vaule(get)
        else:
            values = {}
            values['domain'] = domain
            for i in data:
                values[i['name']] = i['content']
        zone_dir = "/var/named/chroot/var/named/"
        get_file = values['domain'] + ".zone"
        zone_file = zone_dir+get_file
        zone_conf = public.readFile(zone_file)
        new_conf = '''{d}.      IN SOA  {ns}     {email} (
                                        {serial}       ; serial
                                        {refresh}      ; refresh
                                        {retry}      ; retry
                                        {expire}      ; expire
                                        {minimum} )    ; minimum'''.format(
        d=values['domain'],ns=values['ns_server'],email=values['admin_mail'],serial=values['serial'],
        refresh=values['refresh'],retry=values['retry'],expire=values['expire'],minimum=values['minimum'])
        soa_reg = '{}\.(\n|.)+;\s*minimum'.format(values['domain'])
        zone_conf = re.sub(soa_reg,new_conf,zone_conf)
        public.writeFile(zone_file,zone_conf)
        self._dnssever_restart()
        return public.returnMsg(True,'Setup Successfully')


    # 检查输入参数
    def __check_give_vaule(self, get):
        values = {}
        rep_ip = "^(25[0-5]|2[0-4]\d|[0-1]?\d?\d)(\.(25[0-5]|2[0-4]\d|[0-1]?\d?\d)){3}$"
        rep_ipv6 = "^\s*((([0-9A-Fa-f]{1,4}:){7}(([0-9A-Fa-f]{1,4})|:))|(([0-9A-Fa-f]{1,4}:){6}(:|((25[0-5]|2[0-4]\d|[01]?\d{1,2})(\.(25[0-5]|2[0-4]\d|[01]?\d{1,2})){3})|(:[0-9A-Fa-f]{1,4})))|(([0-9A-Fa-f]{1,4}:){5}((:((25[0-5]|2[0-4]\d|[01]?\d{1,2})(\.(25[0-5]|2[0-4]\d|[01]?\d{1,2})){3})?)|((:[0-9A-Fa-f]{1,4}){1,2})))|(([0-9A-Fa-f]{1,4}:){4}(:[0-9A-Fa-f]{1,4}){0,1}((:((25[0-5]|2[0-4]\d|[01]?\d{1,2})(\.(25[0-5]|2[0-4]\d|[01]?\d{1,2})){3})?)|((:[0-9A-Fa-f]{1,4}){1,2})))|(([0-9A-Fa-f]{1,4}:){3}(:[0-9A-Fa-f]{1,4}){0,2}((:((25[0-5]|2[0-4]\d|[01]?\d{1,2})(\.(25[0-5]|2[0-4]\d|[01]?\d{1,2})){3})?)|((:[0-9A-Fa-f]{1,4}){1,2})))|(([0-9A-Fa-f]{1,4}:){2}(:[0-9A-Fa-f]{1,4}){0,3}((:((25[0-5]|2[0-4]\d|[01]?\d{1,2})(\.(25[0-5]|2[0-4]\d|[01]?\d{1,2})){3})?)|((:[0-9A-Fa-f]{1,4}){1,2})))|(([0-9A-Fa-f]{1,4}:)(:[0-9A-Fa-f]{1,4}){0,4}((:((25[0-5]|2[0-4]\d|[01]?\d{1,2})(\.(25[0-5]|2[0-4]\d|[01]?\d{1,2})){3})?)|((:[0-9A-Fa-f]{1,4}){1,2})))|(:(:[0-9A-Fa-f]{1,4}){0,5}((:((25[0-5]|2[0-4]\d|[01]?\d{1,2})(\.(25[0-5]|2[0-4]\d|[01]?\d{1,2})){3})?)|((:[0-9A-Fa-f]{1,4}){1,2})))|(((25[0-5]|2[0-4]\d|[01]?\d{1,2})(\.(25[0-5]|2[0-4]\d|[01]?\d{1,2})){3})))(%.+)?\s*$"
        rep_host = "^[a-zA-Z0-9\_]+\-{0,1}\_{0,1}[a-zA-Z0-9\_]*$"
        rep_domain_point = "^(?=^.{3,255}$)[a-zA-Z0-9][-a-zA-Z0-9]{0,62}(\.[a-zA-Z0-9][-a-zA-Z0-9]{0,62})+\.$"
        rep_domain = "^(?=^.{3,255}$)[a-zA-Z0-9\_\-][a-zA-Z0-9\_\-]{0,62}(\.[a-zA-Z0-9\_\-][a-zA-Z0-9\_\-]{0,62})+$"
        hexadecimal ='[\da-fA-F]+'
        soa_reg = '\d+'

        if hasattr(get,"ns_server"):
            if re.search(rep_domain,get.ns_server):
                values["ns_server"] = '{}.'.format(get.ns_server)
            elif re.search(rep_domain_point,get.ns_server):
                values["ns_server"] = get.ns_server
            else:
                return public.ReturnMsg(False, "Please check if the [txtdname] format is correct")

        if hasattr(get,"ns1"):
            if re.search(rep_domain,get.ns1):
                values["ns1"] = '{}.'.format(get.ns1)
            elif re.search(rep_domain_point,get.ns1):
                values["ns1"] = get.ns1
            else:
                return public.ReturnMsg(False, "Please check if the [ns1] format is correct")

        if hasattr(get,"ns2"):
            if re.search(rep_domain,get.ns2):
                values["ns2"] = '{}.'.format(get.ns2)
            elif re.search(rep_domain_point,get.ns2):
                values["ns2"] = get.ns2
            else:
                return public.ReturnMsg(False, "Please check if the [ns2] format is correct")

        if hasattr(get,"txtdname"):
            if re.search(rep_domain,get.txtdname):
                values["txtdname"] = '{}.'.format(get.txtdname)
            elif re.search(rep_domain_point,get.txtdname):
                values["txtdname"] = get.txtdname
            else:
                return public.ReturnMsg(False, "Please check if the [txtdname] format is correct")

        if hasattr(get,"mboxdname"):

            if re.search(rep_domain,get.mboxdname):
                values["mboxdname"] = '{}.'.format(get.mboxdname)
            elif re.search(rep_domain_point,get.mboxdname):
                values["mboxdname"] = get.mboxdname
            else:
                return public.ReturnMsg(False, "Please check if the [mboxdname] format is correct")

        if hasattr(get,"replacement"):
            if not get.replacement:
                values["replacement"] = None
            else:
                if re.search(rep_domain, get.replacement):
                    values["replacement"] = '{}.'.format(get.replacement)
                elif re.search(rep_domain_point, get.replacement):
                    values["replacement"] = get.replacement
                else:
                    return public.ReturnMsg(False, "Please check if the [replacement] format is correct")

        if hasattr(get,'regexp'):
            if re.search('!.*!.*!', get.regexp):
                values["regexp"] = '"{}"'.format(get.regexp)
            else:
                return public.ReturnMsg(False, "Please check if the [regexp] format is correct")

        if hasattr(get,'order'):
            if re.search(soa_reg, get.order):
                if int(get.order) < 0 or int(get.order) > 65535:
                    return public.ReturnMsg(False, "Please check if the [order] format is correct. e.g: 0-65535")
                values["order"] = str(get.order)
            else:
                return public.ReturnMsg(False, "Please check if the [order] format is correct")

        if hasattr(get,'preference'):
            if re.search(soa_reg, get.preference):
                if int(get.preference) < 0 or int(get.preference) > 65535:
                    return public.ReturnMsg(False, "Please check if the [preference] format is correct. e.g: 0-65535")
                values["preference"] = str(get.preference)
            else:
                return public.ReturnMsg(False, "Please check if the [preference] format is correct")

        if hasattr(get,'flags'):
            if re.search('[a-zA-Z0-9]+', get.flags):
                values["flags"] = '"{}"'.format(get.flags)
            else:
                return public.ReturnMsg(False, "Please check if the [flags] format is correct")

        if hasattr(get,'service'):
            if re.search('^[a-zA-Z][a-zA-Z0-9]{1,32}', get.service):
                values["service"] = '"{}"'.format(get.service)
            else:
                return public.ReturnMsg(False, "Please check if the [service] format is correct")

        if hasattr(get,'latitude'):
            latitude = get.latitude.split()
            e_msg = "Please check if the [latitude] format is correct,e.g:0-90 0-59 0-59.0-999 N/S [90 59 59.999 N]"
            if len(latitude) != 4:
                return public.ReturnMsg(False,e_msg)
            if re.search(soa_reg,latitude[0]):
                if int(latitude[0]) < 0 or int(latitude[0]) > 90 or len(latitude[0]) > 2:
                    return public.ReturnMsg(False, e_msg)
            if re.search(soa_reg,latitude[1]):
                if int(latitude[1]) < 0 or int(latitude[1]) > 59 or len(latitude[1]) > 2:
                    return public.ReturnMsg(False, e_msg)
            if re.search('\d+\.?',latitude[2]):
                tmp = latitude[2].split('.')
                if int(tmp[0]) < 0 or int(tmp[0]) > 59 or len(tmp[0]) > 2:
                    return public.ReturnMsg(False, e_msg)
                if len(tmp) == 2:
                    if int(tmp[1]) < 0 or int(tmp[1]) > 999 or len(tmp[1]) > 3:
                        return public.ReturnMsg(False, e_msg)
                    if len(tmp[1]) == 1:
                        get.latitude = '{} {} {}00 {}'.format(latitude[0],latitude[1],latitude[2],latitude[3])
                    elif len(tmp[1]) == 2:
                        get.latitude = '{} {} {}0 {}'.format(latitude[0],latitude[1],latitude[2],latitude[3])
                else:
                    get.latitude = '{} {} {}.000 {}'.format(latitude[0],latitude[1],latitude[2],latitude[3])
            if re.search('\d+\.?',latitude[3]):
                if latitude[3] not in ['N','S']:
                    return public.ReturnMsg(False, e_msg)
            values["latitude"] = str(get.latitude)

        if hasattr(get,'longitude'):
            longitude = get.longitude.split()
            e_msg = "Please check if the [longitude] format is correct,e.g:0-90 0-59 0-59.0-999 W/E [90 59 59.999 E]"
            if len(longitude) != 4:
                return public.ReturnMsg(False,e_msg)
            if re.search(soa_reg,longitude[0]):
                if int(longitude[0]) < 0 or int(longitude[0]) > 90 or len(longitude[0]) > 2:
                    return public.ReturnMsg(False, e_msg)
            if re.search(soa_reg,longitude[1]):
                if int(longitude[1]) < 0 or int(longitude[1]) > 59 or len(longitude[1]) > 2:
                    return public.ReturnMsg(False, e_msg)
            if re.search('\d+\.?',longitude[2]):
                tmp = longitude[2].split('.')
                if int(tmp[0]) < 0 or int(tmp[0]) > 59 or len(tmp[0]) > 2:
                    return public.ReturnMsg(False, e_msg)
                if len(tmp) == 2:
                    if int(tmp[1]) < 0 or int(tmp[1]) > 999 or len(tmp[1]) > 3:
                        return public.ReturnMsg(False, e_msg)
                    if len(tmp[1]) == 1:
                        get.longitude = '{} {} {}00 {}'.format(longitude[0],longitude[1],longitude[2],longitude[3])
                    elif len(tmp[1]) == 2:
                        get.longitude = '{} {} {}0 {}'.format(longitude[0],longitude[1],longitude[2],longitude[3])
                else:
                    get.longitude = '{} {} {}.000 {}'.format(longitude[0],longitude[1],longitude[2],longitude[3])
            if re.search('\d+\.?',longitude[3]):
                if longitude[3] not in ['W','E']:
                    return public.ReturnMsg(False, e_msg)
            values["longitude"] = str(get.longitude)

        if hasattr(get,'altitude'):
            e_msg = "Please check if the [altitude] format is correct e.g:-9999999-42849672.0-95 [42849672.95]"
            if not re.search('-?\d+\.?', get.altitude):
                return public.ReturnMsg(False, e_msg)
            altitude = get.altitude.split('.')
            if int(altitude[0]) < -9999999 or int(altitude[0]) > 42849672:
                return public.ReturnMsg(False, e_msg)
            if len(altitude) == 2:
                if altitude[1][-1] != 'm':
                    if int(altitude[1]) < 0 or int(altitude[1]) > 95 or len(altitude[1]) > 2:
                        return public.ReturnMsg(False, e_msg)
                    if len(altitude[1]) == 1:
                        get.altitude = get.altitude+'0'
                else:
                    if len(altitude[1][:-1]) > 2:
                        return public.ReturnMsg(False, e_msg)
                    get.altitude = get.altitude[:-1]
            else:
                if altitude[0][-1] != 'm':
                    get.altitude = get.altitude + '.00'
                else:
                    get.altitude = get.altitude[:-1]
            values["altitude"] = str(get.altitude+'m')

        if hasattr(get,'size'):
            e_msg = "Please check if the [size] format is correct,Less than 90000000 [89999999.99]"
            if not re.search('-?\d+\.?', get.size):
                return public.ReturnMsg(False, e_msg)
            size = get.size.split('.')
            if int(size[0]) < 0 or int(size[0]) > 90000000:
                return public.ReturnMsg(False, e_msg)
            if len(size) == 2 and int(size[0]) != 90000000:
                if size[1][-1] != 'm':
                    if int(size[1]) < 0 or int(size[1]) > 99 or len(size[1]) > 2:
                        return public.ReturnMsg(False, e_msg)
                    if len(size[1]) == 1:
                        get.size = get.size+'0'
                else:
                    if len(size[1][:-1]) > 2:
                        return public.ReturnMsg(False, e_msg)
                    get.size = get.size[:-1]
            else:
                if size[0][-1] != 'm':
                    get.size = get.size + '.00'
                else:
                    get.size = get.size[:-1]
            values["size"] = str(get.size+'m')

        if hasattr(get,'horizontal'):
            e_msg = "Please check if the [size] format is correct,Less than 90000000 [89999999.99]"
            if not re.search('-?\d+\.?', get.horizontal):
                return public.ReturnMsg(False, e_msg)
            horizontal = get.horizontal.split('.')
            if int(horizontal[0]) < 0 or int(horizontal[0]) > 90000000:
                return public.ReturnMsg(False, e_msg)
            if len(horizontal) == 2 and int(horizontal[0]) != 90000000:
                if horizontal[1][-1] != 'm':
                    if int(horizontal[1]) < 0 or int(horizontal[1]) > 99 or len(horizontal[1]) > 2:
                        return public.ReturnMsg(False, e_msg)
                    if len(horizontal[1]) == 1:
                        get.horizontal = get.horizontal+'0'
                else:
                    if len(horizontal[1][:-1]) > 2:
                        return public.ReturnMsg(False, e_msg)
                    get.horizontal = get.horizontal[:-1]
            else:
                if horizontal[0][-1] != 'm':
                    get.horizontal = get.horizontal + '.00'
                else:
                    get.horizontal = get.horizontal[:-1]
            values["horizontal"] = str(get.horizontal+'m')

        if hasattr(get,'vertical'):
            e_msg = "Please check if the [vertical] format is correct,Less than 90000000 [89999999.99]"
            if not re.search('-?\d+\.?', get.vertical):
                return public.ReturnMsg(False, e_msg)
            vertical = get.vertical.split('.')
            if int(vertical[0]) < 0 or int(vertical[0]) > 90000000:
                return public.ReturnMsg(False, e_msg)
            if len(vertical) == 2 and int(vertical[0]) != 90000000:
                if vertical[1][-1] != 'm':
                    if int(vertical[1]) < 0 or int(vertical[1]) > 99 or len(vertical[1]) > 2:
                        return public.ReturnMsg(False, e_msg)
                    if len(vertical[1]) == 1:
                        get.vertical = get.vertical+'0'
                else:
                    if len(vertical[1][:-1]) > 2:
                        return public.ReturnMsg(False, e_msg)
                    get.vertical = get.vertical[:-1]
            else:
                if vertical[0][-1] != 'm':
                    get.vertical = get.vertical + '.00'
                else:
                    get.vertical = get.vertical[:-1]
            values["vertical"] = str(get.vertical+'m')

        if hasattr(get,'cpu'):
            if re.search('^[A-Z]+[-/A-Z\d]+[\dA-Z]$', get.cpu):
                values["cpu"] = '"{}"'.format(get.cpu)
            else:
                return public.ReturnMsg(False, "The CPU name must start and end with an uppercase letter or number and not exceed 40 characters. It can only contain uppercase letters, numbers, ‘ / ‘ and ‘ - ‘.")
        if hasattr(get, 'operatingsystem'):
            if re.search('^[A-Z]+[\/\.\-A-Z\d]+[\dA-Z]$', get.operatingsystem):
                values["operatingsystem"] = '"{}"'.format(get.operatingsystem)
            else:
                return public.ReturnMsg(False, "The OS name must start and end with an uppercase letter or number and not exceed 40 characters. It can only contain uppercase letters, numbers, ‘ / ‘, ‘ . ‘, and ‘ - ‘.")
        if hasattr(get,'keytag'):
            if re.search(soa_reg, get.keytag):
                if int(get.keytag) < 0 or int(get.keytag) > 65535:
                    return public.ReturnMsg(False, "Please check if the [keytag] format is correct. e.g: 0-65535")
                values["keytag"] = str(get.keytag)
            else:
                return public.ReturnMsg(False, "Please check if the [keytag] format is correct")
        if hasattr(get,'subtype'):
            if re.search(soa_reg, get.subtype):
                if int(get.subtype) < 0 or int(get.subtype) > 65535:
                    return public.ReturnMsg(False, "Please check if the [subtype] format is correct. e.g: 0-65535")
                values["subtype"] = str(get.subtype)
            else:
                return public.ReturnMsg(False, "Please check if the [subtype] format is correct")
        if hasattr(get,'algorithm'):
            if re.search(soa_reg, get.algorithm):
                values["algorithm"] = str(get.algorithm)
            else:
                return public.ReturnMsg(False, "Please check if the [algorithm] format is correct")
        if hasattr(get,'digesttype'):
            if re.search(soa_reg, get.digesttype):
                values["digesttype"] = str(get.digesttype)
            else:
                return public.ReturnMsg(False, "Please check if the [digesttype] format is correct")
        if hasattr(get,'digest'):
            if re.search(hexadecimal, get.digest):
                values["digest"] = str(get.digest)
            else:
                return public.ReturnMsg(False, "Please check if the [digest] format is correct")
        if hasattr(get,'hostname'):
            # if re.search(rep_domain, get.hostname):
            #     values["hostname"] = get.hostname
            #     if get.hostname[-1] != '.':
            #         values["hostname"] = "{}.".format(get.hostname)
            if re.search(rep_domain,get.hostname):
                values["hostname"] = '{}.'.format(get.hostname)
            elif re.search(rep_domain_point,get.hostname):
                values["hostname"] = get.hostname
            else:
                return public.ReturnMsg(False, "Please check if the [hostname] format is correct")
        if hasattr(get,'priority'):
            if re.search(soa_reg, get.priority):
                values["priority"] = str(get.priority)
            else:
                return public.ReturnMsg(False, "Please check if the [Priority] format is correct")
        if hasattr(get,'port'):
            if re.search(soa_reg, get.port):
                if int(get.port) < 0 or int(get.port) > 65535:
                    return public.ReturnMsg(False, "Please check if the [weight] format is correct. e.g: 0-65535")
                values["port"] = str(get.port)
            else:
                return public.ReturnMsg(False, "Please check if the [weight] format is correct. e.g: 0-65535")
        if hasattr(get,'weight'):
            if re.search(soa_reg, get.weight):
                values["weight"] = str(get.weight)
            else:
                return public.ReturnMsg(False, "Please check if the [weight] format is correct")
        if hasattr(get,'target'):
            if re.search(rep_domain_point, get.target):
                values["target"] = str(get.target)
            elif re.search(rep_domain, get.target):
                values["target"] = str(get.target) + "."
            else:
                return public.ReturnMsg(False, "Please check if the [target] format is correct")
        if hasattr(get,'admin_mail'):
            # if re.search(rep_domain_point, get.admin_mail):
            #     values["admin_mail"] = str(get.admin_mail)
            if re.search(rep_domain_point, get.admin_mail):
                values["admin_mail"] = str(get.admin_mail)
            elif re.search(rep_domain, get.admin_mail):
                values["admin_mail"] = str(get.admin_mail) + "."
            else:
                return public.ReturnMsg(False, "Please check if the model admin email format is correct")
        if hasattr(get,'serial'):
            if re.search(soa_reg, get.serial):
                serial = get.serial
                if serial[-1] == '9' and serial[-2] != '9':
                    serial = '{date}{n1}{n2}'.format(date=serial[:-2],n1=int(serial[-2])+1,n2=0)
                elif serial[-1] != '9':
                    serial = '{date}{n1}{n2}'.format(date=serial[:-2],n1=serial[-2],n2=int(serial[-1])+1)
                values["serial"] = serial
            else:
                return public.ReturnMsg(False, "Please check if the serial format is correct")
        if hasattr(get,'refresh'):
            if re.search(soa_reg, get.refresh):
                values["refresh"] = str(get.refresh)
            else:
                return public.ReturnMsg(False, "Please check if the refresh format is correct")
        if hasattr(get,'retry'):
            if re.search(soa_reg, get.retry):
                values["retry"] = str(get.retry)
            else:
                return public.ReturnMsg(False, "Please check if the retry format is correct")
        if hasattr(get,'expire'):
            if re.search(soa_reg, get.expire):
                values["expire"] = str(get.expire)
            else:
                return public.ReturnMsg(False, "Please check if the expire format is correct")
        if hasattr(get,'minimum'):
            if re.search(soa_reg, get.minimum):
                values["minimum"] = str(get.minimum)
            else:
                return public.ReturnMsg(False, "Please check if the minimum format is correct")
        if hasattr(get,"ns1domain"):
            if not get.ns1domain:
                values["ns1domain"] = None
            else:
                if re.search(rep_domain,get.ns1domain):
                    values["ns1domain"] = str(get.ns1domain)
                else:
                    return public.ReturnMsg(False, "Please check if the NS1 domain name format is correct")
        if hasattr(get,"ns2domain"):
            if not get.ns2domain:
                values["ns2domain"] = None
            else:
                if re.search(rep_domain,get.ns2domain):
                    values["ns2domain"] = str(get.ns2domain)
                else:
                    return public.ReturnMsg(False, "Please check if the NS2 domain name format is correct")

        if hasattr(get,"soa"):
            if not get.soa:
                values["soa"] = None
            else:
                if re.search(rep_domain,get.soa):
                    values["soa"] = str(get.soa)
                else:
                    return public.ReturnMsg(False, "Please check if the soa format is correct")

        if hasattr(get, "id"):
            values["id"] = int(get.id)
        if hasattr(get, "domain"):
            if re.search(rep_domain, get.domain):
                values["domain"] = str(get.domain)
            else:
                return public.ReturnMsg(False, "Please check if the domain name format is correct")
        if hasattr(get, "host"):
            if re.search(rep_domain, get.host):
                values["host"] = str(get.host)
            elif re.search(rep_host, get.host):
                values["host"] = str(get.host)
            elif re.search(rep_domain_point, get.host):
                values["host"] = str(get.host)
            elif get.host == "@":
                values["host"] = str(get.host)
            elif get.host == "*":
                values["host"] = str(get.host)
            else:
                return public.ReturnMsg(False, "Please check if the host name format is correct.")
        if hasattr(get, "type"):
            rep = "(NS|A|CNAME|MX|TXT|AAAA|SRV|CAA|AFSDB|DS|HINFO|LOC|NAPTR|RP|SRV|PTR)"
            if re.search(rep, get.type):
                values["type"] = str(get.type)
            else:
                return public.ReturnMsg(False, "Please check if the parsing type format is correct.")
        if hasattr(get, "ttl"):
            try:
                values["ttl"] = int(get.ttl)
            except:
                return public.ReturnMsg(False, "Please check if the TTL value format is correct.")
        if hasattr(get, "mx_priority"):
            try:
                values["mx_priority"] = int(get.mx_priority)
            except:
                return public.ReturnMsg(False, "Please check if the MX priority format is correct.")
        if hasattr(get, "act"):
            l = ["delete", "add", "modify"]
            if get.act in l:
                values["act"] = get.act
            else:
                return public.ReturnMsg(False, "Please check if the operation type format is correct.")
        if hasattr(get,"listen_ip"):
            if re.search(rep_ip,get.listen_ip) or re.search(rep_ipv6,get.listen_ip) or get.listen_ip == "any":
                values["listen_ip"] = get.listen_ip
            else:
                return public.ReturnMsg(False, "Please check if the IP address format is correct.")
        if hasattr(get,"domain_ip"):
            if re.search(rep_ip,get.domain_ip) or re.search(rep_ipv6,get.domain_ip):
                values["domain_ip"] = get.domain_ip
            else:
                values["domain_ip"] = False
        else:
            values["domain_ip"] = False
        if hasattr(get,"tag"):
            if get.tag != 'issue':
                return public.ReturnMsg(False, "Please check if the [tag] format is correct")
            values["tag"] = get.tag
        if hasattr(get,"flags"):
            if str(get.flags) != '0':
                return public.ReturnMsg(False, "Please check if the [flags] format is correct")
            values["flags"] = get.flags
        if hasattr(get,'ca_domain_name'):
            if re.search(rep_domain_point, get.ca_domain_name):
                values["ca_domain_name"] = str(get.ca_domain_name)
            elif re.search(rep_domain, get.ca_domain_name):
                values["ca_domain_name"] = str(get.ca_domain_name) + "."
            else:
                return public.ReturnMsg(False, "Please check if the [ca_domain_name] format is correct")
        if hasattr(get, "value"):
            try:
                if values["type"] == "A":
                    if re.search(rep_ip, get.value):
                        values["value"] = str(get.value)
                if values["type"] == "NS":
                    if re.search(rep_ip, get.value):
                        values["value"] = str(get.value)+"."
                    if re.search(rep_domain, get.value):
                        values["value"] = str(get.value) + "."
                    if re.search(rep_domain_point, get.value):
                        values["value"] = str(get.value)
                    if re.search(rep_host, get.value):
                        values["value"] = str(get.value) + "."
                if values["type"] == "CNAME":
                    if re.search(rep_domain_point, get.value):
                        values["value"] = str(get.value)
                    if re.search(rep_domain, get.value):
                        values["value"] = str(get.value) + "."
                if values["type"] == "DNAME":
                    if re.search(rep_domain_point, get.value):
                        values["value"] = str(get.value)
                    if re.search(rep_domain, get.value):
                        values["value"] = str(get.value) + "."
                if values["type"] == "MX":
                    if re.search(rep_domain_point, get.value):
                        values["value"] = str(get.value)
                    if re.search(rep_domain, get.value):
                        values["value"] = str(get.value) + "."
                    if re.search(rep_ip, get.value):
                        values["value"] = str(get.value)+ "."
                if values["type"] == "TXT":
                    values["value"] = str(get.value) if '"' == get.value[0] else str('"'+get.value+'"')
                if values["type"] == "AAAA":
                    if re.search(rep_ipv6, get.value):
                        values["value"] = str(get.value)
                if values["type"] in ["SRV","AFSDB","DS","HINFO","LOC","NAPTR","RP"]:
                    values["value"] = str(get.value)
                if values["type"] == "PTR":
                    if re.search(rep_domain, get.value):
                        values["value"] = '{}.'.format(get.value)
                    elif re.search(rep_domain_point, get.value):
                        values["value"] = get.value
                if values["type"] == "CAA":
                    values["flags"] = str(get.flags)
                    values["tag"] = str(get.tag)
                    values["ca_domain_name"] = str(get.ca_domain_name) if '"' in get.ca_domain_name else str('"'+get.ca_domain_name+'"')
                    values["value"] = ''
                if "value" not in values: return public.ReturnMsg(False, "Please check if the record value format is correct")
            except:
                return public.ReturnMsg(False, "Please check if the record value format is correct")
        result = {}
        for i in values:
            try:
                result[i] = values[i].strip()
            except:
                result[i] = values[i]
        return result

# class get:
#     pass
# get.domain = "youbadbad.cn"
# # get.host = "www"
# # get.type = "A"
# # get.ttl = "600"
# get.listen_ip = "192.168.1.198"
#
# d = dns_manager_main()
# print(d.get_listen_ip())