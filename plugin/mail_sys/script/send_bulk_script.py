#coding: utf-8

#------------------------------
# 批量发送调用脚本
#------------------------------
import os
import sys

import traceback
import subprocess
from pathlib import Path

def check_and_start_scripts():
    try:
        script_dir = Path('/www/server/panel/plugin/mail_sys/script/send_bulk')
        data_dir = Path('/www/server/panel/plugin/mail_sys/data')
        # 没有目录 跳过
        if not os.path.exists(script_dir):
            return
        
        # 获取所有可执行脚本
        scripts = [f for f in os.listdir(script_dir) if f.startswith('s_') and f.endswith('.py')]
        
        # 获取暂停标记
        pause_files = [f for f in os.listdir(data_dir) if f.startswith('p_') and f.endswith('.pl')]
        paused_scripts = set()
        
        # 处理暂停标记
        for pause_file in pause_files:
            task_id = pause_file.split('_')[1].split('.')[0]
            script_name = f's_{task_id}.py'
            if script_name in scripts:
                print(f'{script_name} There is a pause marker')
                paused_scripts.add(script_name)
        
        # 过滤掉暂停的脚本
        active_scripts = [s for s in scripts if s not in paused_scripts]
        
        # 检查并启动脚本
        for script in active_scripts:
            script_path = f'/www/server/panel/plugin/mail_sys/script/send_bulk/{script}'
            
            # 修改ps命令使用完整路径
            ps_cmd = f"ps aux | grep '{script}' | grep -v grep"
            if subprocess.run(ps_cmd, shell=True, stdout=subprocess.PIPE).stdout:
                print(f'Script {script} is running, skip')
                continue
            
            # 启动脚本并获取输出
            cmd = f'btpython {script_path}'
            try:
                process = subprocess.Popen(cmd, shell=True,
                               stdout=subprocess.PIPE, 
                               stderr=subprocess.PIPE)
                # 等待一小段时间检查是否立即失败
                stdout, stderr = process.communicate(timeout=1)
                if stderr:
                    print(f'Script startup error: {script}\nerrinfo: {stderr.decode()}')
                else:
                    print(f'The script has been started: {script}')
            except subprocess.TimeoutExpired:
                # 脚本正常运行中
                print(f'The script is running: {script}')
            except Exception as e:
                print(f'An error occurred while starting the script: {script}\nerrinfo: {str(e)}')
            
    except Exception as ex:
        print("Bulk sending errors: " + str(ex))
        print(traceback.format_exc())

if __name__ == "__main__":
    os.chdir('/www/server/panel')
    sys.path.insert(0,'class/')
    check_and_start_scripts()