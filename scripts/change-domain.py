#!/usr/bin/env python3
"""
change-domain.py — Switch Open WebUI to a different domain/subdomain
Run as root on the VPS.

Usage:
    python3 change-domain.py
    python3 change-domain.py --domain chat.example.com --cpanel-user myaccount
    python3 change-domain.py --domain chat.example.com --cpanel-user myaccount --cf-token YOUR_CF_TOKEN
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path


# ── Colours ──────────────────────────────────────────────────────────────────

def green(s):  return f"\033[92m{s}\033[0m"
def red(s):    return f"\033[91m{s}\033[0m"
def yellow(s): return f"\033[93m{s}\033[0m"
def bold(s):   return f"\033[1m{s}\033[0m"

def ok(msg):   print(f"  {green('[OK]')} {msg}")
def err(msg):  print(f"  {red('[ERR]')} {msg}")
def warn(msg): print(f"  {yellow('[WARN]')} {msg}")
def info(msg): print(f"  {bold('[..]')} {msg}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def run(cmd, check=True, capture=False):
    result = subprocess.run(
        cmd, shell=True, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\n{result.stderr or ''}")
    return result


def confirm(prompt):
    return input(f"\n  {yellow('?')} {prompt} [y/N]: ").strip().lower() == 'y'


def whmapi(func, params=None):
    """Call WHM API1 via CLI."""
    cmd = f"whmapi1 {func}"
    if params:
        for k, v in params.items():
            cmd += f" {k}={v}"
    result = run(cmd, capture=True, check=False)
    try:
        return json.loads(result.stdout)
    except Exception:
        return {}


def cpanel_api(user, module, func, params=None):
    """Call cPanel API2 as a specific user via WHM."""
    cmd = f"whmapi1 cpanel user={user} cpanel_jsonapi_module={module} cpanel_jsonapi_func={func}"
    if params:
        for k, v in params.items():
            cmd += f" {k}={v}"
    result = run(cmd, capture=True, check=False)
    try:
        return json.loads(result.stdout)
    except Exception:
        return {}


# ── Cloudflare API ────────────────────────────────────────────────────────────

class CloudflareAPI:
    BASE = "https://api.cloudflare.com/client/v4"

    def __init__(self, token):
        self.token = token

    def _request(self, method, path, data=None):
        url = f"{self.BASE}{path}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(
            url, data=body, method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return json.loads(e.read())

    def get_zone(self, domain):
        """Find Cloudflare zone ID for a root domain."""
        # Try the root domain and parent domains
        parts = domain.split('.')
        for i in range(len(parts) - 1):
            root = '.'.join(parts[i:])
            result = self._request("GET", f"/zones?name={root}&status=active")
            zones = result.get('result', [])
            if zones:
                return zones[0]['id'], root
        return None, None

    def get_record(self, zone_id, name):
        result = self._request("GET", f"/zones/{zone_id}/dns_records?type=A&name={name}")
        records = result.get('result', [])
        return records[0] if records else None

    def add_or_update_record(self, zone_id, name, ip, proxied=True):
        existing = self.get_record(zone_id, name)
        data = {"type": "A", "name": name, "content": ip, "proxied": proxied, "ttl": 1}
        if existing:
            result = self._request("PUT", f"/zones/{zone_id}/dns_records/{existing['id']}", data)
            return result.get('success', False), 'updated'
        else:
            result = self._request("POST", f"/zones/{zone_id}/dns_records", data)
            return result.get('success', False), 'created'


# ── Core Steps ────────────────────────────────────────────────────────────────

PROXY_CONF = """\
<IfModule mod_proxy.c>
  ProxyRequests Off
  ProxyPreserveHost On
  ProxyPass / http://127.0.0.1:3000/
  ProxyPassReverse / http://127.0.0.1:3000/
  RewriteEngine On
  RewriteCond %{HTTP:Upgrade} websocket [NC]
  RewriteCond %{HTTP:Connection} upgrade [NC]
  RewriteRule ^/?(.*) ws://127.0.0.1:3000/$1 [P,L]
</IfModule>
"""

USERDATA_BASE = Path("/etc/apache2/conf.d/userdata")


def get_server_ip():
    result = run("curl -s --max-time 5 ifconfig.me", capture=True, check=False)
    ip = result.stdout.strip()
    return ip if re.match(r'^\d+\.\d+\.\d+\.\d+$', ip) else None


def list_cpanel_accounts():
    data = whmapi("listaccts")
    accounts = []
    for acct in data.get('data', {}).get('acct', []):
        accounts.append({
            'user': acct.get('user'),
            'domain': acct.get('domain'),
        })
    return accounts


def get_current_webui_domain():
    """Scan Apache userdata for proxy.conf pointing to port 3000."""
    found = []
    for conf in USERDATA_BASE.rglob("proxy.conf"):
        if "3000" in conf.read_text():
            # Path: .../userdata/ssl/2_4/USER/DOMAIN/proxy.conf
            parts = conf.parts
            try:
                domain = parts[-2]
                found.append(domain)
            except IndexError:
                pass
    return list(set(found))


def remove_proxy_configs(domain, cpanel_user):
    """Remove proxy.conf from both HTTP and HTTPS vhosts."""
    removed = False
    for proto in ('std', 'ssl'):
        path = USERDATA_BASE / proto / "2_4" / cpanel_user / domain / "proxy.conf"
        if path.exists():
            path.unlink()
            ok(f"Removed proxy: {path}")
            removed = True
    return removed


def write_proxy_configs(domain, cpanel_user):
    """Write proxy.conf to both HTTP and HTTPS vhosts."""
    for proto in ('std', 'ssl'):
        path = USERDATA_BASE / proto / "2_4" / cpanel_user / domain
        path.mkdir(parents=True, exist_ok=True)
        (path / "proxy.conf").write_text(PROXY_CONF)
        ok(f"Written proxy: {path}/proxy.conf")


def create_subdomain(subdomain, root_domain, cpanel_user):
    """Create subdomain in cPanel if it doesn't already exist."""
    docroot = f"{subdomain}.{root_domain}"
    result = cpanel_api(
        cpanel_user, "SubDomain", "addsubdomain",
        {"domain": subdomain, "rootdomain": root_domain, "dir": docroot}
    )
    reason = result.get('cpanelresult', {}).get('event', {}).get('reason', '')
    if 'exists' in reason.lower() or 'already' in reason.lower():
        warn(f"Subdomain {docroot} already exists — skipping creation")
        return True
    if result.get('cpanelresult', {}).get('data'):
        ok(f"Subdomain {docroot} created")
        return True
    warn(f"Could not auto-create subdomain: {reason or 'check cPanel manually'}")
    return False


def rebuild_apache():
    run("/scripts/rebuildhttpdconf", check=False)
    result = run("apachectl configtest", capture=True, check=False)
    if "Syntax OK" in (result.stderr or '') + (result.stdout or ''):
        ok("Apache config syntax OK")
        run("systemctl reload httpd", check=False)
        ok("Apache reloaded")
        return True
    else:
        err("Apache config syntax error — check manually")
        return False


def run_autossl(cpanel_user):
    info("Running AutoSSL (may take 30–60 seconds)...")
    result = run(
        f"/usr/local/cpanel/bin/autossl_check --user={cpanel_user}",
        capture=True, check=False
    )
    output = (result.stdout or '') + (result.stderr or '')
    if 'error' in output.lower():
        warn("AutoSSL reported issues — check WHM > SSL/TLS Status")
    else:
        ok("AutoSSL completed")


def test_domain(domain):
    result = run(f"curl -sk -o /dev/null -w '%{{http_code}}' https://{domain}/health",
                 capture=True, check=False)
    code = result.stdout.strip()
    if code == '200':
        ok(f"https://{domain} → HTTP 200 — live!")
        return True
    else:
        code_http = run(f"curl -s -o /dev/null -w '%{{http_code}}' http://{domain}/health",
                        capture=True, check=False).stdout.strip()
        warn(f"https://{domain} → {code}  |  http://{domain} → {code_http}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Change Open WebUI domain")
    p.add_argument("--domain",       help="New full domain e.g. chat.example.com")
    p.add_argument("--cpanel-user",  help="cPanel account username")
    p.add_argument("--cf-token",     help="Cloudflare API token (optional — for auto DNS)")
    p.add_argument("--remove-old",   action="store_true",
                   help="Remove proxy from old domain (default: prompt)")
    p.add_argument("--skip-ssl",     action="store_true", help="Skip AutoSSL step")
    p.add_argument("--skip-dns",     action="store_true", help="Skip Cloudflare DNS step")
    return p.parse_args()


def main():
    if os.geteuid() != 0:
        err("Must be run as root")
        sys.exit(1)

    args = parse_args()

    print()
    print(bold("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"))
    print(bold("  Open WebUI — Change Domain Script"))
    print(bold("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"))
    print()

    server_ip = get_server_ip()
    ok(f"Server IP: {server_ip}")

    # ── Step 1: Find current domain ──────────────────────────────────────────
    current_domains = get_current_webui_domain()
    if current_domains:
        info(f"Current WebUI domain(s): {', '.join(current_domains)}")
    else:
        warn("No existing WebUI domain proxy found")

    # ── Step 2: Choose new domain ────────────────────────────────────────────
    new_domain = args.domain
    if not new_domain:
        print()
        new_domain = input(f"  {bold('Enter new domain')} (e.g. chat.example.com): ").strip()
    if not new_domain or '.' not in new_domain:
        err("Invalid domain")
        sys.exit(1)

    domain_parts = new_domain.split('.')
    is_subdomain = len(domain_parts) > 2

    # ── Step 3: Choose cPanel account ───────────────────────────────────────
    cpanel_user = args.cpanel_user
    if not cpanel_user:
        accounts = list_cpanel_accounts()
        if accounts:
            print()
            print(f"  {bold('cPanel accounts on this server:')}")
            for i, acct in enumerate(accounts):
                print(f"    [{i+1}] {acct['user']:20s} → {acct['domain']}")
            print()
            choice = input(f"  {bold('Select account number (or type username directly):' )} ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(accounts):
                cpanel_user = accounts[int(choice)-1]['user']
            else:
                cpanel_user = choice

    ok(f"Using cPanel account: {cpanel_user}")

    # ── Step 4: Create subdomain in cPanel ───────────────────────────────────
    print()
    info("Step 1/5 — cPanel subdomain")
    if is_subdomain:
        subdomain = domain_parts[0]
        root_domain = '.'.join(domain_parts[1:])
        create_subdomain(subdomain, root_domain, cpanel_user)
    else:
        warn(f"{new_domain} is a root domain — skipping subdomain creation")

    # ── Step 5: Remove old proxy configs ─────────────────────────────────────
    print()
    info("Step 2/5 — Remove old proxy")
    for old in current_domains:
        if old == new_domain:
            continue
        # Find which cPanel user owns the old domain
        old_user_result = run(
            f"whmapi1 listaccts | python3 -c \"import sys,json; d=json.load(sys.stdin); "
            f"[print(a['user']) for a in d.get('data',{{}}).get('acct',[]) if '{old}' in a.get('domain','')]\"",
            capture=True, check=False
        )
        old_user = old_user_result.stdout.strip() or cpanel_user
        if args.remove_old or confirm(f"Remove proxy from old domain {old}?"):
            remove_proxy_configs(old, old_user)
        else:
            warn(f"Keeping proxy on {old}")

    # ── Step 6: Write new proxy config ───────────────────────────────────────
    print()
    info("Step 3/5 — Write Apache proxy config")
    write_proxy_configs(new_domain, cpanel_user)
    rebuild_apache()

    # ── Step 7: Cloudflare DNS ───────────────────────────────────────────────
    print()
    info("Step 4/5 — DNS")
    if not args.skip_dns:
        cf_token = args.cf_token
        if not cf_token:
            print()
            print(f"  {bold('Cloudflare API token')} (leave blank to skip auto-DNS):")
            print(f"  Get one at: Cloudflare Dashboard → My Profile → API Tokens")
            cf_token = input("  Token: ").strip()

        if cf_token:
            cf = CloudflareAPI(cf_token)
            zone_id, zone_name = cf.get_zone(new_domain)
            if zone_id:
                ok(f"Found Cloudflare zone: {zone_name} ({zone_id})")
                success, action = cf.add_or_update_record(zone_id, new_domain, server_ip)
                if success:
                    ok(f"DNS record {action}: {new_domain} → {server_ip} (proxied)")
                else:
                    err(f"Cloudflare API error — add DNS manually")
                    _print_dns_instructions(new_domain, server_ip)
            else:
                err(f"Zone not found in Cloudflare for {new_domain}")
                _print_dns_instructions(new_domain, server_ip)
        else:
            warn("No CF token — add DNS manually:")
            _print_dns_instructions(new_domain, server_ip)
    else:
        warn("DNS step skipped")
        _print_dns_instructions(new_domain, server_ip)

    # ── Step 8: AutoSSL ──────────────────────────────────────────────────────
    print()
    info("Step 5/5 — SSL certificate")
    if not args.skip_ssl:
        run_autossl(cpanel_user)
    else:
        warn("SSL step skipped")

    # ── Done ─────────────────────────────────────────────────────────────────
    print()
    print(bold("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"))
    print(bold("  Done — testing domain..."))
    print(bold("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"))
    print()

    test_domain(new_domain)

    print()
    print(f"  {bold('Access URLs:')}")
    print(f"    https://{new_domain}")
    print(f"    http://{server_ip}:3000  (direct, no domain needed)")
    print()
    print(f"  {bold('If domain returns 000/5xx:')}")
    print(f"    1. Check DNS record is added in Cloudflare")
    print(f"    2. Check Cloudflare SSL mode is 'Full' (not Strict)")
    print(f"    3. Wait 1–2 min for DNS propagation")
    print()


def _print_dns_instructions(domain, ip):
    print()
    print(f"  {bold('Add this record in Cloudflare DNS:')}")
    print(f"    Type:  A")
    print(f"    Name:  {domain.split('.')[0] if '.' in domain else domain}")
    print(f"    IPv4:  {ip}")
    print(f"    Proxy: ON (orange cloud)")
    print(f"    SSL:   Full (not Strict)")
    print()


if __name__ == "__main__":
    main()
