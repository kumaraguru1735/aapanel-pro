#!/usr/bin/python
# coding: utf-8
# -----------------------------
# 定时检测更新 域名邮箱配额使用量  current_usage
# -----------------------------

import os
import time
import sys
import subprocess
import json


sys.path.append('/www/server/panel/class')
import public

class MailUsageUpdater:
    def __init__(self):
        self.vmail_path = '/www/vmail'
        self.database_path = '/www/vmail/postfixadmin.db'
        self.batch_size = 50
        self.log_file = '/tmp/mail_usage_update.log'
        
    def log(self, msg):
        """记录日志"""
        public.WriteLog('mail_sys', msg)
        with open(self.log_file, 'a') as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
    
    def get_dir_size_fast(self, path):
        """du, get directory size"""
        try:
            cmd = f"du -sb {path} 2>/dev/null | cut -f1"
            result = subprocess.check_output(cmd, shell=True).decode().strip()
            return int(result)
        except:
            return 0
    
    def get_quota_from_maildirsize(self, path):
        """从maildirsize文件获取使用量"""
        try:
            maildirsize_path = os.path.join(path, 'maildirsize')
            if os.path.exists(maildirsize_path):
                with open(maildirsize_path, 'r') as f:
                    lines = f.readlines()
                    
                    # 配额定义，跳过
                    if len(lines) <= 1:
                        return None
                    
                    # 累加
                    total_size = 0
                    for i in range(1, len(lines)):
                        line = lines[i].strip()
                        if not line:
                            continue
                        
                        # 格式: "大小 消息数"
                        size_info = line.split()
                        if len(size_info) >= 1:
                            try:
                                # 大小可能是负数（删除的邮件）
                                size = int(size_info[0])
                                total_size += size
                            except ValueError:
                                continue
                    
                    return total_size
            return None
        except Exception as e:
            self.log(f"Error reading maildirsize file: {str(e)}")
            return None
    
    def get_quota_from_doveadm(self, username):
        """使用doveadm命令获取配额使用量"""
        try:
            cmd = f"doveadm quota get -u {username} 2>/dev/null"
            result = subprocess.check_output(cmd, shell=True).decode()
            for line in result.splitlines():
                if 'STORAGE' in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1]) * 1024  # 转换为字节
            return None
        except:
            return None
    
    def update_domain_usage(self):
        """更新所有域名的使用量"""

        with public.S('domain', self.database_path) as obj:
            domains = obj.field('domain').select()
        
        if not domains:
            return

        domain_updates = []
        for domain_info in domains:
            domain = domain_info['domain']
            domain_path = os.path.join(self.vmail_path, domain)
            
            if not os.path.exists(domain_path):
                continue
                
            usage = self.get_dir_size_fast(domain_path)
            domain_updates.append({
                'domain': domain,
                'current_usage': usage
            })
            
            # 达到批量大小时更新
            if len(domain_updates) >= self.batch_size:
                self._batch_update_domain(domain_updates)
                domain_updates = []
        
        # 更新剩余的域名
        if domain_updates:
            self._batch_update_domain(domain_updates)

    
    def _batch_update_domain(self, updates):
        """批量更新域名使用量"""
        with public.S('domain', self.database_path) as obj:
            for item in updates:
                obj.where('domain', item['domain']).update({
                    'current_usage': item['current_usage']
                })
    
    def update_mailbox_usage(self):
        """更新所有邮箱的使用量"""
        

        with public.S('mailbox', self.database_path) as obj:
            mailboxes = obj.field('username,local_part,domain,quota,quota_active').where('quota_active', 1).select()
        
        if not mailboxes:
            return
        

        mailbox_updates = []
        for mailbox in mailboxes:
            username = mailbox['username']
            local_part = mailbox['local_part']
            domain = mailbox['domain']
            quota = mailbox['quota']
            maildir_path = os.path.join(self.vmail_path, domain, local_part)
            
            if not os.path.exists(maildir_path):
                continue
            
            # 优先使用maildirsize文件获取使用量
            usage = self.get_quota_from_maildirsize(maildir_path)

            # 如果maildirsize不可用
            if usage is None:
                maildirsize_path = os.path.join(maildir_path, 'maildirsize')
                try:
                    # 尝试重算配额
                    stdout, stderr = public.ExecShell(f'doveadm quota recalc -u {username}')
                    
                    # 检查命令是否成功执行
                    if not stderr and os.path.exists(maildirsize_path):
                        # 重新尝试读取maildirsize
                        usage = self.get_quota_from_maildirsize(maildir_path)
                    
                    # 如果仍然失败，创建初始文件
                    if usage is None:
                        # 使用du命令获取实际大小作为初始值
                        actual_size = self.get_dir_size_fast(maildir_path)
                        maildirsize_content = f"{int(quota)}S\n{actual_size} 0\n"
                        public.writeFile(maildirsize_path, maildirsize_content)
                        public.set_own(maildirsize_path, 'vmail', 'mail')
                        usage = actual_size

                except Exception as e:
                        self.log(f"Error processing maildirsize file for user {username}: {str(e)}")
                        # Use du command when error occurs
                        usage = self.get_dir_size_fast(maildir_path)
            
            mailbox_updates.append({
                'username': username,
                'current_usage': usage if usage is not None else 0  # Ensure no None values
            })


            if len(mailbox_updates) >= self.batch_size:
                self._batch_update_mailbox(mailbox_updates)
                mailbox_updates = []
        
        # 更新剩余的邮箱
        if mailbox_updates:
            self._batch_update_mailbox(mailbox_updates)

    
    def _batch_update_mailbox(self, updates):
        """批量更新邮箱使用量"""
        with public.S('mailbox', self.database_path) as obj:
            for item in updates:
                obj.where('username', item['username']).update({
                    'current_usage': item['current_usage']
                })
    
    def run(self):

        try:

            try:
                self.update_domain_usage()
            except Exception as e:
                self.log(f"Error updating domain usage: {str(e)}")

            try:
                self.update_mailbox_usage()
            except Exception as e:
                self.log(f"Error updating mailbox usage: {str(e)}")

            return True
        except Exception as e:
            self.log(f"Error in main update task: {str(e)}")
            return False

if __name__ == "__main__":
    updater = MailUsageUpdater()
    updater.run()