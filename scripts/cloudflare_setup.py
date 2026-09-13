#!/usr/bin/env python3
"""One-time (idempotent) Cloudflare setup for hosting the map.

Creates, if missing:
  - R2 bucket $BUCKET with CORS allowing GET/HEAD + Range from any origin
  - custom domain data.$DOMAIN on the bucket (Cloudflare CDN in front of R2)
  - a Cache Rule making everything on data.$DOMAIN cache-eligible with a
    long edge TTL (.pmtiles is not a cacheable extension by default)
  - Cloudflare Pages project $PAGES_PROJECT with custom domain $DOMAIN and
    the apex CNAME record

Environment: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, optionally DOMAIN
(default postcodemap.net), BUCKET (postcodemap), PAGES_PROJECT (postcodemap),
PRODUCTION_BRANCH (the git branch deploys come from).

Token permissions: Account → Workers R2 Storage: Edit, Cloudflare Pages: Edit;
Zone ($DOMAIN) → Zone: Read, DNS: Edit, Cache Rules: Edit.
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"
TOKEN = os.environ["CLOUDFLARE_API_TOKEN"]
ACCOUNT = os.environ["CLOUDFLARE_ACCOUNT_ID"]
DOMAIN = os.environ.get("DOMAIN", "postcodemap.net")
DATA_HOST = f"data.{DOMAIN}"
BUCKET = os.environ.get("BUCKET", "postcodemap")
PROJECT = os.environ.get("PAGES_PROJECT", "postcodemap")
BRANCH = os.environ.get("PRODUCTION_BRANCH", "main")


def cf(method, path, body=None, ok=(200, 201), quiet_errors=()):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        payload = e.read().decode()
        try:
            errs = json.loads(payload).get("errors", [])
        except Exception:
            errs = [{"code": e.code, "message": payload[:200]}]
        if any(er.get("code") in quiet_errors for er in errs):
            return {"result": None, "errors": errs}
        sys.exit(f"{method} {path} -> HTTP {e.code}: {errs}")


def step(msg):
    print(f"* {msg}", flush=True)


# ---------------------------------------------------------------- zone
zones = cf("GET", f"/zones?name={DOMAIN}")["result"]
if not zones:
    sys.exit(f"zone {DOMAIN} not found in this account (is the domain on Cloudflare DNS?)")
ZONE = zones[0]["id"]
step(f"zone {DOMAIN} = {ZONE}")

# ---------------------------------------------------------------- R2 bucket
r = cf("POST", f"/accounts/{ACCOUNT}/r2/buckets", {"name": BUCKET}, quiet_errors=(10004,))  # 10004 = already exists
step(f"bucket {BUCKET} {'created' if r.get('result') else 'exists'}")

cors = {"rules": [{"allowed": {"origins": ["*"], "methods": ["GET", "HEAD"], "headers": ["range", "if-match", "if-none-match"]},
                   "exposeHeaders": ["etag", "content-range", "content-length", "accept-ranges"], "maxAgeSeconds": 86400}]}
cf("PUT", f"/accounts/{ACCOUNT}/r2/buckets/{BUCKET}/cors", cors)
step("bucket CORS set (GET/HEAD + Range from any origin)")

domains = cf("GET", f"/accounts/{ACCOUNT}/r2/buckets/{BUCKET}/domains/custom")["result"]
if not any(d.get("domain") == DATA_HOST for d in (domains.get("domains") if isinstance(domains, dict) else domains) or []):
    cf("POST", f"/accounts/{ACCOUNT}/r2/buckets/{BUCKET}/domains/custom", {"domain": DATA_HOST, "zoneId": ZONE, "enabled": True, "minTLS": "1.2"})
    step(f"custom domain {DATA_HOST} attached to bucket (DNS record created by R2)")
else:
    step(f"custom domain {DATA_HOST} already attached")

# ---------------------------------------------------------------- cache rule
DESC = "postcodemap: cache everything on the data host"
rule = {"description": DESC, "expression": f'(http.host eq "{DATA_HOST}")', "action": "set_cache_settings",
        "action_parameters": {"cache": True, "edge_ttl": {"mode": "override_origin", "default": 31536000},
                              "browser_ttl": {"mode": "respect_origin"}}}
entry = cf("GET", f"/zones/{ZONE}/rulesets/phases/http_request_cache_settings/entrypoint", quiet_errors=(10000, 10001, 10002, 10003))
existing = (entry.get("result") or {}).get("rules", []) if entry.get("result") else []
if any(x.get("description") == DESC for x in existing):
    step("cache rule already present")
else:
    if entry.get("result"):
        cf("POST", f"/zones/{ZONE}/rulesets/{entry['result']['id']}/rules", rule)
    else:
        cf("PUT", f"/zones/{ZONE}/rulesets/phases/http_request_cache_settings/entrypoint", {"rules": [rule]})
    step(f"cache rule created: {DATA_HOST} cache everything, edge TTL 1 year")

# ---------------------------------------------------------------- Pages project + apex domain
proj = cf("GET", f"/accounts/{ACCOUNT}/pages/projects/{PROJECT}", quiet_errors=(8000007,))
if not proj.get("result"):
    cf("POST", f"/accounts/{ACCOUNT}/pages/projects", {"name": PROJECT, "production_branch": BRANCH})
    step(f"Pages project {PROJECT} created (production branch {BRANCH})")
else:
    step(f"Pages project {PROJECT} exists")
pd = cf("GET", f"/accounts/{ACCOUNT}/pages/projects/{PROJECT}/domains")["result"]
if not any(d.get("name") == DOMAIN for d in pd):
    cf("POST", f"/accounts/{ACCOUNT}/pages/projects/{PROJECT}/domains", {"name": DOMAIN})
    step(f"custom domain {DOMAIN} added to Pages project")
else:
    step(f"Pages custom domain {DOMAIN} already added")
recs = cf("GET", f"/zones/{ZONE}/dns_records?name={DOMAIN}&type=CNAME")["result"]
if not recs:
    cf("POST", f"/zones/{ZONE}/dns_records", {"type": "CNAME", "name": DOMAIN, "content": f"{PROJECT}.pages.dev", "proxied": True, "ttl": 1})
    step(f"DNS: {DOMAIN} CNAME {PROJECT}.pages.dev (proxied)")
else:
    step(f"DNS: {DOMAIN} CNAME exists -> {recs[0]['content']}")
print("done")
