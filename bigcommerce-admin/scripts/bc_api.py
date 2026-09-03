#!/usr/bin/env python3
"""
BigCommerce Management API client (stdlib only).

Credential sources, in priority order:
  1. Environment variables: BC_STORE_HASH, BC_ACCESS_TOKEN
  2. .env.local in the current directory (or nearest parent), lines like:
       BC_STORE_HASH=abc123
       BC_ACCESS_TOKEN=xxxx
       # multi-env variants also supported: BC_STAGING_STORE_HASH=..., etc.
     Also accepted as a fallback (the Catalyst/Next.js storefront convention),
     when no --env/BC_ENV is given:
       BIGCOMMERCE_STORE_HASH=abc123
       BIGCOMMERCE_ACCESS_TOKEN=xxxx
  3. ~/.bc-cli/config.json, either flat:
       {"store_hash": "...", "access_token": "..."}
     or multi-environment:
       {"default_environment": "prod",
        "environments": {
          "prod":    {"store_hash": "...", "access_token": "..."},
          "staging": {"store_hash": "...", "access_token": "..."}}}

Select an environment with --env NAME or BC_ENV=NAME.

SECURITY: access tokens are never printed. All output (responses, errors,
URLs) is passed through a redactor that masks any occurrence of the token.

CLI:
  python bc_api.py list-envs
  python bc_api.py GET  /v3/catalog/products --params limit=50
  python bc_api.py GET  /v3/catalog/products --all --env staging
  python bc_api.py POST /v3/catalog/products --data @new.json
  python bc_api.py DELETE /v3/catalog/products/123 --yes

Importable:
  from bc_api import request, get_all, redact
"""

import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

BASE = "https://api.bigcommerce.com/stores/{hash}{path}"
MAX_429_RETRIES = 5
_SECRETS = {}  # secret value -> placeholder; populated as credentials load


def _finish_creds(h, t):
    """Register credentials for redaction, then hand them back."""
    if t:
        _SECRETS[t] = "[ACCESS_TOKEN]"
    if h:
        _SECRETS[h] = "[STORE_HASH]"
    return h, t


def redact(text):
    """Mask any known secret in a string before it is shown anywhere."""
    if not isinstance(text, str):
        text = str(text)
    for secret, placeholder in _SECRETS.items():
        text = text.replace(secret, placeholder)
    return text


def mask(value, keep=4):
    """Display helper: show only a short prefix of an identifier."""
    if not value:
        return "?"
    return value[:keep] + "…" if len(value) > keep else value


def _parse_env_file(path):
    vals = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            vals[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return vals


def _find_env_local():
    d = Path.cwd()
    for parent in [d, *d.parents]:
        f = parent / ".env.local"
        if f.is_file():
            return f
    return None


def _load_config_json():
    f = Path.home() / ".bc-cli" / "config.json"
    if not f.is_file():
        return None
    try:
        return json.loads(f.read_text())
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"Could not parse {f}: {e.__class__.__name__}")


def _entry_creds(e):
    """Read store_hash/access_token from a config entry, accepting camelCase too."""
    h = e.get("store_hash") or e.get("storeHash")
    t = e.get("access_token") or e.get("accessToken")
    return h, t


def list_environments():
    """Return env names + store hashes only — never tokens."""
    out = []
    cfg = _load_config_json()
    if cfg:
        envs = cfg.get("environments")
        if isinstance(envs, dict):
            default = cfg.get("default_environment")
            for name, e in envs.items():
                h, _ = _entry_creds(e)
                out.append({"environment": name,
                            "store_hash": mask(h),
                            "default": name == default})
        else:
            h, _ = _entry_creds(cfg)
            if h:
                out.append({"environment": "(flat config)",
                            "store_hash": mask(h), "default": True})
    env_file = _find_env_local()
    if env_file:
        vals = _parse_env_file(env_file)
        for k in vals:
            if k.endswith("STORE_HASH") and k.startswith("BC_"):
                name = k[len("BC_"):-len("_STORE_HASH")].lower() if k != "BC_STORE_HASH" else "(default)"
                out.append({"environment": f"{name} [.env.local]",
                            "store_hash": mask(vals[k]), "default": k == "BC_STORE_HASH"})
        if "BIGCOMMERCE_STORE_HASH" in vals and "BC_STORE_HASH" not in vals:
            out.append({"environment": "(default) [.env.local, BIGCOMMERCE_*]",
                        "store_hash": mask(vals["BIGCOMMERCE_STORE_HASH"]), "default": True})
    return out


def set_default_environment(name):
    """Set default_environment in ~/.bc-cli/config.json. Prints no secrets."""
    f = Path.home() / ".bc-cli" / "config.json"
    cfg = _load_config_json()
    if not cfg or not isinstance(cfg.get("environments"), dict):
        sys.exit(f"No multi-environment config found at {f}.")
    envs = cfg["environments"]
    if name not in envs:
        sys.exit(f"Environment '{name}' not found "
                 f"(available: {', '.join(sorted(envs))}).")
    previous = cfg.get("default_environment")
    cfg["default_environment"] = name
    f.write_text(json.dumps(cfg, indent=2) + "\n")
    print(f"Default environment: {previous or '(none)'} -> {name}")


def _creds(env_name=None):
    env_name = env_name or os.environ.get("BC_ENV")

    # 1. process environment (only when no named env requested)
    if not env_name:
        h, t = os.environ.get("BC_STORE_HASH"), os.environ.get("BC_ACCESS_TOKEN")
        if h and t:
            return _finish_creds(h, t)
        h, t = os.environ.get("BIGCOMMERCE_STORE_HASH"), os.environ.get("BIGCOMMERCE_ACCESS_TOKEN")
        if h and t:
            return _finish_creds(h, t)

    # 2. .env.local
    env_file = _find_env_local()
    if env_file:
        vals = _parse_env_file(env_file)
        if env_name:
            prefix = f"BC_{env_name.upper()}_"
            h, t = vals.get(prefix + "STORE_HASH"), vals.get(prefix + "ACCESS_TOKEN")
        else:
            h, t = vals.get("BC_STORE_HASH"), vals.get("BC_ACCESS_TOKEN")
            if not (h and t):
                # Catalyst/Next.js storefront convention
                h, t = vals.get("BIGCOMMERCE_STORE_HASH"), vals.get("BIGCOMMERCE_ACCESS_TOKEN")
        if h and t:
            return _finish_creds(h, t)

    # 3. ~/.bc-cli/config.json
    cfg = _load_config_json()
    if cfg:
        envs = cfg.get("environments")
        if isinstance(envs, dict):
            name = env_name or cfg.get("default_environment")
            if not name:
                sys.exit("Multiple environments in ~/.bc-cli/config.json and no "
                         "default_environment set; pass --env NAME "
                         f"(available: {', '.join(envs)}).")
            e = envs.get(name)
            if not e:
                sys.exit(f"Environment '{name}' not found "
                         f"(available: {', '.join(envs)}).")
            h, t = _entry_creds(e)
        else:
            h, t = _entry_creds(cfg)
        if h and t:
            return _finish_creds(h, t)

    sys.exit(
        "No credentials found. Provide them via BC_STORE_HASH/BC_ACCESS_TOKEN "
        "env vars, a .env.local file, or ~/.bc-cli/config.json "
        "(tokens come from the control panel: Settings > API > API Accounts)."
    )


def request(method, path, params=None, body=None, file_path=None, env=None):
    """Make one API request. Returns (status_code, parsed_json_or_None).
    Retries automatically on 429 using X-Rate-Limit-Time-Reset-Ms."""
    store_hash, token = _creds(env)
    url = BASE.format(hash=store_hash, path=path)
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, safe=":,")

    headers = {"X-Auth-Token": token, "Accept": "application/json"}
    data = None
    if file_path:
        boundary = uuid.uuid4().hex
        ctype = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        with open(file_path, "rb") as f:
            content = f.read()
        name = os.path.basename(file_path)
        data = (
            f"--{boundary}\r\nContent-Disposition: form-data; "
            f'name="image_file"; filename="{name}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"

    for attempt in range(MAX_429_RETRIES + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < MAX_429_RETRIES:
                reset_ms = int(e.headers.get("X-Rate-Limit-Time-Reset-Ms", 30000))
                wait = min(reset_ms / 1000 + 0.5, 35)
                print(f"[rate-limited] waiting {wait:.1f}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            raw = e.read()
            try:
                return e.code, json.loads(raw) if raw else None
            except json.JSONDecodeError:
                return e.code, {"raw": redact(raw.decode(errors="replace"))}
        except urllib.error.URLError as e:
            sys.exit(redact(f"Network error calling {method} {path}: {e.reason}"))
    return 429, None


def get_all(path, params=None, limit=250, env=None):
    """Yield every item across pages. Works for v3 (data/meta) and v2 (bare list)."""
    params = dict(params or {})
    params.setdefault("limit", limit)
    page = 1
    while True:
        params["page"] = page
        status, payload = request("GET", path, params=params, env=env)
        if status == 204 or payload is None:
            return
        if status >= 400:
            raise RuntimeError(redact(f"GET {path} page {page} -> {status}: {payload}"))
        if isinstance(payload, dict) and "data" in payload:  # v3
            yield from payload["data"]
            pg = (payload.get("meta") or {}).get("pagination") or {}
            if page >= pg.get("total_pages", page):
                return
        elif isinstance(payload, list):  # v2
            yield from payload
            if len(payload) < int(params["limit"]):
                return
        else:
            yield payload
            return
        page += 1


def _main():
    import argparse

    p = argparse.ArgumentParser(description="BigCommerce Management API client")
    p.add_argument("method", choices=["GET", "POST", "PUT", "DELETE", "list-envs", "set-default"])
    p.add_argument("path", nargs="?", help="API path, or env name for set-default")
    p.add_argument("--env", help="named environment from config.json / .env.local")
    p.add_argument("--params", nargs="*", default=[], help="key=value query params")
    p.add_argument("--data", help="JSON body, or @file.json")
    p.add_argument("--file", dest="file_path", help="upload a local file (multipart image_file)")
    p.add_argument("--all", action="store_true", help="GET: fetch all pages")
    p.add_argument("--yes", action="store_true", help="confirm destructive request")
    args = p.parse_args()

    if args.method == "set-default":
        if not args.path:
            p.error("usage: set-default <environment-name>")
        set_default_environment(args.path)
        return

    if args.method == "list-envs":
        envs = list_environments()
        if not envs:
            print("No environments found in ~/.bc-cli/config.json or .env.local.")
        else:
            for e in envs:
                mark = " (default)" if e["default"] else ""
                print(f"{e['environment']:<28} store_hash={e['store_hash']}{mark}")
        return

    if not args.path:
        p.error("path is required for API requests")

    params = dict(kv.split("=", 1) for kv in args.params)

    destructive = args.method == "DELETE" or (
        args.method in ("PUT", "POST") and "settings" in args.path
    )
    broad_delete = args.method == "DELETE" and (
        not args.path.rstrip("/").split("/")[-1].isdigit() or params
    )
    if destructive and not args.yes:
        sys.exit(
            f"Refusing {args.method} {args.path} without --yes."
            + (" WARNING: this delete targets multiple/all records." if broad_delete else "")
        )

    body = None
    if args.data:
        raw = open(args.data[1:]).read() if args.data.startswith("@") else args.data
        body = json.loads(raw)

    if args.all and args.method == "GET":
        items = list(get_all(args.path, params, env=args.env))
        print(redact(json.dumps(items, indent=2)))
        print(f"\n# {len(items)} items total", file=sys.stderr)
        return

    status, payload = request(args.method, args.path, params=params, body=body,
                              file_path=args.file_path, env=args.env)
    print(f"# HTTP {status}", file=sys.stderr)
    if payload is not None:
        print(redact(json.dumps(payload, indent=2)))
    if status >= 400:
        sys.exit(1)


if __name__ == "__main__":
    _main()
