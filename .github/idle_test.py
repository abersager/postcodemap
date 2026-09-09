import urllib3, time, sys
urllib3.disable_warnings()
hosts = {"github.io/Fastly": ("https://abersager.github.io/postcodemap/tiles/boundaries.pmtiles", {"Range": "bytes=0-1023"}),
         "example.com/control": ("https://example.com/", {})}
pools = {n: urllib3.PoolManager(maxsize=1, timeout=urllib3.Timeout(connect=10, read=40)) for n in hosts}
def get(n):
    u, h = hosts[n]; t0 = time.time()
    r = pools[n].request("GET", u, headers=h, preload_content=False); r.read(); r.release_conn()
    return time.time() - t0
for n in hosts: get(n)
stalls = {n: 0 for n in hosts}; rows = []
for trial in range(10):
    time.sleep(20)
    line = f"trial {trial+1}:"
    for n in hosts:
        try: d = get(n); line += f"  {n} {d:.2f}s"; stalls[n] += d > 5
        except Exception as e: line += f"  {n} ERROR({type(e).__name__})"; stalls[n] += 1
    print(line, flush=True)
print("STALLS(>5s) after 20s idle:", stalls, flush=True)
