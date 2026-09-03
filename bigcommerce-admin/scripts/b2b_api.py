#!/usr/bin/env python3
"""
BigCommerce B2B Edition API client (stdlib only).

Separate host and auth scheme from bc_api.py's core Store API, but reuses
the SAME credentials (as of Sept 2025, the old authToken exchange is
deprecated — server-to-server B2B calls just use the store's normal
X-Auth-Token plus a new X-Store-Hash header). See
references/b2b-edition.md for endpoint details, gotchas, and a full RFQ
(quote) payload example.

CLI:
  python b2b_api.py GET  /api/v3/io/companies
  python b2b_api.py GET  /api/v3/io/rfq --params limit=50
  python b2b_api.py POST /api/v3/io/rfq --data @quote.json
  python b2b_api.py PUT  /api/v3/io/super-admins/20667710 --data '{"companies": [{"companyId": 123, "isAssigned": true}]}'

Importable:
  from b2b_api import b2b_request
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bc_api import _creds, redact, MAX_429_RETRIES  # noqa: E402

B2B_BASE = "https://api-b2b.bigcommerce.com"


def b2b_request(method, path, params=None, body=None, env=None):
    """One B2B Edition API request. Returns (status_code, parsed_json_or_None)."""
    store_hash, token = _creds(env)
    url = f"{B2B_BASE}{path}"
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, safe=":,")

    headers = {"X-Auth-Token": token, "X-Store-Hash": store_hash, "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None

    for attempt in range(MAX_429_RETRIES + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < MAX_429_RETRIES:
                time.sleep(5)
                continue
            raw = e.read()
            try:
                return e.code, json.loads(raw) if raw else None
            except json.JSONDecodeError:
                return e.code, {"raw": redact(raw.decode(errors="replace"))}
        except urllib.error.URLError as e:
            sys.exit(redact(f"Network error calling {method} {path}: {e.reason}"))
    return 429, None


def _main():
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)

    method, path = args[0].upper(), args[1]
    rest = args[2:]

    params, data, env = None, None, None
    i = 0
    while i < len(rest):
        if rest[i] == "--params":
            params = {}
            i += 1
            while i < len(rest) and not rest[i].startswith("--"):
                k, _, v = rest[i].partition("=")
                params[k] = v
                i += 1
        elif rest[i] == "--data":
            i += 1
            raw = rest[i]
            if raw.startswith("@"):
                raw = Path(raw[1:]).read_text()
            data = json.loads(raw)
            i += 1
        elif rest[i] == "--env":
            i += 1
            env = rest[i]
            i += 1
        elif rest[i] == "--yes":
            i += 1
        else:
            i += 1

    if method == "DELETE" and "--yes" not in rest:
        sys.exit(f"Refusing DELETE {path} without --yes.")

    status, resp = b2b_request(method, path, params=params, body=data, env=env)
    print(f"# HTTP {status}")
    print(redact(json.dumps(resp, indent=2)) if resp is not None else "")


if __name__ == "__main__":
    _main()
