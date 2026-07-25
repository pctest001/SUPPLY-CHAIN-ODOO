import urllib.request, json, sys

BASE = "http://localhost:8069"

def rpc(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read().decode("utf-8", "ignore"))

def authenticate(login, password):
    p = {"jsonrpc": "2.0", "method": "call",
         "params": {"db": "supplychain", "login": login, "password": password}}
    r = rpc(BASE + "/web/session/authenticate", p)
    return r.get("result", {})

# 1) WRONG password -> must be rejected (proves the check is real, not bypassed)
bad = authenticate("admin@example.com", "wrong-pass-123")
print("wrong password -> uid:", bad.get("uid"))
assert bad.get("uid") in (False, None), "SECURITY BUG: wrong password was accepted!"

# 2) CORRECT password -> must authenticate
ok = authenticate("admin@example.com", "admin")
uid = ok.get("uid")
print("correct password -> uid:", uid)
if not uid:
    print("RESULT: LOGIN FAILED ->", ok)
    sys.exit(1)
print("RESULT: LOGIN OK (reproducible admin password works)")

# 3) confirm session identity
info = rpc(BASE + "/web/session/get_session_info",
           {"jsonrpc": "2.0", "method": "call", "params": {}})
res = info.get("result", {})
print("session username:", res.get("username"), "| uid:", res.get("uid"))
