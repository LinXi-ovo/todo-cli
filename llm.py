"""LLM 任务生成模块。

供 td.py 以 `import llm` 方式调用，负责：
  1. 读取 .env 与配置里的接口参数
  2. 按配置的接口格式（openai / anthropic / custom）发起请求
  3. 把模型返回的 JSON 解析成任务标题列表

不依赖第三方库，只用标准库 urllib，避免给 td 引入额外安装负担。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

# 支持的接口格式
API_OPENAI = "openai"          # POST {url}，OpenAI /v1/chat/completions 风格
API_ANTHROPIC = "anthropic"    # POST {url}，Anthropic /v1/messages 风格
API_CUSTOM = "custom"          # POST {url}，完全由用户给出完整地址，走 OpenAI 结构

VALID_API_STYLES = (API_OPENAI, API_ANTHROPIC, API_CUSTOM)

# 各格式的默认路径拼接（url 只给 base 时使用）
DEFAULT_PATHS = {
    API_OPENAI: "/v1/chat/completions",
    API_ANTHROPIC: "/v1/messages",
    API_CUSTOM: "",  # custom 认为用户已给完整地址
}


class LLMError(Exception):
    """调用大模型过程中的可预期错误"""


# ---------- .env 解析 ----------
def load_env(env_path: Path) -> dict:
    """读取 .env 文件为字典；支持 # 注释、空行、key=value、引号包裹"""
    env = {}
    if not env_path.exists():
        return env
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise LLMError(f"无法读取 .env：{exc}") from exc

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        # 去掉成对的引号
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        env[key.strip()] = value
    return env


def resolve_api_key(config: dict, env: dict) -> str:
    """按优先级取 apikey。

    1. 配置里显式写的值（含 "env:NAME" 间接引用）
    2. 进程环境变量 TD_LLM_APIKEY / TD_API_KEY
    3. .env 文件里的 TD_LLM_APIKEY / TD_API_KEY
    """
    raw = str(config.get("llm_apikey") or "").strip()

    # 配置显式写了值，就以它为准
    if raw:
        if raw.lower().startswith("env:"):
            name = raw[4:].strip()
            return os.environ.get(name) or env.get(name) or ""
        return raw

    # 没写则回落到环境变量，再回落到 .env
    for key in ("TD_LLM_APIKEY", "TD_API_KEY"):
        if os.environ.get(key):
            return os.environ[key]
    for key in ("TD_LLM_APIKEY", "TD_API_KEY"):
        if env.get(key):
            return env[key]
    return ""


# ---------- 提示词 ----------
SYSTEM_PROMPT = (
    "你是一个待办事项提取助手。用户会给出一段自然语言描述，"
    "你要把它拆解成若干条独立、简短、可执行的待办任务。\n"
    "要求：\n"
    "1. 只输出 JSON 数组，不要任何解释文字、不要 markdown 代码块。\n"
    "2. 数组每个元素是一个字符串，代表一条任务标题。\n"
    "3. 标题保留用户提到的时间、地点等关键信息，但保持简洁。\n"
    '4. 如果描述里只有一件事，就返回只含一个元素的数组。\n'
    '示例输出：["明天交色彩作业", "买牛奶"]'
)


def build_url(config: dict) -> str:
    """根据接口格式与配置拼出最终请求地址"""
    url = str(config.get("llm_url") or "").strip()
    if not url:
        raise LLMError("未配置 llm_url，请先执行：td cfg set llm_url <地址>")

    style = str(config.get("llm_api_style") or API_OPENAI).strip().lower()
    if style not in VALID_API_STYLES:
        raise LLMError(
            f"llm_api_style 无效：{style}，可选 {', '.join(VALID_API_STYLES)}"
        )

    # 已经像完整接口地址就直接用；否则按格式补默认路径
    if style == API_CUSTOM or url.rstrip("/").endswith(("chat/completions", "/messages")):
        return url
    return url.rstrip("/") + DEFAULT_PATHS[style]


# ---------- 请求构造 ----------
def build_request(url: str, config: dict, apikey: str, user_text: str):
    """按接口格式构造 Request 对象"""
    style = str(config.get("llm_api_style") or API_OPENAI).strip().lower()
    model = str(config.get("llm_model") or "").strip()
    if not model:
        raise LLMError("未配置 llm_model，请先执行：td cfg set llm_model <模型名>")

    try:
        timeout = int(config.get("llm_timeout") or 60)
    except (TypeError, ValueError):
        timeout = 60

    if style == API_ANTHROPIC:
        payload = {
            "model": model,
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_text}],
        }
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if apikey:
            headers["x-api-key"] = apikey
    else:  # openai / custom 共用 OpenAI 结构
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.2,
        }
        headers = {"Content-Type": "application/json"}
        if apikey:
            headers["Authorization"] = f"Bearer {apikey}"

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    return req, timeout


def parse_response(raw: bytes, style: str) -> str:
    """从响应体里取出模型输出的文本"""
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LLMError(f"响应不是合法 JSON：{exc}") from exc

    if isinstance(obj, dict) and obj.get("error"):
        err = obj["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise LLMError(f"接口返回错误：{msg}")

    if style == API_ANTHROPIC:
        content = obj.get("content")
        if isinstance(content, list) and content:
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block.get("text", "")
            return content[0].get("text", "") if isinstance(content[0], dict) else ""
        raise LLMError("响应结构异常：缺少 content 字段")

    # OpenAI 风格
    choices = obj.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") or {}
        return message.get("content", "")
    raise LLMError("响应结构异常：缺少 choices 字段")


# ---------- JSON 文本解析 ----------
def extract_titles(text: str) -> list[str]:
    """从模型输出里抽出任务标题列表，容忍代码块包裹和多余说明"""
    if not text or not text.strip():
        raise LLMError("模型返回了空内容")

    cleaned = text.strip()

    # 去掉 ```json ... ``` 包裹
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    data = None
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # 退一步：截取第一个 [ 到最后一个 ] 之间的内容
        start, end = cleaned.find("["), cleaned.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                data = None

    if data is None:
        # 实在解析不了，把非空行当作任务列表
        fallback = [
            ln.strip().lstrip("-*0123456789. ").strip()
            for ln in cleaned.splitlines()
            if ln.strip()
        ]
        fallback = [t for t in fallback if t]
        if not fallback:
            raise LLMError("无法从模型输出中解析出任务")
        return fallback

    if isinstance(data, str):
        return [data.strip()] if data.strip() else []
    if isinstance(data, dict):
        # 兼容 {"tasks": [...]} 这种
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


# ---------- 对外主函数 ----------
def generate_titles(user_text: str, config: dict, env_path: Path) -> list[str]:
    """把一段自然语言转成任务标题列表。

    config 需要包含：llm_url / llm_model / llm_api_style / llm_apikey / llm_timeout
    """
    text = (user_text or "").strip()
    if not text:
        raise LLMError("内容为空，没什么可生成的。")

    env = load_env(env_path)
    apikey = resolve_api_key(config, env)
    url = build_url(config)
    req, timeout = build_request(url, config, apikey, text)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            body = exc.read().decode("utf-8", "replace")
            detail = body[:300]
        except Exception:
            pass
        hint = ""
        if exc.code in (401, 403):
            hint = "（apikey 无效或未配置，检查 .env 里的 TD_LLM_APIKEY）"
        elif exc.code == 404:
            hint = "（接口地址可能不对，检查 llm_url 与 llm_api_style）"
        raise LLMError(f"请求失败 HTTP {exc.code}{hint} {detail}".strip()) from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"无法连接接口：{exc.reason}（检查 llm_url 与网络）") from exc
    except TimeoutError as exc:
        raise LLMError(f"请求超时（{timeout}s），可在配置里调大 llm_timeout") from exc

    style = str(config.get("llm_api_style") or API_OPENAI).strip().lower()
    content = parse_response(raw, style)
    return extract_titles(content)


def test_connection(config: dict, env_path: Path) -> str:
    """连通性自检：发一条极短请求，返回模型原始响应文本"""
    env = load_env(env_path)
    apikey = resolve_api_key(config, env)
    url = build_url(config)
    req, timeout = build_request(url, config, apikey, "回复两个字：正常")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300] if exc.fp else ""
        raise LLMError(f"HTTP {exc.code}：{detail}".strip()) from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"无法连接：{exc.reason}") from exc
    style = str(config.get("llm_api_style") or API_OPENAI).strip().lower()
    return parse_response(raw, style)
