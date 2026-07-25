import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

# ---------- 1) 本地起一个返回 JSON 的小服务（模拟后端接口）----------
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = {
            "city": "北京",
            "weather": "晴",
            "temperature": 26,
            "humidity": 40,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # 安静日志
        pass


def run_server():
    server = HTTPServer(("127.0.0.1", 8000), Handler)
    server.serve_forever()


# 后台线程启动服务
t = threading.Thread(target=run_server, daemon=True)
t.start()

# ---------- 2) 用 requests 发请求 ----------
r = requests.get("http://127.0.0.1:8000/", timeout=5)
print("状态码:", r.status_code)
print("响应头 Content-Type:", r.headers.get("Content-Type"))

# ---------- 3) 解析 JSON ----------
data = r.json()  # 等价于 json.loads(r.text)
print("解析后的数据类型:", type(data))
print("城市:", data["city"])
print("天气:", data["weather"])
print("温度:", data["temperature"], "℃")
print("湿度:", data["humidity"], "%")

# 直接把整个 dict 漂亮打印出来
print("\n完整 JSON 内容:")
print(json.dumps(data, ensure_ascii=False, indent=2))
