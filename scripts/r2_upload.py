#!/usr/bin/env python3
"""Upload a directory tree to R2 concurrently through the Cloudflare API
(the same endpoint `wrangler r2 object put` uses, without a Node start-up per
file), paced to the API's rate limit. Objects get an immutable one-year Cache-Control header, because the
prefix is versioned per deploy.

    python3 scripts/r2_upload.py <dir> <bucket> <prefix>      e.g. dist/countries postcodemap v/20260913-abc1234/countries

Environment: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID.
"""
import mimetypes
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# The Cloudflare API allows 1,200 requests per 5 minutes per token; stay under it.
RATE = 3.5  # requests per second
_lock, _next = threading.Lock(), [0.0]


def pace():
    with _lock:
        now = time.time()
        _next[0] = max(_next[0], now) + 1 / RATE
        wait = _next[0] - now - 1 / RATE
    if wait > 0:
        time.sleep(wait)

TOKEN, ACCOUNT = os.environ["CLOUDFLARE_API_TOKEN"], os.environ["CLOUDFLARE_ACCOUNT_ID"]
root, bucket, prefix = sys.argv[1], sys.argv[2], sys.argv[3].strip("/")
mimetypes.add_type("application/octet-stream", ".pmtiles")


def put(rel):
    key = f"{prefix}/{rel}"
    ctype = mimetypes.guess_type(rel)[0] or "application/octet-stream"
    with open(os.path.join(root, rel), "rb") as f:
        data = f.read()
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/r2/buckets/{bucket}/objects/{urllib.request.quote(key)}"
    for attempt in range(8):
        pace()
        req = urllib.request.Request(url, method="PUT", data=data, headers={
            "Authorization": f"Bearer {TOKEN}", "Content-Type": ctype, "Content-Length": str(len(data)),
            "Cache-Control": "public, max-age=31536000, immutable"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                r.read()
            return len(data)
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            if e.code in (429, 500, 502, 503, 504) and attempt < 7:
                time.sleep(min(60, float(e.headers.get("Retry-After") or 0) or 5 * 2 ** attempt))
                continue
            sys.exit(f"PUT {key} -> HTTP {e.code}: {body}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 7:
                time.sleep(5 * 2 ** attempt)
                continue
            sys.exit(f"PUT {key} failed: {e}")


files = sorted(os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs)
t0 = time.time()
with ThreadPoolExecutor(max_workers=6) as ex:
    total = sum(ex.map(put, files))
print(f"uploaded {len(files)} files, {total / 1e6:.1f} MB, to {bucket}/{prefix}/ in {time.time() - t0:.0f}s")
