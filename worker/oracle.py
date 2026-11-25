"""Oracle worker: polls Open-Meteo for the mela grid point and posts a heartbeat
+ observation to the app. Runs as a pod on the NudgeBee-watched cluster.

Fails fast on bad config, so a broken deploy shows up as CrashLoopBackOff:
the incident NudgeBee investigates in the demo.
"""

import json
import os
import sys
import time
import urllib.request

APP_URL = os.environ.get("APP_URL", "").rstrip("/")
TOKEN = os.environ.get("ORACLE_TOKEN", "")
LAT = float(os.environ.get("LAT", "12.9822"))
LON = float(os.environ.get("LON", "77.6083"))
INTERVAL = int(os.environ.get("INTERVAL_SECONDS", "20"))


def log(**kw):
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **kw}), flush=True)


def fetch_rain() -> dict:
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
           f"&hourly=precipitation&past_hours=1&forecast_hours=1&timezone=Asia%2FKolkata")
    with urllib.request.urlopen(url, timeout=15) as r:
        j = json.load(r)
    return {"lat": LAT, "lon": LON, "rain_mm_last_hour": j["hourly"]["precipitation"][0],
            "hour": j["hourly"]["time"][0], "source": "open-meteo"}


def post(obs: dict):
    req = urllib.request.Request(f"{APP_URL}/api/oracle/heartbeat", data=json.dumps(obs).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Oracle-Token": TOKEN})
    with urllib.request.urlopen(req, timeout=15) as r:
        if r.status != 200:
            raise RuntimeError(f"app returned {r.status}")


def main():
    if not APP_URL.startswith("http"):
        log(level="fatal", msg="APP_URL missing or invalid", app_url=APP_URL)
        sys.exit(2)
    if not TOKEN:
        log(level="fatal", msg="ORACLE_TOKEN missing")
        sys.exit(2)
    log(level="info", msg="oracle worker starting", app_url=APP_URL, lat=LAT, lon=LON)
    failures = 0
    while True:
        try:
            obs = fetch_rain()
            post(obs)
            log(level="info", msg="observation posted", **obs)
            failures = 0
        except Exception as e:
            failures += 1
            log(level="error", msg="post failed", error=str(e), consecutive_failures=failures)
            if failures >= 3:
                log(level="fatal", msg="cannot reach app or weather source; exiting")
                sys.exit(1)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
