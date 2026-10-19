"""llm.py 与 alarm.py 自测：URL 拼接、apikey、结构化解析、提醒时间计算。"""
import json
import sys
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm
import alarm

PORT = 18082
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
        content = ('```json\n[{"title":"开组会","date":"2026-10-20",'
                   '"time":"15:00","remind":null,"type":"meeting"}]\n```')
        payload = {"choices": [{"message": {"content": content}}]}
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

    # ---- URL ----
    check("补默认路径",
          llm.build_url({"llm_url": "https://api.deepseek.com"})
          == "https://api.deepseek.com/v1/chat/completions")
    check("已含 /v1 不重复拼",
          llm.build_url({"llm_url": "https://x.com/v1"})
          == "https://x.com/v1/chat/completions")
    check("完整地址原样用",
          llm.build_url({"llm_url": "https://x.com/v1/chat/completions"})
          == "https://x.com/v1/chat/completions")
    try:
        llm.build_url({"llm_url": ""})
        check("空 url 抛错", False)
    except llm.LLMError:
        check("空 url 抛错", True)

    # ---- apikey ----
    check("从 .env 读", llm.resolve_api_key({"llm_apikey": ""}, env_path) == "sk-from-env")
    check("配置优先", llm.resolve_api_key({"llm_apikey": "sk-direct"}, env_path) == "sk-direct")

    # ---- 提示词注入当天日期 ----
    prompt = llm.build_system_prompt()
    check("提示词含今天日期", datetime.now().strftime("%Y-%m-%d") in prompt)
    check("提示词要求 type 字段", '"type"' in prompt)

    # ---- 结构化解析 ----
    t = llm.extract_tasks('[{"title":"开组会","date":"2026-10-20","time":"15:00","type":"meeting"}]')
    check("解析出完整字段", t[0]["title"] == "开组会" and t[0]["date"] == "2026-10-20"
          and t[0]["time"] == "15:00" and t[0]["type"] == "meeting", t)

    t = llm.extract_tasks('```json\n[{"title":"吃药","type":"health"}]\n```')
    check("代码块包裹", t[0]["title"] == "吃药", t)

    t = llm.extract_tasks('["纯字符串"]')
    check("字符串降级兼容", t[0]["title"] == "纯字符串" and t[0]["date"] is None, t)

    t = llm.extract_tasks('[{"title":"x","date":"10/20","time":"15点","type":"bogus"}]')
    check("日期补年份", t[0]["date"].endswith("-10-20"), t)
    check("中文时间归一", t[0]["time"] == "15:00", t)
    check("非法类型归 other", t[0]["type"] == "other", t)

    t = llm.extract_tasks('结果如下：[{"title":"a"}] 完毕')
    check("夹带文字", t[0]["title"] == "a", t)

    try:
        llm.extract_tasks("")
        check("空输出抛错", False)
    except llm.LLMError:
        check("空输出抛错", True)

    # ---- 端到端 ----
    cfg = {"llm_url": BASE, "llm_model": "m", "llm_apikey": "", "llm_timeout": 10}
    tasks = llm.generate_tasks("明天下午3点开组会", cfg, env_path)
    check("端到端返回结构化", tasks[0]["type"] == "meeting", tasks)
    rec = RECEIVED[-1]
    check("请求路径正确", rec["path"] == "/v1/chat/completions")
    check("Bearer 鉴权", rec["auth"] == "Bearer sk-from-env")

    # ---- 提醒时间计算 ----
    now = datetime.now()
    task = {"title": "x", "date": now.strftime("%Y-%m-%d"), "time": "15:00"}
    remind = alarm.parse_remind(task, 10)
    check("默认提前 10 分钟", remind.hour == 14 and remind.minute == 50, remind)

    task2 = dict(task, remind="14:00")
    check("remind 字段优先", alarm.parse_remind(task2, 10).strftime("%H:%M") == "14:00")

    check("无日期返回 None", alarm.parse_remind({"title": "x"}, 10) is None)

    # 到点触发
    soon = (now + timedelta(minutes=5)).strftime("%H:%M")
    tasks = [
        {"title": "即将", "done": False, "date": now.strftime("%Y-%m-%d"),
         "time": soon, "type": "work"},
        {"title": "以后", "done": False, "date": (now + timedelta(days=2)).strftime("%Y-%m-%d"),
         "time": "15:00", "type": "life"},
        {"title": "已完成", "done": True, "date": now.strftime("%Y-%m-%d"),
         "time": soon, "type": "life"},
        {"title": "无时间", "done": False, "type": "life"},
    ]
    fired = alarm.due_now(tasks, now, 10)
    check("只触发到点的未完成任务", len(fired) == 1 and fired[0][0]["title"] == "即将",
          [f[0]["title"] for f in fired])

    # 过期太久不补弹
    old = (now - timedelta(hours=3)).strftime("%H:%M")
    stale = [{"title": "老任务", "done": False, "date": now.strftime("%Y-%m-%d"),
              "time": old, "type": "life"}]
    check("过期超 30 分钟不提醒", len(alarm.due_now(stale, now, 10)) == 0)

    env_path.unlink(missing_ok=True)
    srv.shutdown()
    print(f"\n===== {sum(RESULTS)}/{len(RESULTS)} 通过 =====")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(run())
