#coding: utf-8

#------------------------------
# 发送结束后筛选日志
#------------------------------
import os
import sys
import fcntl
import subprocess
import traceback
from pathlib import Path
# 设置工作目录
os.chdir('/www/server/panel')
sys.path.insert(0, 'class/')
import public

class ProcessLock:
    def __init__(self, lock_file):
        self.lock_file = lock_file
        self.lock_fd = None

    def acquire(self):
        try:
            self.lock_fd = open(self.lock_file, 'w')
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_fd.write(str(os.getpid()))
            self.lock_fd.flush()
            return True
        except IOError:
            if self.lock_fd:
                self.lock_fd.close()
            return False

    def release(self):
        if self.lock_fd:
            fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
            self.lock_fd.close()
            try:
                os.remove(self.lock_file)
            except:
                pass

def check_and_start_analysis():
    try:
        script_dir = Path('/www/server/panel/plugin/mail_sys/script/tasklog_analysis')
        data_dir = Path('/www/server/panel/plugin/mail_sys/data')
        # 没有目录 跳过
        if not os.path.exists(script_dir):
            return
        

        # 获取活动脚本
        scripts = [f for f in os.listdir(script_dir) if f.startswith('t_') and f.endswith('.py')]
        pause_files = [f for f in os.listdir(data_dir) if f.startswith('p_') and f.endswith('.pl')]
        paused_scripts = {f't_{f.split("_")[1].split(".")[0]}.py' for f in pause_files}
        active_scripts = [s for s in scripts if s not in paused_scripts]
        
        for script in active_scripts:
            script_path = script_dir / script
            pid_file = Path(f'/tmp/{script}.pid')
            
            # 检查脚本是否在运行
            if pid_file.exists():
                try:
                    pid = int(pid_file.read_text().strip())
                    if os.path.exists(f'/proc/{pid}'):
                        continue
                except:
                    pid_file.unlink(missing_ok=True)
            
            # 启动分析脚本
            try:
                cmd = f'btpython {script_path}'
                process = subprocess.Popen(
                    cmd, 
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True
                )
                
                # 记录PID
                pid_file.write_text(str(process.pid))
                # public.print_log(f'Started: {script} (PID: {process.pid})')
                
            except Exception as e:
                public.print_log(f'Failed to start {script}: {str(e)}')
                
    except Exception as e:
        public.print_log(f"Error: {str(e)}")
        public.print_log(traceback.format_exc())

def main():

    # 检查是否已在运行
    lock = ProcessLock('/tmp/mail_error_logs.lock')
    if not lock.acquire():
        # public.print_log("Already running")
        sys.exit(0)

    try:
        check_and_start_analysis()
    finally:
        lock.release()

if __name__ == "__main__":
    main()