#!/usr/bin/env python3
"""
swap-subdomain.py — Change the subdomain prefix for Open WebUI
Example: chat.forexrobots.co.za → fx.forexrobots.co.za

Run as root on the VPS:
    python3 swap-subdomain.py
    python3 swap-subdomain.py --from chat --to fx --domain forexrobots.co.za --user forexrobotsco
"""

import argparse, json, os, subprocess, sys
from pathlib import Path

CPANEL_USER  = "forexrobotsco"
ROOT_DOMAIN  = "forexrobots.co.za"
WEBUI_PORT   = 3000
USERDATA     = Path("/etc/apache2/conf.d/userdata")

PROXY_CONF = f"""\
<IfModule mod_proxy.c>
  ProxyRequests Off
  ProxyPreserveHost On
  ProxyPass / http://127.0.0.1:{WEBUI_PORT}/
  ProxyPassReverse / http://127.0.0.1:{WEBUI_PORT}/
  RewriteEngine On
  RewriteCond %{{HTTP:Upgrade}} websocket [NC]
  RewriteCond %{{HTTP:Connection}} upgrade [NC]
  RewriteRule ^/?(.*) ws://127.0.0.1:{WEBUI_PORT}/$1 [P,L]
</IfModule>
"""

def run(cmd):
    return subprocess.run(cmd, shell=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def ok(m):   print(f"  \033[92m[OK]\033[0m  {m}")
def err(m):  print(f"  \033[91m[ERR]\033[0m {m}")
def info(m): print(f"  \033[1m[..]\033[0m  {m}")

# ─────────────────────────────────────────────────────────────────────────────

def create_subdomain(prefix, root, user):
    full = f"{prefix}.{root}"
    info(f"Creating subdomain {full} in cPanel...")
    r = run(f"whmapi1 cpanel user={user} cpanel_jsonapi_module=SubDomain "
            f"cpanel_jsonapi_func=addsubdomain domain={prefix} rootdomain={root} dir={full}")
    try:
        d = json.loads(r.stdout)
        reason = d.get('cpanelresult', {}).get('event', {}).get('reason', '')
        if 'exist' in reason.lower():
            ok(f"{full} already exists")
        else:
            ok(f"{full} created")
    except Exception:
        ok(f"Done (check cPanel if {full} is missing)")

def write_proxy(prefix, root, user):
    full = f"{prefix}.{root}"
    for proto in ('std', 'ssl'):
        path = USERDATA / proto / "2_4" / user / full
        path.mkdir(parents=True, exist_ok=True)
        (path / "proxy.conf").write_text(PROXY_CONF)
        ok(f"Proxy written → {path}/proxy.conf")

def remove_proxy(prefix, root, user):
    full = f"{prefix}.{root}"
    removed = False
    for proto in ('std', 'ssl'):
        f = USERDATA / proto / "2_4" / user / full / "proxy.conf"
        if f.exists():
            f.unlink()
            ok(f"Removed → {f}")
            removed = True
    if not removed:
        info(f"No proxy found for {full} (nothing to remove)")

def reload_apache():
    info("Rebuilding Apache config...")
    run("/scripts/rebuildhttpdconf")
    r = run("apachectl configtest")
    if "Syntax OK" in r.stderr + r.stdout:
        ok("Syntax OK")
        run("systemctl reload httpd")
        ok("Apache reloaded")
    else:
        err("Apache config error — run: apachectl configtest")
        sys.exit(1)

def test_url(prefix, root):
    full = f"{prefix}.{root}"
    r = run(f"curl -sk -o /dev/null -w '%{{http_code}}' https://{full}/health")
    code = r.stdout.strip()
    if code == "200":
        ok(f"https://{full} → 200 LIVE")
    else:
        r2 = run(f"dig +short {full}")
        dns = r2.stdout.strip() or "no DNS record"
        print(f"\n  \033[93m[WARN]\033[0m https://{full} → {code}")
        print(f"         DNS: {dns}")
        if not r2.stdout.strip():
            print(f"\n  Add this in Cloudflare DNS:")
            print(f"    Type: A  |  Name: {prefix}  |  IPv4: {get_ip()}  |  Proxy: ON")

def get_ip():
    r = run("curl -s --max-time 5 ifconfig.me")
    return r.stdout.strip() or "YOUR_SERVER_IP"

# ─────────────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--from",   dest="old", help="Old subdomain prefix  e.g. chat")
    p.add_argument("--to",     dest="new", help="New subdomain prefix  e.g. fx")
    p.add_argument("--domain", default=ROOT_DOMAIN,  help=f"Root domain (default: {ROOT_DOMAIN})")
    p.add_argument("--user",   default=CPANEL_USER,  help=f"cPanel user (default: {CPANEL_USER})")
    args = p.parse_args()

    if os.geteuid() != 0:
        err("Run as root"); sys.exit(1)

    print("\n\033[1m━━  Open WebUI — Swap Subdomain  ━━\033[0m\n")

    old = args.old or input("  Old prefix (e.g. chat): ").strip()
    new = args.new or input("  New prefix (e.g. fx):   ").strip()

    if not old or not new:
        err("Both prefixes required"); sys.exit(1)
    if old == new:
        err("Old and new are the same"); sys.exit(1)

    root = args.domain
    user = args.user

    print(f"\n  {old}.{root}  →  {new}.{root}\n")
    confirm = input("  Proceed? [y/N]: ").strip().lower()
    if confirm != 'y':
        print("  Cancelled."); sys.exit(0)

    print()
    create_subdomain(new, root, user)   # 1. create new subdomain in cPanel
    write_proxy(new, root, user)        # 2. write proxy for new
    remove_proxy(old, root, user)       # 3. remove proxy from old
    reload_apache()                     # 4. rebuild + reload Apache
    print()
    test_url(new, root)                 # 5. test live

    print(f"\n  \033[1mDone.\033[0m  New URL: https://{new}.{root}")
    print(f"  Direct: http://{get_ip()}:{WEBUI_PORT}\n")

if __name__ == "__main__":
    main()
