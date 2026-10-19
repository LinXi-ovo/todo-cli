"""对 llm.py 做端到端自测：覆盖三种接口格式、.env 解析、异常与降级解析。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm
import mock_llm

PORT = 18080
BASE = f"http://127.0.0.1:{PORT}"

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("[PASS] " if cond else "[FAIL] ") + name + (f"  {detail}" if detail and not cond else ""))


def run():
    srv = mock_llm.serve(PORT)
    env_path = Path(__file__).resolve().parent / ".env_test"

    # ---------- 1. .env 解析 ----------
    env_path.write_text(
        "# 注释行\n"
        "\n"
        "TD_LLM_APIKEY=sk-from-env-file\n"
        "QUOTED=\"value with spaces\"\n"
        "SINGLE='another'\n",
        encoding="utf-8",
    )
    env = llm.load_env(env_path)
    check(".env 解析 apikey", env.get("TD_LLM_APIKEY") == "sk-from-env-file", env)
    check(".env 忽略注释与空行", len(env) == 3, repr(env))
    check(".env 去双引号", env.get("QUOTED") == "value with spaces", env.get("QUOTED"))
    check(".env 去单引号", env.get("SINGLE") == "another", env.get("SINGLE"))

    # ---------- 2. apikey 优先级 ----------
    cfg = {"llm_apikey": ""}
    check("apikey 从 .env 读", llm.resolve_api_key(cfg, env) == "sk-from-env-file")

    cfg2 = {"llm_apikey": "env:QUOTED"}
    check("apikey env:间接引用", llm.resolve_api_key(cfg2, env) == "value with spaces",
          llm.resolve_api_key(cfg2, env))

    cfg3 = {"llm_apikey": "sk-direct"}
    check("apikey 直接写在配置", llm.resolve_api_key(cfg3, {}) == "sk-direct")

    # ---------- 3. URL 拼接 ----------
    check("openai 补默认路径",
          llm.build_url({"llm_url": "https://api.deepseek.com", "llm_api_style": "openai"})
          == "https://api.deepseek.com/v1/chat/completions",
          llm.build_url({"llm_url": "https://api.deepseek.com", "llm_api_style": "openai"}))

    check("anthropic 补默认路径",
          llm.build_url({"llm_url": "https://api.anthropic.com", "llm_api_style": "anthropic"})
          == "https://api.anthropic.com/v1/messages")

    check("已给完整地址不重复拼接",
          llm.build_url({"llm_url": "https://x.com/v1/chat/completions", "llm_api_style": "openai"})
          == "https://x.com/v1/chat/completions")

    check("custom 原样使用",
          llm.build_url({"llm_url": "https://x.com/any/path", "llm_api_style": "custom"})
          == "https://x.com/any/path")

    try:
        llm.build_url({"llm_url": "", "llm_api_style": "openai"})
        check("空 url 抛错", False)
    except llm.LLMError:
        check("空 url 抛错", True)

    try:
        llm.build_url({"llm_url": "https://x.com", "llm_api_style": "bogus"})
        check("非法 api_style 抛错", False)
    except llm.LLMError:
        check("非法 api_style 抛错", True)

    # ---------- 4. OpenAI 格式端到端 ----------
    mock_llm.RECEIVED.clear()
    titles = llm.generate_titles(
        "明天交色彩作业，还要买牛奶", 
        {"llm_url": BASE, "llm_model": "test-model", "llm_api_style": "openai",
         "llm_apikey": "", "llm_timeout": 10},
        env_path,
    )
    check("openai 返回两条任务", titles == ["明天交色彩作业", "买牛奶"], titles)
    rec = mock_llm.RECEIVED[-1]
    check("openai 走 chat/completions", rec["path"] == "/v1/chat/completions", rec["path"])
    check("openai 用 Bearer 鉴权", rec["auth"] == "Bearer sk-from-env-file", rec["auth"])
    check("openai 请求含 model", rec["body"].get("model") == "test-model")
    check("openai 请求含 messages", isinstance(rec["body"].get("messages"), list))

    # ---------- 5. Anthropic 格式端到端 ----------
    mock_llm.RECEIVED.clear()
    titles = llm.generate_titles(
        "明天交色彩作业，还要买牛奶",
        {"llm_url": BASE, "llm_model": "claude-x", "llm_api_style": "anthropic",
         "llm_apikey": "", "llm_timeout": 10},
        env_path,
    )
    check("anthropic 返回两条任务", titles == ["明天交色彩作业", "买牛奶"], titles)
    rec = mock_llm.RECEIVED[-1]
    check("anthropic 走 /v1/messages", rec["path"] == "/v1/messages", rec["path"])
    check("anthropic 用 x-api-key", rec["xkey"] == "sk-from-env-file", rec["xkey"])
    check("anthropic 带版本头", rec["version"] == "2023-06-01", rec["version"])
    check("anthropic 不接受 system 角色混入 messages",
          all(m["role"] != "system" for m in rec["body"]["messages"]),
          rec["body"]["messages"])

    # ---------- 6. custom 格式 ----------
    mock_llm.RECEIVED.clear()
    titles = llm.generate_titles(
        "测试",
        {"llm_url": f"{BASE}/v1/chat/completions", "llm_model": "m",
         "llm_api_style": "custom", "llm_apikey": "", "llm_timeout": 10},
        env_path,
    )
    check("custom 走指定路径", mock_llm.RECEIVED[-1]["path"] == "/v1/chat/completions")

    # ---------- 7. 输出解析容错 ----------
    check("解析纯 JSON 数组", llm.extract_titles('["a","b"]') == ["a", "b"])
    check("解析代码块包裹", llm.extract_titles('```json\n["a"]\n```') == ["a"])
    check("解析带前后废话", llm.extract_titles('好的，结果如下：["a","b"] 完毕') == ["a", "b"])
    check("解析 {\"tasks\": []} 结构", llm.extract_titles('{"tasks":["a"]}') == ["a"])
    check("解析对象数组", llm.extract_titles('[{"title":"a"}]') == ["a"])
    check("解析纯字符串", llm.extract_titles('"单独一条"') == ["单独一条"])
    check("解析降级为按行拆分", llm.extract_titles("- 任务一\n- 任务二") == ["任务一", "任务二"])

    try:
        llm.extract_titles("")
        check("空输出抛错", False)
    except llm.LLMError:
        check("空输出抛错", True)

    # ---------- 8. 错误响应 ----------
    mock_llm.RECEIVED.clear()
    try:
        llm.generate_titles("x", {"llm_url": "http://127.0.0.1:9", "llm_model": "m",
                                  "llm_api_style": "openai", "llm_apikey": "",
                                  "llm_timeout": 3}, env_path)
        check("连接失败抛错", False)
    except llm.LLMError as e:
        check("连接失败抛错", "无法连接" in str(e), str(e))

    # 缺 model
    try:
        llm.generate_titles("x", {"llm_url": BASE, "llm_model": "",
                                  "llm_api_style": "openai"}, env_path)
        check("缺 model 抛错", False)
    except llm.LLMError as e:
        check("缺 model 抛错", "llm_model" in str(e), str(e))

    env_path.unlink(missing_ok=True)
    srv.shutdown()

    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n===== {passed}/{total} 通过 =====")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(run())
