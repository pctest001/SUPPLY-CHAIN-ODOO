import urllib.request, urllib.parse, http.cookiejar, re, sys

BASE = "http://localhost:8069"
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

html = op.open(urllib.request.Request(BASE + "/web/login"), timeout=30).read().decode("utf-8", "ignore")

# Odoo embeds csrf token in the login form; grab it (handle both attribute orders)
m = re.search(r'name="csrf_token"[^>]*value="([^"]*)"', html) \
    or re.search(r'value="([^"]*)"[^>]*name="csrf_token"', html)
csrf = m.group(1) if m else ""
print("csrf found:", bool(csrf))

# Build the same POST the browser login form sends
data = {
    "login": "admin@example.com",
    "password": "admin",
    "db": "supplychain",
}
if csrf:
    data["csrf_token"] = csrf
body = urllib.parse.urlencode(data).encode()
req = urllib.request.Request(BASE + "/web/login", data=body, method="POST")
try:
    resp = op.open(req, timeout=30)
    final = resp.geturl()
    txt = resp.read().decode("utf-8", "ignore")
    print("final url:", final)
    if "Wrong login/password" in txt:
        print("RESULT: BROWSER LOGIN FAILED")
        sys.exit(1)
    print("RESULT: BROWSER LOGIN OK (redirected to:", final, ")")
except urllib.error.HTTPError as e:
    print("POST -> HTTP", e.code, "location:", e.headers.get("Location"))
    if e.code in (301, 302, 303):
        print("RESULT: BROWSER LOGIN OK (redirect = success)")
    else:
        print("RESULT: BROWSER LOGIN FAILED")
        sys.exit(1)
