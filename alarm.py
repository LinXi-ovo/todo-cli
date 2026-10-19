"""提醒与闹钟模块。

供 td.py 调用，负责：
  1. 用 Windows Toast 弹系统通知
  2. 守护进程循环检查到点的任务并提醒
  3. 开关开机自启（写注册表 Run 项）

仅支持 Windows。
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# 注册表自启项名称
RUN_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "TdAlarm"

# 默认提前提醒分钟数
DEFAULT_LEAD_MINUTES = 10

TOAST_SCRIPT = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$title = $env:TD_TITLE
$body  = $env:TD_BODY

$escTitle = [System.Security.SecurityElement]::Escape($title)
$escBody  = [System.Security.SecurityElement]::Escape($body)

$template = "<toast scenario=`"reminder`"><visual><binding template=`"ToastGeneric`"><text>$escTitle</text><text>$escBody</text></binding></visual><audio silent=`"false`" /></toast>"

$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)

$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:TD_APPID)
$notifier.Show($toast)
"""


class AlarmError(Exception):
    """提醒相关的可预期错误"""


# ---------- 通知 ----------
def notify(title: str, body: str) -> bool:
    """弹 Windows Toast 通知；失败时退回 MessageBox"""
    if _toast(title, body):
        return True
    return _messagebox(title, body)


def _run_ps(script: str, args: list[str] | None = None,
            timeout: int = 20, env: dict | None = None):
    """稳健地跑 PowerShell：不按 UTF-8 硬解码，避免中文系统上解码异常

    返回 (returncode, stdout_text)。解码失败时用 errors='replace' 兜底。
    """
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
    if args:
        cmd += args
    try:
        proc = subprocess.run(
            cmd, capture_output=True, timeout=timeout, env=env,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""

    err = proc.stderr or b""
    out = proc.stdout or b""
    try:
        stderr_text = err.decode("utf-8", "replace")
    except Exception:
        stderr_text = ""
    try:
        stdout_text = out.decode("utf-8", "replace")
    except Exception:
        stdout_text = ""
    # 仅为调试保留，实际判断只看 returncode
    if proc.returncode != 0 and stderr_text:
        pass
    return proc.returncode, stdout_text


def _toast(title: str, body: str) -> bool:
    """调用 PowerShell 发送 Toast。

    注意：-Command 后面的脚本串无法接收 param()，必须用环境变量传参。
    """
    import os
    env = dict(os.environ, TD_TITLE=title, TD_BODY=body, TD_APPID="td todo")
    code, _ = _run_ps(TOAST_SCRIPT, timeout=20, env=env)
    return code == 0


def _messagebox(title: str, body: str) -> bool:
    """兜底：传统弹窗"""
    import os
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "[System.Windows.Forms.MessageBox]::Show($env:TD_BODY, $env:TD_TITLE) | Out-Null"
    )
    env = dict(os.environ, TD_TITLE=title, TD_BODY=body)
    code, _ = _run_ps(script, timeout=120, env=env)
    return code == 0


# ---------- 到点判断 ----------
def task_due_at(task: dict):
    """算出任务的提醒时间点；无有效日期则返回 None"""
    date_text = task.get("date")
    if not date_text:
        return None
    time_text = task.get("time") or "09:00"
    try:
        return datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def parse_remind(task: dict, default_lead: int = DEFAULT_LEAD_MINUTES):
    """算出实际提醒时刻：优先用 remind 字段，否则按提前量推算"""
    due = task_due_at(task)
    if not due:
        return None

    remind_text = task.get("remind")
    if remind_text:
        try:
            hh, mm = remind_text.split(":")
            return due.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        except (ValueError, AttributeError):
            pass
    return due - timedelta(minutes=default_lead)


def due_now(tasks: list, now: datetime | None = None, default_lead: int = DEFAULT_LEAD_MINUTES):
    """返回此刻应该提醒的任务（提醒时间已到且未提醒过）"""
    now = now or datetime.now()
    fired = []
    for task in tasks:
        if task.get("done") or task.get("reminded"):
            continue
        remind_at = parse_remind(task, default_lead)
        if not remind_at:
            continue
        # 提醒时间已到，且没超过太久（避免开机时把陈年任务全弹一遍）
        if remind_at <= now <= remind_at + timedelta(minutes=30):
            fired.append((task, remind_at))
    return fired


def describe(task: dict) -> str:
    """生成通知正文"""
    parts = []
    if task.get("date"):
        parts.append(task["date"])
    if task.get("time"):
        parts.append(task["time"])
    when = " ".join(parts)
    ttype = task.get("type")
    head = f"[{ttype}] " if ttype else ""
    return f"{head}{when}".strip() or "该做这件事了"


# ---------- 守护进程 ----------
def run_daemon(data_path: Path, state_path: Path, interval: int = 30,
               default_lead: int = DEFAULT_LEAD_MINUTES, on_fire=None):
    """循环检查到点任务并提醒，直到进程被杀。

    state_path 记录已提醒过的任务，避免重复弹窗。
    """
    print(f"提醒守护进程已启动，每 {interval} 秒检查一次。Ctrl+C 退出。", flush=True)

    while True:
        try:
            tasks = _load_tasks(data_path)
            fired_state = _load_state(state_path)
            now = datetime.now()

            for task, remind_at in due_now(tasks, now, default_lead):
                key = _task_key(task)
                if key in fired_state:
                    continue
                ok = notify(task.get("title", "待办提醒"), describe(task))
                fired_state[key] = now.strftime("%Y-%m-%d %H:%M:%S")
                _save_state(state_path, fired_state)
                if on_fire:
                    on_fire(task, ok)
                print(f"[{now:%H:%M:%S}] 已提醒：{task.get('title')}", flush=True)

            # 清理过期记录，防止状态文件无限增长
            _prune_state(state_path, fired_state)
        except Exception as exc:  # 守护进程不能因单次异常退出
            print(f"[{datetime.now():%H:%M:%S}] 检查出错：{exc}", flush=True)

        time.sleep(interval)


def _load_tasks(path: Path) -> list:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _task_key(task: dict) -> str:
    """任务唯一标识：标题+日期+时间"""
    return f"{task.get('title')}|{task.get('date')}|{task.get('time')}"


def _load_state(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(path: Path, state: dict):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _prune_state(path: Path, state: dict, keep_days: int = 7):
    """丢掉 7 天前的提醒记录"""
    cutoff = datetime.now() - timedelta(days=keep_days)
    kept = {}
    for key, ts in state.items():
        try:
            when = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            continue
        if when >= cutoff:
            kept[key] = ts
    if len(kept) != len(state):
        _save_state(path, kept)


# ---------- 开机自启 ----------
def enable_autostart(script_path: Path) -> str:
    """把守护进程写入注册表 Run 项，返回结果描述"""
    cmd = f'"{sys.executable}" "{script_path}" __daemon__'
    try:
        proc = subprocess.run(
            ["reg", "add", RUN_KEY, "/v", RUN_NAME, "/t", "REG_SZ", "/d", cmd, "/f"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AlarmError(f"写入注册表失败：{exc}") from exc
    if proc.returncode != 0:
        raise AlarmError(f"写入注册表失败：{proc.stderr.strip() or proc.stdout.strip()}")
    return f"已开启开机自启：{RUN_KEY}\\{RUN_NAME}"


def disable_autostart() -> str:
    """移除注册表 Run 项"""
    try:
        proc = subprocess.run(
            ["reg", "delete", RUN_KEY, "/v", RUN_NAME, "/f"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AlarmError(f"删除注册表项失败：{exc}") from exc
    if proc.returncode != 0:
        raise AlarmError(f"删除注册表项失败：{proc.stderr.strip() or proc.stdout.strip()}")
    return "已关闭开机自启"


def autostart_enabled() -> bool:
    """查询注册表里是否已有自启项"""
    try:
        proc = subprocess.run(
            ["reg", "query", RUN_KEY, "/v", RUN_NAME],
            capture_output=True, text=True, timeout=15,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
