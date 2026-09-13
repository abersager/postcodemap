#!/usr/bin/env python3
"""Upload a directory tree to R2 concurrently through the Cloudflare API
(the same endpoint `wrangler r2 object put` uses, without a Node start-up per
file). Objects get an immutable one-year Cache-Control header, because the
prefix is versioned per deploy.

    python3 scripts/r2_upload.py <dir> <bucket> <prefix>      e.g. dist/countries postcodemap v/20260913-abc1234/countries

Environment: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID.
"""
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

TOKEN, ACCOUNT = os.environ["CLOUDFLARE_API_TOKEN"], os.environ["CLOUDFLARE_ACCOUNT_ID"]
root, bucket, prefix = sys.argv[1], sys.argv[2], sys.argv[3].strip("/")
mimetypes.add_type("application/octet-stream", ".pmtiles")


def put(rel):
    key = f"{prefix}/{rel}"
    ctype = mimetypes.guess_type(rel)[0] or "application/octet-stream"
    with open(os.path.join(root, rel), "rb") as f:
        data = f.read()
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/r2/buckets/{bucket}/objects/{urllib.request.quote(key)}"
    for attempt in range(5):
        req = urllib.request.Request(url, method="PUT", data=data, headers={
            "Authorization": f"Bearer {TOKEN}", "Content-Type": ctype, "Content-Length": str(len(data)),
            "Cache-Control": "public, max-age=31536000, immutable"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                r.read()
            return len(data)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(2 ** attempt)
                continue
            sys.exit(f"PUT {key} -> HTTP {e.code}: {e.read().decode()[:200]}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 4:
                time.sleep(2 ** attempt)
                continue
            sys.exit(f"PUT {key} failed: {e}")


files = sorted(os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs)
t0 = time.time()
with ThreadPoolExecutor(max_workers=24) as ex:
    total = sum(ex.map(put, files))
print(f"uploaded {len(files)} files, {total / 1e6:.1f} MB, to {bucket}/{prefix}/ in {time.time() - t0:.0f}s")
