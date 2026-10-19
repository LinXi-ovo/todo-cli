"""LLM 任务生成模块（仅 OpenAI 兼容接口）。

供 td.py 以 `import llm` 方式调用，依赖 requests + python-dotenv。
"""

from __future__ import annotations

import json
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

# OpenAI 兼容接口的默认路径（url 只给 base 时补上）
DEFAULT_PATH = "/v1/chat/completions"

SYSTEM_PROMPT = (
    "你是一个待办事项提取助手。把用户给出的自然语言描述拆解成若干条独立、"
    "简短、可执行的待办任务。\n"
    "只输出 JSON 字符串数组，不要解释文字，不要 markdown 代码块。\n"
    "保留时间、地点等关键信息，保持简洁。只有一件事就返回单元素数组。\n"
    '示例：["明天交色彩作业", "买牛奶"]'
)


class LLMError(Exception):
    """调用大模型过程中的可预期错误"""


def build_url(config: dict) -> str:
    """拼出完整请求地址"""
    url = str(config.get("llm_url") or "").strip()
    if not url:
        raise LLMError("未配置 llm_url，请先执行：td cfg set llm_url <地址>")
    if url.rstrip("/").endswith("chat/completions"):
        return url
    return url.rstrip("/") + DEFAULT_PATH


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


def extract_titles(text: str) -> list[str]:
    """从模型输出里抽出任务标题，容忍代码块包裹和多余文字"""
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
            # 实在解析不了，按行降级拆分
            lines = [ln.strip().lstrip("-*0123456789. ").strip()
                     for ln in cleaned.splitlines()]
            lines = [ln for ln in lines if ln]
            if not lines:
                raise LLMError("无法从模型输出中解析出任务")
            return lines

    if isinstance(data, str):
        return [data.strip()] if data.strip() else []
    if isinstance(data, dict):
        for key in ("tasks", "todos", "items", "list"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise LLMError("模型输出的 JSON 不是数组")

    titles = []
    for item in data:
        if isinstance(item, str):
            title = item.strip()
        elif isinstance(item, dict):
            title = str(item.get("title") or item.get("summary") or "").strip()
        else:
            title = str(item).strip()
        if title:
            titles.append(title)
    return titles


def generate_titles(user_text: str, config: dict, env_path: Path) -> list[str]:
    """把一段自然语言转成任务标题列表"""
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
            {"role": "system", "content": SYSTEM_PROMPT},
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

    return extract_titles(content)
