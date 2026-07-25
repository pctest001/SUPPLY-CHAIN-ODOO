# -*- coding: utf-8 -*-
"""
实战练习：把 4 天笔记串成一条主线
  Day03: HTTP 基础 (GET/POST/状态码/Header/Body)
  Day04: Session 会话管理
  Day05: 超时与异常处理

测试站点:
  https://httpbingo.org   (httpbin 的维护继任版, GET/POST/delay/status 都稳)
  https://postman-echo.com (Session/cookie 演示用, /cookie/add + /cookies 稳)

用法:
  C:/Python314/python.exe day04_practice_http_session_timeout.py

注意(Windows 实战坑):
  控制台是 GBK 编码, 不要 print 表情符号(如 ✋), 会 UnicodeEncodeError 崩脚本。
  本脚本全程用纯 ASCII 提示符。
"""

import requests
from requests.exceptions import Timeout, ConnectionError, HTTPError, RequestException

BASE = "https://httpbingo.org"
COOKIE_BASE = "https://postman-echo.com"


# ============ 第 1 部分：HTTP 基础 GET ============
def demo_http_basic():
    print("\n" + "=" * 60)
    print("[第1部分] HTTP 基础: GET + 状态码 + Header + Body")
    print("=" * 60)

    r = requests.get(
        BASE + "/get",
        params={"q": "猫", "page": 1},          # GET 参数 → URL 后面 ?q=猫&page=1
        headers={"User-Agent": "MyPracticeBot/1.0"},  # 自定义请求头
        timeout=(3, 10),
    )
    print("状态码:", r.status_code, "| r.ok =", r.ok)
    print("Content-Type:", r.headers.get("Content-Type"))
    data = r.json()                             # 响应体当 JSON 解析
    print("服务器收到的参数:", data["args"])
    print("服务器看到的 User-Agent:", data["headers"]["User-Agent"])


# ============ 第 2 部分：HTTP 基础 POST + Body ============
def demo_http_post():
    print("\n" + "=" * 60)
    print("[第2部分] HTTP 基础: POST + 请求体 Body")
    print("=" * 60)

    r = requests.post(
        BASE + "/post",
        json={"user": "小明", "action": "下单"},
        timeout=(3, 10),
    )
    print("状态码:", r.status_code)
    body = r.json()
    print("服务器收到的 JSON Body:", body["json"])


# ============ 第 3 部分：Session 会话（自动带 cookie）============
def demo_session():
    print("\n" + "=" * 60)
    print("[第3部分] Session: 登录后自动保持会话")
    print("=" * 60)

    s = requests.Session()
    # postman-echo 的 /cookie/add 会下发一个自定义 cookie
    s.get(COOKIE_BASE + "/cookie/add?session_id=abc123", timeout=(3, 10))
    print("Session 拿到的 cookie:", dict(s.cookies))

    # 再次请求 /cookies，Session 自动带上刚才的 cookie
    r = s.get(COOKIE_BASE + "/cookies", timeout=(3, 10))
    print("服务器看到的 cookie:", r.json()["cookies"])


# ============ 第 4 部分：超时与异常（故意触发）============
def safe_request(url, retries=2):
    for i in range(1, retries + 1):
        try:
            print(f"  第{i}次请求: {url}")
            resp = requests.get(url, timeout=(2, 3))
            resp.raise_for_status()            # 4xx/5xx → 抛 HTTPError
            return resp
        except Timeout:
            print("    [超时] 读取超时")
        except ConnectionError:
            print("    [连接错误] DNS/拒绝连接")
        except HTTPError as e:
            print(f"    [HTTP错误] 服务器回错: {e}")
            break                              # 4xx 重试也没用，直接放弃
        except RequestException as e:
            print(f"    [其他请求错误] {e}")
    return None


def demo_timeout_and_exception():
    print("\n" + "=" * 60)
    print("[第4部分] 超时与异常: 故意触发看效果")
    print("=" * 60)

    # 4.1 触发读取超时: /delay/5 故意 5 秒后才响应，但我们只读 3 秒
    print("(a) 触发读取超时 (delay/5, 读超时=3秒):")
    safe_request(BASE + "/delay/5")

    # 4.2 触发 404 → HTTPError
    print("\n(b) 触发 404 状态码:")
    safe_request(BASE + "/status/404")

    # 4.3 正常请求 (对照)
    print("\n(c) 正常请求 (对照):")
    r = safe_request(BASE + "/get")
    if r:
        print("    [成功] 拿到数据, 状态码:", r.status_code)


# ============ 综合：Session + 超时 + 异常 合体 ============
def demo_combo():
    print("\n" + "=" * 60)
    print("[综合] Session + 超时 + 异常 合体模板")
    print("=" * 60)

    s = requests.Session()
    s.headers.update({"User-Agent": "MyPracticeBot/1.0"})
    try:
        # 登录(模拟)
        r = s.post(BASE + "/post",
                   json={"u": "小明", "p": "123"},
                   timeout=(3, 10))
        r.raise_for_status()
        print("登录请求状态码:", r.status_code)

        # 用同一个 Session 继续访问(自动带 cookie/header)
        r2 = s.get(BASE + "/headers", timeout=(3, 10))
        r2.raise_for_status()
        print("带 UA 的后续请求, 服务器看到:", r2.json()["headers"]["User-Agent"])
    except Timeout:
        print("[超时]")
    except RequestException as e:
        print("[请求出错]", e)


if __name__ == "__main__":
    print("#" * 60)
    print("# 实战练习: HTTP 基础 + Session + 超时异常")
    print("#" * 60)
    # 每个 demo 单独包异常：某个测试站抽风也不影响整体跑完
    for name, fn in [("HTTP基础", demo_http_basic),
                     ("HTTP-POST", demo_http_post),
                     ("Session", demo_session),
                     ("超时异常", demo_timeout_and_exception),
                     ("综合", demo_combo)]:
        try:
            fn()
        except RequestException as e:
            print(f"[警告] [{name}] 网络请求出错(已捕获, 继续): {e}")
    print("\n[完成] 全部演示结束。回顾 4 天笔记：")
    print("   Day03 HTTP基础 | Day04 Session | Day05 超时异常")
