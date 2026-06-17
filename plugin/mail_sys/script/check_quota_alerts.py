#!/usr/bin/python
# coding: utf-8
# -----------------------------
# 检查邮件域名和邮箱配额使用情况并发送告警
# -----------------------------

import os
import time
import sys
import json
from datetime import datetime, timedelta

sys.path.append('/www/server/panel/class')
import public
import public.PluginLoader as plugin_loader

class MailQuotaAlerts:
    def __init__(self):
        self.vmail_path = '/www/vmail'
        self.database_path = '/www/vmail/postfixadmin.db'
        self.alert_history_file = '/www/server/panel/plugin/mail_sys/data/quota_alerts_history.json'
        self.alert_config_file = '/www/server/panel/plugin/mail_sys/data/quota_alert_conf.json'
        self.alert_thresholds = [90, 95]  # 90%和95%使用率时告警
        self.alert_interval = 24  # 重复告警的间隔小时数
        self.log_file = '/tmp/mail_check_quota_alerts.log'
        
        # 加载配置
        self.config = self.load_alert_config()

        data_dir = os.path.dirname(self.alert_history_file)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)


        if not os.path.exists(self.alert_history_file):
            self.save_alert_history({})

    def log(self, msg):
        """记录日志"""
        public.WriteLog('mail_sys', msg)
        with open(self.log_file, 'a') as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
    
    def load_alert_config(self):
        """加载告警配置"""
        try:
            if os.path.exists(self.alert_config_file):
                with open(self.alert_config_file, 'r') as f:
                    return json.load(f)
            return {"send_email_to_user": True}
        except Exception as e:
            self.log(f"Error loading alert config: {str(e)}")
            return {"send_email_to_user": True}

    def load_alert_history(self):
        """从文件加载告警历史"""
        try:
            if os.path.exists(self.alert_history_file):
                with open(self.alert_history_file, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            self.log(f"Error loading alert history: {str(e)}")
            return {}

    def save_alert_history(self, history):
        """保存告警历史到文件"""
        try:
            with open(self.alert_history_file, 'w') as f:
                json.dump(history, f)
        except Exception as e:
            self.log(f"Error saving alert history: {str(e)}")

    def should_send_alert(self, target_id, threshold):
        """根据历史记录检查是否应该发送告警"""
        history = self.load_alert_history()
        current_time = datetime.now()

        alert_key = f"{target_id}_{threshold}"

        if alert_key in history:
            last_alert_time = datetime.fromisoformat(history[alert_key])
            # 检查自上次告警以来是否已经过了足够的时间
            if current_time - last_alert_time < timedelta(hours=self.alert_interval):
                return False

        # 使用当前时间更新历史记录
        history[alert_key] = current_time.isoformat()
        self.save_alert_history(history)
        return True

    def get_quota_from_maildirsize(self, path):
        """从maildirsize文件获取使用量"""
        try:
            maildirsize_path = os.path.join(path, 'maildirsize')
            if os.path.exists(maildirsize_path):
                with open(maildirsize_path, 'r') as f:
                    lines = f.readlines()

                    # First line is quota definition, skip it
                    if len(lines) <= 1:
                        return None

                    # Add up all subsequent line sizes
                    total_size = 0
                    for i in range(1, len(lines)):
                        line = lines[i].strip()
                        if not line:
                            continue

                        # Each line format: "size message_count"
                        size_info = line.split()
                        if len(size_info) >= 1:
                            try:
                                # Size can be negative (deleted emails)
                                size = int(size_info[0])
                                total_size += size
                            except ValueError:
                                continue

                    return total_size
            return None
        except Exception as e:
            self.log(f"Error reading maildirsize file: {str(e)}")
            return None



    def format_size(self, size_bytes):
        """将字节格式化为人类可读的大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024*1024):.2f} MB"
        else:
            return f"{size_bytes/(1024*1024*1024):.2f} GB"

    def check_domain_quota_alerts(self):
        """检查域名配额并发送告警"""

        # 查看是否开启了告警
        bulk = plugin_loader.get_module('{}/plugin/mail_sys/mail_send_bulk.py'.format(public.get_panel_path()))
        SendMailBulk = bulk.SendMailBulk


        alarm = False
        args = public.dict_obj()
        args.keyword = 'mail_domain_quota_alert'
        try:
            send_task = SendMailBulk().get_alarm_send(args)
        except:
            public.print_log(public.get_error_info())
            print(public.get_error_info())
            send_task = False
        if send_task and send_task.get('status', False):
            alarm = True

        if not alarm:  # 未开启跳过
            return

        self.log("Starting domain quota check...")
        start_time = time.time()

        with public.S('domain', self.database_path) as obj:
            domains = obj.field('domain,quota,current_usage').select()

        if not domains:
            self.log("No domain records found")
            return

        # 收集超过阈值的域名
        alerts_by_threshold = {threshold: [] for threshold in self.alert_thresholds}

        for domain_info in domains:
            domain = domain_info['domain']
            quota = domain_info.get('quota', 0)
            usage = domain_info.get('current_usage', 0)

            if not quota or quota <= 0 or usage is None:
                continue

            # 计算使用百分比
            usage_percent = (usage / quota) * 100

            # 检查是否超过阈值
            for threshold in self.alert_thresholds:
                if usage_percent >= threshold:
                    alerts_by_threshold[threshold].append({
                            'domain': domain,
                            'usage': usage,
                            'quota': quota,
                            'percent': usage_percent
                        })
                    break  # 只在超过的最高阈值发送告警

        # 为每个阈值级别发送告警
        for threshold, domains_list in alerts_by_threshold.items():
            if domains_list:
                self.send_domain_quota_alert(threshold, domains_list)

        elapsed = time.time() - start_time
        self.log(f"Domain quota check completed, time elapsed: {elapsed:.2f} seconds")

    def send_domain_quota_alert(self, threshold, domains_list):
        """为超过配额阈值的域名发送告警"""
        if not domains_list:
            return

        # 准备告警消息
        alert_level = "WARNING" if threshold < 90 else "CRITICAL"
        # subject = f"{alert_level}: Mail Domain Quota Alert ({threshold}% threshold)"

        # 格式化消息正文

        body = []
        max_percent = max([domain_info['percent'] for domain_info in domains_list])
        if max_percent >= 95:
            severity = "95%"
        elif max_percent >= 90:
            severity = "90%"
        elif max_percent >= 80:
            severity = "80%"
        else:
            severity = f"{threshold}%"

        body.append(f">The following mail domains have exceeded {severity} of their quota:")




        for domain_info in domains_list:
            domain = domain_info['domain']
            usage = self.format_size(domain_info['usage'])
            quota = self.format_size(domain_info['quota'])
            percent = domain_info['percent']

            body.append(f"- Domain: {domain}")
            body.append(f"  Usage: {usage} / {quota} ({percent:.1f}%)")

        # 通过推送系统发送告警
        try:
            args = public.dict_obj()
            args.keyword = 'mail_domain_quota_alert'
            args.body = body

            push_data = {
                "alert_level": alert_level,
                "threshold": threshold,
                "domains": domains_list,
                "msg_list": body
            }
            self.send_alert_notification(args, push_data)
            self.log(f"Sent domain quota alert for {len(domains_list)} domains at {threshold}% threshold")
        except Exception as e:
            self.log(f"Error sending domain quota alert: {str(e)}")

    def check_mailbox_quota_alerts(self):
        """检查邮箱配额并发送告警"""
        # 检查是否开启了告警
        self.log("Starting mailbox quota check...")
        start_time = time.time()

        # 获取所有带有配额信息的邮箱
        with public.S('mailbox', self.database_path) as obj:
            mailboxes = obj.field('username,local_part,domain,quota,current_usage,quota_active').where('quota_active', 1).select()

        if not mailboxes:
            self.log("No mailbox records found")
            return

        # 处理每个邮箱
        for mailbox in mailboxes:
            try:
                username = mailbox['username']
                local_part = mailbox['local_part']
                domain = mailbox['domain']
                quota = mailbox.get('quota', 0)
                usage = mailbox.get('current_usage')

                # 如果没有设置配额或数据无效则跳过
                if not quota or quota <= 0:
                    continue

                # 如果数据库中没有使用量数据，尝试获取
                if usage is None:
                    maildir_path = os.path.join(self.vmail_path, domain, local_part)
                    if not os.path.exists(maildir_path):
                        continue

                    # 尝试从maildirsize文件获取使用量
                    usage = self.get_quota_from_maildirsize(maildir_path)

                    # 如果仍然不可用
                    if usage is None:
                        continue

                # 计算使用百分比
                if usage is not None and usage > 0:
                    usage_percent = (usage / quota) * 100

                    # 检查是否超过阈值
                    for threshold in self.alert_thresholds:
                        if usage_percent >= threshold:
                            # public.print_log(f' 当前邮箱比较超过-- {username}')
                            # 根据历史记录检查是否应该发送告警
                            if self.should_send_alert(f"mailbox_{username}", threshold):
                                self.send_mailbox_quota_alert(username, usage, quota, usage_percent, threshold)

                            break  # 只在超过的最高阈值发送告警

            except Exception as e:
                self.log(f"Error processing mailbox {mailbox.get('username', 'unknown')}: {str(e)}")

        elapsed = time.time() - start_time
        self.log(f"Mailbox quota check completed, time elapsed: {elapsed:.2f} seconds")

    def send_mailbox_quota_alert(self, username, usage, quota, percent, threshold):
        """向邮箱所有者发送配额告警邮件"""
        # 检查是否开启了发送邮件
        if not self.config.get('send_email_to_user', True):
            # self.log(f"Skipping email alert to {username} (disabled by config)")
            return

        try:
            # 格式化大小为人类可读格式
            usage_formatted = self.format_size(usage)
            quota_formatted = self.format_size(quota)

            # 确定告警级别
            alert_level = "Warning" if threshold < 90 else "Critical"

            # 准备邮件主题和正文
            subject = f"{alert_level}: Your mailbox is {percent:.1f}% full"

            body = f"""
Dear User,

Your mailbox ({username}) has reached {percent:.1f}% of its quota.

Current usage: {usage_formatted} of {quota_formatted}

To avoid potential email delivery issues, please consider:
1. Deleting unnecessary emails, especially those with large attachments
2. Archiving old emails to local storage
3. Emptying your trash and spam folders

If you need assistance or require a quota increase, please contact your mail administrator.

This is an automated message. Please do not reply.
"""
            if percent >= 100:
                return

            # 使用邮件系统发送邮件
            from_address = f"postmaster@{username.split('@')[1]}"  # 使用 postmaster@domain.com

            # 使用系统邮件发送功能
            self.send_mail_to_user(from_address, username, subject, body)

            self.log(f"Sent quota alert email to {username} ({percent:.1f}%)")

        except Exception as e:
            self.log(f"Error sending quota alert to {username}: {str(e)}")

    def send_mail_to_user(self, from_address, to_address, subject, body):
        """使用系统邮件功能向用户发送邮件"""
        try:
            # 创建邮件内容
            mail_content = f"From: {from_address}\r\n"
            mail_content += f"To: {to_address}\r\n"
            mail_content += f"Subject: {subject}\r\n"
            mail_content += "Content-Type: text/plain; charset=utf-8\r\n\r\n"
            mail_content += body

            # 写入临时文件
            temp_file = f"/tmp/quota_alert_{int(time.time())}.eml"
            public.writeFile(temp_file, mail_content)

            # 使用sendmail发送
            cmd = f"sendmail -t < {temp_file}"
            public.ExecShell(cmd)

            # 清理
            if os.path.exists(temp_file):
                os.remove(temp_file)

            return True
        except Exception as e:
            self.log(f"Error in send_mail_to_user: {str(e)}")
            return False

    def send_alert_notification(self, args, push_data):
        """通过推送系统发送告警通知"""
        try:
            import sys
            if "/www/server/panel" not in sys.path:
                sys.path.insert(0, "/www/server/panel")

            from mod.base.push_mod import push_by_task_keyword
            res = push_by_task_keyword(args.keyword, args.keyword, push_data=push_data)
            return res
        except Exception as e:
            public.print_log(public.get_error_info())
            self.log(f"Error in send_alert_notification: {str(e)}")
            return False

    def run(self):
        """运行配额告警检查"""
        try:
            self.log("Starting mail quota alert checks")
            
            # 域名告警暂时不启用
            # try:
            #     self.check_domain_quota_alerts()
            # except Exception as e:
            #     self.log(f"Error checking domain quotas: {str(e)}")

            try:
                self.check_mailbox_quota_alerts()
            except Exception as e:
                self.log(f"Error checking mailbox quotas: {str(e)}")

            self.log("Mail quota alert checks completed")
            return True
        except Exception as e:
            self.log(f"Error in main alert task: {str(e)}")
            return False

if __name__ == "__main__":
    alerts = MailQuotaAlerts()
    alerts.run()
