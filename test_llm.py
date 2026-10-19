"""llm.py 自测：覆盖 URL 拼接、apikey 解析、输出解析、端到端调用。"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm

PORT = 18081
BASE = f"http://127.0.0.1:{PORT}"
RECEIVED = []
RESULTS = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        RECEIVED.append({"path": self.path,
                         "auth": self.headers.get("Authorization"),
                         "body": body})
        payload = {"choices": [{"message": {"content":
                   '```json\n["明天交色彩作业", "买牛奶"]\n```'}}]}
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print(("[PASS] " if cond else "[FAIL] ") + name + (f"  {detail}" if detail and not cond else ""))


def run():
    srv = HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    env_path = Path(__file__).resolve().parent / ".env_test"
    env_path.write_text("TD_LLM_APIKEY=sk-from-env\n", encoding="utf-8")

    # URL 拼接
    check("补 /v1/chat/completions",
          llm.build_url({"llm_url": "https://api.deepseek.com"})
          == "https://api.deepseek.com/v1/chat/completions")
    check("已是完整地址不重复拼",
          llm.build_url({"llm_url": "https://x.com/v1/chat/completions"})
          == "https://x.com/v1/chat/completions")
    try:
        llm.build_url({"llm_url": ""})
        check("空 url 抛错", False)
    except llm.LLMError:
        check("空 url 抛错", True)

    # apikey 解析
    check("从 .env 读 apikey",
          llm.resolve_api_key({"llm_apikey": ""}, env_path) == "sk-from-env")
    check("配置显式值优先",
          llm.resolve_api_key({"llm_apikey": "sk-direct"}, env_path) == "sk-direct")

    # 输出解析
    check("纯数组", llm.extract_titles('["a","b"]') == ["a", "b"])
    check("代码块包裹", llm.extract_titles('```json\n["a"]\n```') == ["a"])
    check("夹带废话", llm.extract_titles('结果：["a"] 完毕') == ["a"])
    check("对象数组", llm.extract_titles('[{"title":"a"}]') == ["a"])
    check("按行降级", llm.extract_titles("- 任务一\n- 任务二") == ["任务一", "任务二"])
    try:
        llm.extract_titles("")
        check("空输出抛错", False)
    except llm.LLMError:
        check("空输出抛错", True)

    # 端到端
    cfg = {"llm_url": BASE, "llm_model": "test-model", "llm_apikey": "",
           "llm_timeout": 10}
    titles = llm.generate_titles("明天交作业买牛奶", cfg, env_path)
    check("端到端返回两条", titles == ["明天交色彩作业", "买牛奶"], titles)
    rec = RECEIVED[-1]
    check("请求路径正确", rec["path"] == "/v1/chat/completions", rec["path"])
    check("Bearer 鉴权", rec["auth"] == "Bearer sk-from-env", rec["auth"])
    check("请求含 model", rec["body"].get("model") == "test-model")
    check("请求含 system 角色",
          rec["body"]["messages"][0]["role"] == "system")

    try:
        llm.generate_titles("x", {"llm_url": BASE, "llm_model": ""}, env_path)
        check("缺 model 抛错", False)
    except llm.LLMError as e:
        check("缺 model 抛错", "llm_model" in str(e))

    env_path.unlink(missing_ok=True)
    srv.shutdown()
    print(f"\n===== {sum(RESULTS)}/{len(RESULTS)} 通过 =====")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(run())
