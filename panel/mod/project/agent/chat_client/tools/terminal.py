from . import register_tool
from .base import _xml_response
import threading
import subprocess
import time
import uuid
import os
import re
from typing import Dict, Tuple

# 危险命令黑名单模式
DANGEROUS_COMMAND_PATTERNS = [
    r'rm\s+-rf\s+/$',  # rm -rf /
    r'rm\s+-rf\s+/\*',  # rm -rf /*
    r'rm\s+-rf\s+~',  # rm -rf ~
    r'dd\s+if=',  # dd 磁盘操作
    r'mkfs',  # 格式化
    r'>\s*/dev/sd[a-z]',  # 直接写入磁盘
    r'>\s*/dev/nvme',  # 直接写入NVMe
    r'chmod\s+777\s+/',  # 修改根目录权限
    r'chown\s+.*\s+/',  # 修改根目录所有者
    r'shutdown',  # 关机
    r'reboot',  # 重启
    r'halt',  # 停机
    r'poweroff',  # 关电
    r'init\s+0',  # 关机
    r'init\s+6',  # 重启
    r':\(\)\s*\{',  # Fork bomb
    r'curl.*\|\s*bash',  # 远程执行
    r'wget.*\|\s*bash',  # 远程执行
    r'eval\s+',  # eval 执行
    r'exec\s+',  # exec 执行
]


def _split_merged_command(command: str) -> list:
    """仅按逻辑控制符（&&, ;, ||）拆分命令，保留管道符在子命令内部。"""
    parts = re.split(r'\s*(?:&&|\|\||;)\s*', command)
    return [p.strip() for p in parts if p.strip()]


def _split_merged_command_with_delims(command: str) -> list:
    """
    拆分合并命令，保留原连接符。
    返回 [(cmd, delim), ...] 列表。例如: "cmd1 && cmd2 ; cmd3" -> [('cmd1', '&&'), ('cmd2', ';'), ('cmd3', '')]
    """
    # 仅在 &&, ||, ; 处切分并捕获分隔符
    tokens = re.split(r'(\s*(?:&&|\|\||;)\s*)', command)
    tokens = [t for t in tokens if t]  # 过滤空字符

    if not tokens:
        return []
    if len(tokens) == 1:
        return [(tokens[0].strip(), "")]

    result = []
    i = 0
    while i < len(tokens):
        cmd = tokens[i].strip()
        delim = ""
        if i + 1 < len(tokens):
            delim = tokens[i + 1].strip()
        result.append((cmd, delim))
        i += 2
    return result


def _wrap_merged_command_with_markers(command: str) -> str:
    """
    包装合并命令，动态保留并应用原始连接符（&&, ||, ;），维持原 Shell 逻辑。
    """
    parts = _split_merged_command_with_delims(command)
    wrapped_parts = []

    for i, (cmd, delim) in enumerate(parts):
        escaped_cmd = cmd.replace("'", "'\\''")
        # 包装子命令
        wrapped = f'bash -c \'printf "===CMD_START_{i}===\\n"; {escaped_cmd}; printf "\\n===CMD_END_{i}===\\nRC=%s\\n" "$?"\''

        # 将原始连接符附带在包装好的命令之后
        if delim:
            wrapped_parts.append(f"{wrapped} {delim}")
        else:
            wrapped_parts.append(wrapped)

    return " ".join(wrapped_parts)


def _parse_merged_output(raw_output: str, command: str) -> str:
    parts = _split_merged_command_with_delims(command)
    results = []

    # 标记前一步是否执行失败，辅助判断后续步骤是否被跳过
    is_previous_skipped = False

    for i in range(len(parts)):
        cmd_text = parts[i][0] if i < len(parts) else f"command_{i}"
        start_marker = f"===CMD_START_{i}==="
        end_marker = f"===CMD_END_{i}==="

        # 如果前一步被判定为 skipped，或者在 raw_output 中找不到当前步骤的 Marker
        start_idx = raw_output.find(start_marker)
        if start_idx == -1:
            is_previous_skipped = True
            results.append(f"[{i + 1}] {cmd_text}\nExit code: Skipped (Not Executed)\nOutput: -")
            continue

        output_start = start_idx + len(start_marker)
        end_idx = raw_output.find(end_marker, output_start)

        if end_idx == -1:
            cmd_output = raw_output[output_start:].strip()
            rc = -1
        else:
            cmd_output = raw_output[output_start:end_idx].strip()
            # 提取退出码
            rc_part = raw_output[end_idx + len(end_marker):]
            rc_marker = "RC="
            rc_idx = rc_part.find(rc_marker)
            if rc_idx != -1:
                rc_start = rc_idx + len(rc_marker)
                rc_end = rc_part.find("\n", rc_start)
                rc_str = rc_part[rc_start:rc_end].strip() if rc_end != -1 else rc_part[rc_start:].strip()
            else:
                rc_str = ""
            try:
                rc = int(rc_str)
            except (ValueError, TypeError):
                rc = -1

        status = f"Exit code: {rc}"
        results.append(f"[{i + 1}] {cmd_text}\n{status}\n{cmd_output}")

    return "\n---\n".join(results)


def _is_dangerous_command(command: str) -> tuple:
    """检查命令是否危险, 返回 (is_dangerous, reason)。拆分合并命令后逐项检查。"""
    for part in _split_merged_command(command):
        for pattern in DANGEROUS_COMMAND_PATTERNS:
            if re.search(pattern, part, re.IGNORECASE):
                return True, f"Blocked by pattern: {pattern} (in: {part})"
    return False, None


# --- Command Manager for Non-blocking Commands ---
class CommandManager:
    def __init__(self):
        self.commands = {}
        self.lock = threading.Lock()

    def start_command(self, command: str, cwd: str) -> tuple:
        cmd_id = str(uuid.uuid4())

        shell_cmd = command
        if os.name == 'nt':
            shell_cmd = ["powershell", "-Command", command]

        try:
            process = subprocess.Popen(
                shell_cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding='utf-8',
                errors='replace',
                shell=False if os.name == 'nt' else True
            )
        except Exception as e:
            return None, str(e)

        cmd_info = {
            "id": cmd_id,
            "process": process,
            "output": [],  # List of lines
            "status": "running",
            "start_time": time.time(),
            "cwd": cwd,
            "command": command
        }

        with self.lock:
            self.commands[cmd_id] = cmd_info

        # Start thread to read output
        t = threading.Thread(target=self._read_output, args=(cmd_id, process))
        t.daemon = True
        t.start()

        return cmd_id, None

    def _read_output(self, cmd_id, process):
        try:
            for line in iter(process.stdout.readline, ''):
                with self.lock:
                    if cmd_id in self.commands:
                        self.commands[cmd_id]["output"].append(line)
        except Exception:
            pass
        finally:
            try:
                process.stdout.close()
            except:
                pass

            return_code = process.wait()

            with self.lock:
                if cmd_id in self.commands:
                    self.commands[cmd_id]["status"] = "done"
                    self.commands[cmd_id]["returncode"] = return_code

    def get_status(self, cmd_id: str, priority: str = "bottom", limit: int = 1000):
        with self.lock:
            if cmd_id not in self.commands:
                return None

            cmd = self.commands[cmd_id]
            output_lines = cmd["output"]

            if priority == "bottom":
                lines = output_lines[-limit:]
            else:
                lines = output_lines[:limit]

            return {
                "status": cmd["status"],
                "returncode": cmd.get("returncode"),
                "output": "".join(lines),
                "cwd": cmd["cwd"],
                "command": cmd["command"]
            }

    def stop_command(self, cmd_id: str):
        with self.lock:
            if cmd_id not in self.commands:
                return False

            cmd = self.commands[cmd_id]
            if cmd["status"] == "running":
                try:
                    cmd["process"].terminate()
                    cmd["status"] = "stopped"
                except:
                    pass
                return True
            return False


_CMD_MANAGER = CommandManager()


class BashSessionManager:
    """管理 Bash 会话的 subprocess 实例，支持跨调用保持 cwd 和环境变量。"""

    def __init__(self, session_timeout: int = 600):
        self._sessions: Dict[str, subprocess.Popen] = {}
        self._session_cwd: Dict[str, str] = {}
        self._last_used: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._session_timeout = session_timeout

    def create_session(self, session_id: str, cwd: str) -> bool:
        """创建新的 shell 会话"""
        with self._lock:
            if session_id in self._sessions:
                return False
            if os.name == 'nt':
                shell = ["powershell", "-NoExit", "-Command", "-"]
            else:
                shell = ["/bin/bash", "-i"]
            try:
                proc = subprocess.Popen(
                    shell, cwd=cwd,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding='utf-8', errors='replace', bufsize=0,
                )
                self._sessions[session_id] = proc
                self._session_cwd[session_id] = cwd
                self._last_used[session_id] = time.time()
                return True
            except Exception:
                return False

    def execute_in_session(self, session_id: str, command: str, timeout: int = 120) -> Tuple[str, int]:
        """在已有会话中执行命令，返回 (output, returncode)"""
        with self._lock:
            proc = self._sessions.get(session_id)
            if not proc or proc.poll() is not None:
                return "Session not found or expired.", -1
        self._last_used[session_id] = time.time()
        try:
            delimiter = "===BASH_SESSION_EOF==="
            full_command = f"{command}; echo {delimiter}; echo $?"
            proc.stdin.write(full_command + "\n")
            proc.stdin.flush()
            output_lines = []
            deadline = time.time() + timeout
            found_delimiter = False
            while time.time() < deadline:
                line = proc.stdout.readline()
                if not line:
                    break
                if delimiter in line:
                    found_delimiter = True
                    break
                output_lines.append(line)
            returncode = -1
            if found_delimiter:
                rc_line = proc.stdout.readline()
                try:
                    returncode = int(rc_line.strip())
                except (ValueError, TypeError):
                    pass
            return "".join(output_lines), returncode
        except Exception as e:
            return f"Error executing in session: {e}", -1

    def close_session(self, session_id: str) -> bool:
        """关闭指定会话"""
        with self._lock:
            proc = self._sessions.pop(session_id, None)
            self._session_cwd.pop(session_id, None)
            self._last_used.pop(session_id, None)
        if proc:
            try:
                proc.stdin.write("exit\n")
                proc.stdin.flush()
                proc.stdin.close()
                proc.wait(timeout=5)
            except:
                proc.kill()
            return True
        return False

    def cleanup_expired(self):
        """清理超时会话"""
        now = time.time()
        with self._lock:
            expired = [sid for sid, t in self._last_used.items() if now - t > self._session_timeout]
        for sid in expired:
            self.close_session(sid)


_BASH_SESSION_MANAGER = BashSessionManager()


@register_tool(category="Agent", name_cn="Run Command", risk_level="high")
class RunCommand:
    """
    Execute shell commands. Supports merged command chains (e.g., `cd /tmp && ls && cat file.txt`).

    When to use:
    - Run terminal commands: git, npm, pip, systemctl, docker, etc.
    - Chain multiple dependent commands in one call using && or ; (output shows each step separately)
    - Maintain state across calls with session_id (keeps cwd and env variables)

    When NOT to use:
    - For file operations (reading/writing/editing/searching) — use the dedicated file tools instead
    - For interactive commands (top, nano, vi) — they will hang
    - For commands requiring sudo user input — use non-interactive flags (e.g., apt-get -y)

    Safety:
    - Dangerous commands are auto-blocked (rm -rf /, dd, mkfs, curl|bash, etc.)

    Command chaining examples:
    - `cd /www/wwwlogs && ls -la && tail -50 access.log` — 3 steps, single call
    - `echo "line1" && echo "line2" && echo "line3"` — all outputs individually labeled

    Args:
        command: Shell command to execute (supports && ; || chains)
        blocking: Wait for completion (default True). False returns immediately with a command_id for later polling.
        cwd: Working directory for the command
        timeout: Timeout in milliseconds (default 120000 = 2 min)
        session_id: Optional session ID to reuse the same subprocess (preserves cwd, env vars)
        description: Brief description of what this command does (for logging)
    """

    def execute(self, command: str, blocking: bool = True, cwd: str = None, timeout: int = 120000,
                session_id: str = None, description: str = None) -> str:
        BASH_MAX_RETURN_CHARS = 30000

        if not cwd:
            cwd = os.getcwd()

        # 危险命令检查
        is_dangerous, reason = _is_dangerous_command(command)
        if is_dangerous:
            return _xml_response("RunCommand", "error", f"Dangerous command blocked. {reason}.")

        # 清理超时会话
        _BASH_SESSION_MANAGER.cleanup_expired()

        # 会话模式
        if session_id:
            return self._execute_session(command, session_id, cwd, timeout, description, BASH_MAX_RETURN_CHARS)

        # 无状态模式
        return self._execute_stateless(command, cwd, timeout, blocking, description, BASH_MAX_RETURN_CHARS)

    def _execute_stateless(self, command: str, cwd: str, timeout: int, blocking: bool,
                           description: str, max_chars: int) -> str:
        """无状态模式：每次执行独立 subprocess，合并命令注入动态分界符"""
        if not blocking:
            cmd_id, err = _CMD_MANAGER.start_command(command, cwd)
            if err:
                return _xml_response("RunCommand", "error", err, max_chars=max_chars)

            result = (
                f"<terminal_id>new</terminal_id>\n"
                f"<terminal_cwd>{cwd}</terminal_cwd>\n"
                f"Note: Command ID is provided for you to check command status later.\n"
                f"<command_id>{cmd_id}</command_id>\n"
                f"The command is running, you need to call check_command_status tool to get more logs.\n"
            )
            return _xml_response("RunCommand", "running", result, max_chars=max_chars)

        try:
            parts = _split_merged_command(command)
            is_merged = len(parts) > 1

            if is_merged:
                # 合并命令：注入动态分界符
                shell_cmd = _wrap_merged_command_with_markers(command)
            else:
                shell_cmd = command

            if os.name == 'nt':
                shell_cmd = ["powershell", "-Command", shell_cmd]

            timeout_sec = timeout / 1000.0
            start_time = time.time()

            result = subprocess.run(
                shell_cmd, cwd=cwd, capture_output=True, text=True,
                encoding='utf-8', errors='replace',
                shell=False if os.name == 'nt' else True, timeout=timeout_sec
            )

            raw_output = result.stdout + result.stderr
            duration = time.time() - start_time

            if is_merged:
                output = _parse_merged_output(raw_output, command)
            else:
                output = raw_output

            metadata = f"Exit Code: {result.returncode}\nDuration: {duration:.2f}s"
            final_output = f"{metadata}\n\n{output}"

            if description:
                final_output = f"Description: {description}\n\n{final_output}"

            return _xml_response("RunCommand", "done", final_output, max_chars=max_chars)

        except subprocess.TimeoutExpired:
            return _xml_response("RunCommand", "error", f"Command timed out after {timeout} ms", max_chars=max_chars)
        except Exception as e:
            return _xml_response("RunCommand", "error", str(e), max_chars=max_chars)

    def _execute_session(self, command: str, session_id: str, cwd: str, timeout: int,
                         description: str, max_chars: int) -> str:
        """会话模式：复用已有 subprocess 实例，合并命令注入动态分界符"""
        if session_id not in _BASH_SESSION_MANAGER._sessions:
            if not _BASH_SESSION_MANAGER.create_session(session_id, cwd):
                return _xml_response("RunCommand", "error", f"Failed to create session: {session_id}")

        parts = _split_merged_command(command)
        is_merged = len(parts) > 1

        if is_merged:
            exec_cmd = _wrap_merged_command_with_markers(command)
        else:
            exec_cmd = command

        timeout_sec = timeout / 1000.0
        start_time = time.time()

        raw_output, returncode = _BASH_SESSION_MANAGER.execute_in_session(session_id, exec_cmd, int(timeout_sec))
        duration = time.time() - start_time

        if is_merged:
            output = _parse_merged_output(raw_output, command)
        else:
            output = raw_output

        metadata = f"Exit Code: {returncode}\nDuration: {duration:.2f}s\nSession: {session_id}"
        final_output = f"{metadata}\n\n{output}"

        if description:
            final_output = f"Description: {description}\n\n{final_output}"

        return _xml_response("RunCommand", "done", final_output, max_chars=max_chars)
