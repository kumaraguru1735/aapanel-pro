from . import register_tool
import glob
import re
import shutil
from typing import List

# Import shared helper
from .base import _xml_response

import subprocess
import os, sys

os.chdir('/www/server/panel/')
sys.path.insert(0, 'class/')
sys.path.insert(0, '/www/server/panel/')
import public
from public import lang

# 系统关键路径黑名单 (禁止写入/删除)
BLOCKED_PATHS = [
    '/etc/passwd',
    '/etc/shadow',
    '/etc/sudoers',
    '/etc/ssh/sshd_config',
    '/bin/',
    '/sbin/',
    '/usr/bin/',
    '/usr/sbin/',
    '/lib/',
    '/lib64/',
    '/boot/',
    '/proc/',
    '/sys/',
    '/dev/',
    '/root/.ssh/',
    '/www/server/panel/BTPanel/__init__.py',
]


def _is_blocked_path(file_path: str) -> tuple:
    """检查路径是否在黑名单中, 返回 (is_blocked, reason)"""
    abs_path = os.path.abspath(file_path)
    for blocked in BLOCKED_PATHS:
        if abs_path == blocked or abs_path.startswith(blocked):
            return True, f"Path is system critical: {blocked}"
    return False, None


# --- Tools ---

@register_tool(category="Agent", name_cn="Glob Find", risk_level="low")
def Glob(pattern: str, path: str = None) -> str:
    """
    Fast file pattern matching. Finds files matching glob patterns like "**/*.py" or "src/**/*.js".

    When to use:
    - Find files by name pattern or extension across a directory tree
    - Locate config files, source files, or log files by extension
    - Discover all files of a specific type (e.g., "*.conf", "*.log")

    When NOT to use:
    - To search file contents — use Grep Search instead
    - To list directory structure — use List Directory instead

    Args:
        pattern: The glob pattern to match (e.g., "*.conf", "**/*.py", "nginx/*")
        path: The directory to search in (absolute path). Defaults to /www/server/panel/
    """
    if not path:
        path = os.getcwd()

    try:
        if not os.path.exists(path):
            return _xml_response("Glob", "error", f"Path not found: {path}")

        search_path = os.path.join(path, pattern)
        files = glob.glob(search_path, recursive=True)

        # Filter only files and sort by mtime (descending)
        file_stats = []
        for f in files:
            if os.path.isfile(f):
                try:
                    mtime = os.path.getmtime(f)
                    file_stats.append((f, mtime))
                except:
                    pass

        file_stats.sort(key=lambda x: x[1], reverse=True)

        limit = 100
        truncated = False
        if len(file_stats) > limit:
            file_stats = file_stats[:limit]
            truncated = True

        output = [f[0] for f in file_stats]

        if not output:
            return _xml_response("Glob", "done", "No files found")

        result = "\n".join(output)
        if truncated:
            result += f"\n\n(Results are truncated: showing first {limit} results. Consider using a more specific path or pattern.)"

        return _xml_response("Glob", "done", result)
    except Exception as e:
        return _xml_response("Glob", "error", str(e))


@register_tool(category="Agent", name_cn="Grep Search", risk_level="low")
def Grep(pattern: str, include: str = None, path: str = None, **kwargs) -> str:
    r"""
    Search file contents using regular expressions. Returns matching lines with file paths and line numbers.

    When to use:
    - Find where a specific function, variable, or configuration is defined/used
    - Search for error messages, log patterns, or specific text across multiple files
    - Locate code by content rather than filename

    When NOT to use:
    - To find files by name pattern — use Glob Find instead
    - To count exact matches or complex analysis — use RunCommand with `rg` (ripgrep)

    Args:
        pattern: The regex pattern to search for (e.g., "def get_sites", "error.*timeout")
        include: File pattern filter (e.g., "*.py", "*.conf"). Defaults to all files.
        path: The directory to search in (absolute path). Defaults to /www/server/panel/
    """
    if not path:
        path = os.getcwd()

    try:
        import glob as glob_module

        # 1. Find files
        files_to_search = []
        if os.path.isfile(path):
            files_to_search = [path]
        else:
            search_glob = include if include else "**/*"
            # Support simple brace expansion if needed, but glob doesn't support it natively in all versions
            # For simplicity, we assume standard glob patterns
            candidates = glob_module.glob(os.path.join(path, search_glob), recursive=True)
            files_to_search = [f for f in candidates if os.path.isfile(f)]

        regex = re.compile(pattern)
        matches = []
        MAX_LINE_LENGTH = 2000

        for file_path in files_to_search:
            try:
                # Check file size/binary? Skip for now to keep simple
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    try:
                        mtime = os.path.getmtime(file_path)
                    except:
                        mtime = 0

                    for i, line in enumerate(lines):
                        if regex.search(line):
                            matches.append({
                                "path": file_path,
                                "lineNum": i + 1,
                                "lineText": line.rstrip(),
                                "mtime": mtime
                            })
            except Exception:
                continue

        # Sort by mtime desc
        matches.sort(key=lambda x: x["mtime"], reverse=True)

        limit = 100
        truncated = len(matches) > limit
        final_matches = matches[:limit] if truncated else matches

        if not final_matches:
            return _xml_response("Grep", "done", "No files found")

        output_lines = [f"Found {len(matches)} matches{f' (showing first {limit})' if truncated else ''}"]

        current_file = ""
        for match in final_matches:
            if current_file != match["path"]:
                if current_file != "":
                    output_lines.append("")
                current_file = match["path"]
                output_lines.append(f"{match['path']}:")

            line_text = match["lineText"]
            if len(line_text) > MAX_LINE_LENGTH:
                line_text = line_text[:MAX_LINE_LENGTH] + "..."
            output_lines.append(f"  Line {match['lineNum']}: {line_text}")

        if truncated:
            output_lines.append("")
            output_lines.append(
                f"(Results truncated: showing {limit} of {len(matches)} matches. Consider using a more specific path or pattern.)")

        return _xml_response("Grep", "done", "\n".join(output_lines))

    except Exception as e:
        return _xml_response("Grep", "error", str(e))


@register_tool(category="Agent", name_cn="List Directory", risk_level="low")
def LS(path: str = None, ignore: List[str] = None) -> str:
    """
    Browse directory structure. Lists files and subdirectories with a tree-like view, auto-ignoring common noise directories (node_modules, .git, __pycache__, etc).

    When to use:
    - Explore unknown directory structures or understand project layout
    - Check what files exist in a specific directory
    - Quick overview of project structure

    When NOT to use:
    - To find files by pattern — use Glob Find instead
    - To search file contents — use Grep Search instead

    Args:
        path: The absolute path to list. Defaults to /www/server/panel/
        ignore: Additional glob patterns to exclude (e.g., ["*.log", "temp/*"])
    """
    if not path:
        path = os.getcwd()

    try:
        if not os.path.exists(path):
            return _xml_response("LS", "error", "Path not found")

        DEFAULT_IGNORE = [
            "node_modules", "__pycache__", ".git", "dist", "build", "target",
            "vendor", "bin", "obj", ".idea", ".vscode", ".zig-cache", "zig-out",
            "coverage", "tmp", "temp", ".cache", "logs",
            ".venv", "venv", "env"
        ]

        ignore_patterns = DEFAULT_IGNORE + (ignore if ignore else [])

        LIMIT = 100

        def should_ignore(name):
            return name in ignore_patterns or any(glob.fnmatch.fnmatch(name, p) for p in ignore_patterns)  # noqa

        try:
            entries = os.listdir(path)
        except PermissionError:
            return _xml_response("LS", "error", f"Permission denied: {path}")

        dirs = []
        files = []
        for entry in entries:
            if should_ignore(entry):
                continue
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                dirs.append(entry)
            else:
                files.append(entry)

        dirs.sort()
        files.sort()

        output_lines = [f"{path}/"]

        for d in dirs:
            subdir_path = os.path.join(path, d)
            output_lines.append(f"  {d}/")

            try:
                sub_entries = os.listdir(subdir_path)
            except PermissionError:
                continue

            sub_dirs = []
            sub_files = []
            for entry in sub_entries:
                if should_ignore(entry):
                    continue
                entry_path = os.path.join(subdir_path, entry)
                if os.path.isdir(entry_path):
                    sub_dirs.append(entry)
                else:
                    sub_files.append(entry)

            sub_dirs.sort()
            sub_files.sort()

            count = 0
            truncated = False
            for sub_d in sub_dirs:
                if count >= LIMIT:
                    truncated = True
                    break
                output_lines.append(f"    {sub_d}/")
                count += 1

            for sub_f in sub_files:
                if count >= LIMIT:
                    truncated = True
                    break
                output_lines.append(f"    {sub_f}")
                count += 1

            if truncated:
                output_lines.append(
                    f"    ... ({lang('Showing')} {LIMIT} {lang('items in current directory, use LS tool for more')})")

        for f in files:
            output_lines.append(f"  {f}")

        return _xml_response("LS", "done", "\n".join(output_lines))
    except Exception as e:
        return _xml_response("LS", "error", str(e))


@register_tool(category="Agent", name_cn="Write File", risk_level="high")
def Write(file_path: str, content: str) -> str:
    """
     Create or overwrite a file with the given content.

    Rules:
    - MUST read the file first with the Read tool if the file already exists — otherwise it will fail
    - Prefer SearchReplace for editing existing files (it preserves unchanged content)
    - Use this tool only for creating new files or complete rewrites
    - Blocked from modifying system-critical paths (/etc/passwd, /bin/, /root/.ssh/, etc.)

    Args:
        file_path: The absolute path to write to (must be absolute, not relative)
        content: The complete file content to write
    """
    # 路径黑名单检查
    is_blocked, reason = _is_blocked_path(file_path)
    if is_blocked:
        return _xml_response("Write", "error",
                             f"Path blocked: {reason}. System critical files cannot be modified through AI assistant.")

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return _xml_response("Write", "done", f"File written: {file_path}")
    except Exception as e:
        return _xml_response("Write", "error", str(e))


@register_tool(category="Agent", name_cn="Delete File", risk_level="high")
def DeleteFile(file_paths: List[str]) -> str:
    """
    Permanently delete files or directories (recursive for directories).

    Rules:
    - Blocked from deleting system-critical paths (/etc/passwd, /bin/, /root/.ssh/, etc.)
    - Directories are deleted recursively (like rm -rf)
    - All paths must be absolute

    Args:
        file_paths: List of absolute file/directory paths to delete
    """
    deleted = []
    errors = []
    for path in file_paths:
        # 路径黑名单检查
        is_blocked, reason = _is_blocked_path(path)
        if is_blocked:
            errors.append(f"{path}: Blocked - {reason}")
            continue

        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            deleted.append(path)
        except Exception as e:
            errors.append(f"{path}: {str(e)}")

    result = "<file_changes>\nThese files is deleted in this toolcall:\n<deleted_files>\n"
    for p in deleted:
        result += f"  - {p}\n"
    result += "</deleted_files>\n</file_changes>"

    if errors:
        result += f"\nErrors:\n" + "\n".join(errors)

    return _xml_response("DeleteFile", "done", result)


def _run_shell_cmd(command: list, timeout: int = 300) -> tuple:
    """
    Common function to execute shell commands.
    Returns (success: bool, output: str)
    """
    try:
        # Use shell=False for security when passing a list
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        output = result.stdout.strip()
        if not output:
            output = result.stderr.strip()

        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, f"Error: Command timed out after {timeout} seconds."
    except FileNotFoundError:
        return False, f"Error: Command not found: {command[0]}"
    except Exception as e:
        return False, f"Error executing command: {str(e)}"


@register_tool(category="System", name_cn="Get System Resources", risk_level="low")
def get_system_resources() -> str:
    """
    Get real-time system resource metrics: CPU load average, memory usage, disk usage, and OS version.

    Use for:
    - Quick server health check
    - Determine if server is under heavy load
    - Check available disk space before file operations

    Returns: Load Avg (1m/5m/15m), Memory (used/total + %), Disk / (used/total + %), OS version
    """
    try:
        # Load Average
        try:
            load1, load5, load15 = os.getloadavg()
            load_info = f"Load Avg: {load1:.2f}, {load5:.2f}, {load15:.2f}"
        except OSError:
            load_info = "Load Avg: N/A (Windows?)"

        # Memory
        mem_info = "Mem: Unknown"
        if os.path.exists('/proc/meminfo'):
            with open('/proc/meminfo', 'r') as f:
                lines = f.readlines()
                total = 0
                available = 0
                for line in lines:
                    if 'MemTotal' in line:
                        total = int(line.split()[1]) // 1024  # MB
                    if 'MemAvailable' in line:
                        available = int(line.split()[1]) // 1024  # MB
                used = total - available
                percent = (used / total * 100) if total > 0 else 0
                mem_info = f"Mem: {used}MB/{total}MB ({percent:.1f}%)"

        # Disk
        disk = shutil.disk_usage("/")
        total_gb = disk.total // (1024 ** 3)
        used_gb = disk.used // (1024 ** 3)
        disk_percent = (disk.used / disk.total * 100)
        disk_info = f"Disk (/): {used_gb}GB/{total_gb}GB ({disk_percent:.1f}%)"
        os_info = public.get_os_version()

        result = f"{load_info}\n{mem_info}\n{disk_info}\nOS: {os_info}"
        return _xml_response("get_system_resources", "done", result)
    except Exception as e:
        return _xml_response("get_system_resources", "error", f"Error getting resources: {str(e)}")


@register_tool(category="Website", name_cn="Get Website List", risk_level="medium")
def get_sites() -> str:
    """
    List all websites managed by aaPanel (excluding Docker-based sites).

    Use for:
    - Discover all deployed websites and their types (PHP, static, proxy, etc.)
    - Find website names/IDs before using other website tools

    Returns: JSON array with id, name (domain or ip:port), project_type (PHP/html/proxy/etc.)
    """
    import json
    sites = public.M('sites').field('id,name,project_type').select()
    return _xml_response("get_sites", "done", json.dumps(sites, ensure_ascii=False, indent=2))


@register_tool(category="Website", name_cn="Get Website Config", risk_level="medium")
def get_sites_conf(site_name_list: List[str] = None) -> str:
    """
    Get the nginx or Apache configuration files for one or more websites.

    Use for:
    - Inspect website server configuration (vhost, SSL, rewrite rules, etc.)
    - Diagnose 403/502/500 errors related to server config
    - Check reverse proxy, SSL, or redirect settings

    Args:
        site_name_list: List of website domains/ip:port from Get Website List. Empty list returns ALL configs.
    """
    import json
    if not site_name_list:
        all_sites = public.M('sites').field('name,project_type').select()
        if not all_sites:
            return _xml_response("get_sites_conf", "done",
                                 json.dumps({"error": "No sites found in panel."}, ensure_ascii=False, indent=2))
        site_name_list = [s['name'] for s in all_sites]

    results = {}
    for site_name in site_name_list:
        site_data = public.M('sites').field('name,project_type').where("name=?", site_name).select()
        if not site_data:
            results[site_name] = {"error": f"Site not found in panel."}
            continue

        project_type = site_data[0]['project_type'].lower()
        prefix = '' if project_type in ('php', 'proxy', 'phpmod', 'wp2') else project_type + '_'

        conf_path = f"/www/server/panel/vhost/nginx/{prefix}{site_name}.conf"
        if not os.path.exists(conf_path):
            conf_path = f"/www/server/panel/vhost/apache/{prefix}{site_name}.conf"
            if not os.path.exists(conf_path):
                results[site_name] = {"error": "Configuration file not found."}
                continue

        with open(conf_path, 'r') as f:
            results[site_name] = f.read()

    if len(site_name_list) == 1 and "error" not in results:
        return _xml_response("get_sites_conf", "done", results[site_name_list[0]])
    return _xml_response("get_sites_conf", "done", json.dumps(results, ensure_ascii=False, indent=2))


@register_tool(category="Website", name_cn="Get Website Access Logs", risk_level="medium")
def get_sites_logs(site_name_list: List[str] = None) -> str:
    """
    Get recent access logs for one or more websites (up to 1000 lines each).

    Use for:
    - Analyze recent visitor traffic, HTTP status codes, and request patterns
    - Diagnose 404, 500, or other HTTP errors by examining log entries
    - Identify suspicious activity (repeated failed requests, scanner bots)

    Args:
        site_name_list: List of website domains/ip:port from Get Website List. Empty list returns logs for ALL sites.
    """
    import json
    from logsModelV2.siteModel import main
    logs_model = main()

    if not site_name_list:
        all_sites = public.M('sites').field('name').select()
        if not all_sites:
            return _xml_response("get_sites_logs", "done",
                                 json.dumps({"error": "No sites found in panel."}, ensure_ascii=False, indent=2))
        site_name_list = [s['name'] for s in all_sites]

    results = {}
    for site_name in site_name_list:
        logs = logs_model.GetSiteLogs(public.to_dict_obj({"siteName": site_name})).get("message")
        results[site_name] = logs

    if len(site_name_list) == 1:
        return _xml_response("get_sites_logs", "done",
                             json.dumps(results[site_name_list[0]], ensure_ascii=False, indent=2))
    return _xml_response("get_sites_logs", "done", json.dumps(results, ensure_ascii=False, indent=2))


@register_tool(category="Website", name_cn="Get Website Traffic Data", risk_level="medium")
def get_site_overview(site_name_list: List[str] = None) -> str:
    """
    Get statistical traffic data for one or more websites over the last 7 days (UV, PV, bandwidth, etc).

    Use for:
    - Check website traffic trends and visitor counts
    - Compare bandwidth usage and request volume
    - Generate traffic reports for one or more websites

    Args:
        site_name_list: List of website domains/ip:port from Get Website List. Empty list returns overview for ALL sites.
    """
    import json
    from projectModelV2.monitorModel import main as monitor

    if not site_name_list:
        all_sites = public.M('sites').field('name').select()
        if not all_sites:
            return _xml_response("get_site_overview", "done",
                                 json.dumps({"error": "No sites found in panel."}, ensure_ascii=False, indent=2))
        site_name_list = [s['name'] for s in all_sites]

    results = {}
    for site_name in site_name_list:
        monitordata = monitor().get_overview(public.to_dict_obj({"site_name": site_name})).get("message")
        results[site_name] = monitordata

    if len(site_name_list) == 1:
        return _xml_response("get_site_overview", "done",
                             json.dumps(results[site_name_list[0]], ensure_ascii=False, indent=2))
    return _xml_response("get_site_overview", "done", json.dumps(results, ensure_ascii=False, indent=2))


@register_tool(category="Website", name_cn="Get All Website Traffic Data", risk_level="medium")
def get_site_analysis() -> str:
    """
    Get aggregated traffic data for all websites (last 7 days), ranked by traffic.

    Use for:
    - Compare traffic across all websites to find most/least visited sites
    - Identify which websites are consuming the most bandwidth
    - Generate overall website traffic reports
    """
    import json
    from projectModelV2.monitorModel import main as monitor

    monitordata = monitor().get_overview(public.to_dict_obj({"metric": "traffic", "order": "desc"})).get("message")

    return _xml_response("get_site_analysis", "done", json.dumps(monitordata, ensure_ascii=False, indent=2))


@register_tool(category="Database", name_cn="Get MySQL Database List", risk_level="medium")
def get_mysql_list() -> str:
    """
    List all MySQL databases managed by aaPanel (passwords are redacted).

    Use for:
    - Discover available databases and their associated users
    - Check which databases exist before running queries or migrations
    - Verify database access permissions (allowed IPs)

    Returns: JSON array with name, username, accept (allowed IP), type
    """
    import json
    dbs = public.M('databases').field('name,username,accept,type').where("type=?", "MySQL").select()
    return _xml_response("get_mysql_list", "done", json.dumps(dbs, ensure_ascii=False, indent=2))


@register_tool(category="System", name_cn="Get Top 10 Processes", risk_level="low")
def get_top_processes() -> str:
    """
    Get the top 10 processes by CPU usage and top 10 by memory usage.

    Use for:
    - Identify what is consuming high CPU or memory resources
    - Diagnose server slowdowns or high load
    - Find specific processes to investigate or restart

    Returns: Two sections — CPU TOP 10 and Memory TOP 10 (PID, user, %cpu, %mem, command)
    """
    output_parts = []

    # 1. CPU Top 10
    success_cpu, output_cpu = _run_shell_cmd(["ps", "-eo", "pid,user,%cpu,%mem,command", "--sort=-%cpu"])
    if success_cpu:
        lines = output_cpu.strip().splitlines()
        header = lines[0] if lines else ""
        top10 = lines[1:11]
        output_parts.append("--- CPU Usage TOP 10 ---")
        output_parts.append(header)
        output_parts.extend(top10)
    else:
        output_parts.append(f"{lang('Failed to get CPU TOP 10')}: {output_cpu}")

    output_parts.append("")  # 空行分隔

    # 2. Memory Top 10
    success_mem, output_mem = _run_shell_cmd(["ps", "-eo", "pid,user,%cpu,%mem,command", "--sort=-%mem"])
    if success_mem:
        lines = output_mem.strip().splitlines()
        header = lines[0] if lines else ""
        top10 = lines[1:11]
        output_parts.append("--- Memory Usage TOP 10 ---")
        output_parts.append(header)
        output_parts.extend(top10)
    else:
        output_parts.append(f"{lang('Failed to get Memory TOP 10')}: {output_mem}")

    return _xml_response("get_top_processes", "done", "\n".join(output_parts))
