"""LLM 任务生成模块（仅 OpenAI 兼容接口）。

供 td.py 以 `import llm` 方式调用，依赖 requests + python-dotenv。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

# OpenAI 兼容接口的默认路径（url 只给 base 时补上）
DEFAULT_PATH = "/v1/chat/completions"

SYSTEM_PROMPT = (
    "你是一个日程与待办解析助手。把用户给出的自然语言描述拆解成若干条独立任务，"
    "并为每条提取时间信息和类型。\n"
    "\n"
    "严格只输出 JSON 数组，不要解释文字，不要 markdown 代码块。\n"
    "每个元素是一个对象，字段如下：\n"
    '  "title": 任务标题，简短可执行，去掉时间词后仍语义完整\n'
    '  "date":  截止/执行日期，格式 YYYY-MM-DD；无法确定时输出 null\n'
    '  "time":  具体时刻，格式 HH:MM（24 小时制）；无法确定时输出 null\n'
    '  "remind":提醒时间，格式 HH:MM；未提及则 null（默认在 time 前 10 分钟提醒）\n'
    '  "type":  任务类型，只能取以下之一：'
    "work（工作）/ study（学习）/ life（生活）/ health（健康）/ "
    "meeting（会议）/ other（其他）\n"
    "\n"
    "今天是 {today}，当前时间 {now}，请据此推算「明天」「下周三」「三天后」等相对时间。\n"
    "\n"
    "示例输入：明天下午3点开组会，晚上8点吃药\n"
    "示例输出：\n"
    '[{{"title":"开组会","date":"2026-10-20","time":"15:00","remind":null,"type":"meeting"}},'
    '{{"title":"吃药","date":"2026-10-20","time":"20:00","remind":null,"type":"health"}}]'
)


class LLMError(Exception):
    """调用大模型过程中的可预期错误"""


def build_system_prompt() -> str:
    """把当前日期时间注入提示词，便于模型推算相对时间"""
    now = datetime.now()
    return SYSTEM_PROMPT.format(
        today=now.strftime("%Y-%m-%d"),
        now=now.strftime("%H:%M"),
    )

def build_url(config: dict) -> str:
    """拼出完整请求地址，容忍用户已经填了 /v1 或完整路径"""
    url = str(config.get("llm_url") or "").strip()
    if not url:
        raise LLMError("未配置 llm_url，请先执行：td cfg set llm_url <地址>")

    base = url.rstrip("/")

    # 已经是完整接口地址，原样使用
    if base.endswith("chat/completions"):
        return base

    # 已以 /v1 结尾，只补后半段，避免拼成 /v1/v1/...
    if base.endswith("/v1"):
        return base + "/chat/completions"

    return base + DEFAULT_PATH


def resolve_api_key(config: dict, env_path: Path) -> str:
    """取 apikey：配置显式值 > 环境变量 / .env 的 TD_LLM_APIKEY"""
    raw = str(config.get("llm_apikey") or "").strip()
    if raw.lower().startswith("env:"):
        name = raw[4:].strip()
        return os.environ.get(name) or ""
    if raw:
        return raw

    load_dotenv(env_path)
    return os.environ.get("TD_LLM_APIKEY") or os.environ.get("TD_API_KEY") or ""


def extract_tasks(text: str) -> list[dict]:
    """从模型输出里抽出任务对象，容忍代码块包裹和多余文字。

    返回 [{"title","date","time","remind","type"}, ...]
    缺字段时填 None；纯字符串输出也能兼容。
    """
    if not text or not text.strip():
        raise LLMError("模型返回了空内容")

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(
            ln for ln in cleaned.splitlines() if not ln.strip().startswith("```")
        ).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("["), cleaned.rfind("]")
        data = None
        if start != -1 and end > start:
            try:
                data = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                data = None
        if data is None:
            # 实在解析不了，按行降级拆分（只保留标题）
            lines = [ln.strip().lstrip("-*0123456789. ").strip()
                     for ln in cleaned.splitlines()]
            lines = [ln for ln in lines if ln]
            if not lines:
                raise LLMError("无法从模型输出中解析出任务")
            return [{"title": ln, "date": None, "time": None,
                     "remind": None, "type": None} for ln in lines]

    if isinstance(data, str):
        data = [data]
    if isinstance(data, dict):
        for key in ("tasks", "todos", "items", "list"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise LLMError("模型输出的 JSON 不是数组")

    tasks = []
    for item in data:
        if isinstance(item, str):
            title = item.strip()
            tasks.append({"title": title, "date": None, "time": None,
                          "remind": None, "type": None})
            continue
        if not isinstance(item, dict):
            title = str(item).strip()
            if title:
                tasks.append({"title": title, "date": None, "time": None,
                              "remind": None, "type": None})
            continue

        title = str(item.get("title") or item.get("summary") or "").strip()
        if not title:
            continue
        tasks.append({
            "title": title,
            "date": _norm_date(item.get("date")),
            "time": _norm_time(item.get("time")),
            "remind": _norm_time(item.get("remind")),
            "type": _norm_type(item.get("type")),
        })
    return tasks


def _norm_date(value):
    """规整日期为 YYYY-MM-DD，无法识别返回 None"""
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m-%d", "%m/%d"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt in ("%m-%d", "%m/%d"):
            parsed = parsed.replace(year=datetime.now().year)
        return parsed.strftime("%Y-%m-%d")
    return None


def _norm_time(value):
    """规整时间为 HH:MM，无法识别返回 None"""
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%H:%M", "%H:%M:%S", "%H点%M分", "%H点"):
        try:
            return datetime.strptime(text, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return None


VALID_TYPES = ("work", "study", "life", "health", "meeting", "other")


def _norm_type(value):
    """规整任务类型，非法值归为 other"""
    if not value:
        return None
    text = str(value).strip().lower()
    return text if text in VALID_TYPES else "other"


def generate_tasks(user_text: str, config: dict, env_path: Path) -> list[dict]:
    """把一段自然语言转成带日程信息的任务列表"""
    text = (user_text or "").strip()
    if not text:
        raise LLMError("内容为空，没什么可生成的。")

    model = str(config.get("llm_model") or "").strip()
    if not model:
        raise LLMError("未配置 llm_model，请先执行：td cfg set llm_model <模型名>")

    url = build_url(config)
    apikey = resolve_api_key(config, env_path)
    try:
        timeout = int(config.get("llm_timeout") or 60)
    except (TypeError, ValueError):
        timeout = 60

    headers = {"Content-Type": "application/json"}
    if apikey:
        headers["Authorization"] = f"Bearer {apikey}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": text},
        ],
        "temperature": 0.2,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.Timeout as exc:
        raise LLMError(f"请求超时（{timeout}s），可调大 llm_timeout") from exc
    except requests.RequestException as exc:
        raise LLMError(f"无法连接接口：{exc}（检查 llm_url 与网络）") from exc

    if resp.status_code != 200:
        hint = ""
        if resp.status_code in (401, 403):
            hint = "（apikey 无效或未配置，检查 .env 里的 TD_LLM_APIKEY）"
        elif resp.status_code == 404:
            hint = "（接口地址可能不对，检查 llm_url）"
        raise LLMError(f"请求失败 HTTP {resp.status_code}{hint} {resp.text[:300]}".strip())

    try:
        data = resp.json()
    except ValueError as exc:
        raise LLMError("响应不是合法 JSON") from exc

    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise LLMError(f"接口返回错误：{msg}")

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("响应结构异常：缺少 choices[0].message.content") from exc

    return extract_tasks(content)
