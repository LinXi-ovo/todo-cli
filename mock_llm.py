"""本地 mock LLM 服务，用于验证 td @ 的三条接口路径，不消耗真实额度。"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

RECEIVED = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        RECEIVED.append({
            "path": self.path,
            "auth": self.headers.get("Authorization"),
            "xkey": self.headers.get("x-api-key"),
            "version": self.headers.get("anthropic-version"),
            "body": body,
        })

        # 模拟模型输出：带代码块的 JSON
        content = '```json\n["明天交色彩作业", "买牛奶"]\n```'

        if self.path.endswith("/messages"):
            payload = {
                "content": [{"type": "text", "text": content}],
                "model": body.get("model", "unknown"),
            }
        else:
            payload = {
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "model": body.get("model", "unknown"),
            }

        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(port=18080):
    srv = HTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


if __name__ == "__main__":
    import sys as _sys
    import time as _time

    _port = int(_sys.argv[1]) if len(_sys.argv) > 1 else 18080
    _srv = HTTPServer(("127.0.0.1", _port), Handler)
    print(f"mock LLM 已启动 http://127.0.0.1:{_port}", flush=True)
    try:
        _srv.serve_forever()
    except KeyboardInterrupt:
        pass
