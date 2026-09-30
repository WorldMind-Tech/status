#!/usr/bin/env python3
"""One round of checks for the PreWorld Review status page (run every 5 minutes by .github/workflows/check.yml).

Probes each public endpoint, updates data/status.json (current state, per-day counts for 90 days, the last 50 incidents) and
opens or closes the incident issue. A check counts as down after two failing rounds in a row, so one network blip is not an
outage. Only the public health endpoint and the docs page are read: no customer data, no credentials.
"""
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.request

CHECKS = [
    {"id": "app", "name": "平台 / Platform", "url": "https://review.nice2.io/healthz", "expect": '"ok":true'},
    {"id": "docs", "name": "文档站 / Docs", "url": "https://review.nice2.io/docs/", "expect": None},
]
DATA = "data/status.json"
DAYS_KEPT = 90
DOWN_AFTER = 2


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(t):
    return t.isoformat().replace("+00:00", "Z")


def probe(check):
    """(ok, milliseconds, what went wrong): up to three tries, 10 s apart"""
    detail = ""
    for attempt in range(3):
        started = time.monotonic()
        try:
            req = urllib.request.Request(check["url"], headers={"User-Agent": "WorldMind-Tech status check"})
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read(4096).decode("utf-8", "replace")
                ms = round((time.monotonic() - started) * 1000)
                if check["expect"] and check["expect"] not in body.replace(" ", ""):
                    detail = f"HTTP {r.status}, unexpected answer"
                else:
                    return True, ms, ""
        except urllib.error.HTTPError as e:
            detail = f"HTTP {e.code}"
        except Exception as e:  # timeouts, DNS, TLS: the name of the error is enough
            detail = type(e).__name__
        if attempt < 2:
            time.sleep(10)
    return False, None, detail


def github(method, path, body=None):
    """the repository's own issues, with the workflow's token; nothing when run outside Actions"""
    token, repo = os.environ.get("GH_TOKEN"), os.environ.get("REPO")
    if not token or not repo:
        return None
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read() or b"null")


def main():
    data = json.load(open(DATA, encoding="utf-8")) if os.path.exists(DATA) else {}
    state, days, incidents = data.setdefault("state", {}), data.setdefault("days", {}), data.setdefault("incidents", [])
    t = now()
    data["checks"] = [{k: c[k] for k in ("id", "name", "url")} for c in CHECKS]
    for c in CHECKS:
        ok, ms, detail = probe(c)
        s = state.setdefault(c["id"], {"status": "up", "since": iso(t), "fails": 0})
        count = days.setdefault(t.date().isoformat(), {}).setdefault(c["id"], [0, 0])
        count[0] += 1 if ok else 0
        count[1] += 1
        s.update(last_checked=iso(t), last_ms=ms, last_error=detail or None)
        if ok:
            s["fails"], s["first_fail"] = 0, None
            if s["status"] == "down":
                s["status"], s["since"] = "up", iso(t)
                open_incident = next((i for i in reversed(incidents) if i["check"] == c["id"] and not i.get("end")), None)
                if open_incident:
                    open_incident["end"] = iso(t)
                    if open_incident.get("issue"):
                        try:
                            github("POST", f"/issues/{open_incident['issue']}/comments", {"body": f"Back up at {iso(t)} UTC. 已恢复。"})
                            github("PATCH", f"/issues/{open_incident['issue']}", {"state": "closed"})
                        except Exception as e:
                            print(f"could not close issue {open_incident['issue']}: {e}")
        else:
            s["fails"] += 1
            s["first_fail"] = s.get("first_fail") or iso(t)
            if s["status"] == "up" and s["fails"] >= DOWN_AFTER:
                s["status"], s["since"] = "down", s["first_fail"]
                incident = {"check": c["id"], "start": s["first_fail"], "end": None, "detail": detail, "issue": None}
                try:
                    issue = github("POST", "/issues", {
                        "title": f"{c['name']}: down / 不可用",
                        "labels": ["incident"],
                        "body": f"{c['url']} failed {s['fails']} checks in a row, starting about {s['first_fail']} UTC ({detail}). "
                                f"This issue closes itself when the check passes again.\n\n"
                                f"从 {s['first_fail']}（UTC）起连续 {s['fails']} 次检查没通过（{detail}）。恢复后这个 issue 自动关闭。",
                    })
                    incident["issue"] = issue and issue.get("number")
                except Exception as e:
                    print(f"could not open an issue: {e}")
                incidents.append(incident)
        print(f"{c['id']}: {'ok' if ok else 'FAIL ' + detail} {ms if ms is not None else ''}")
    for day in sorted(days)[:-DAYS_KEPT]:
        del days[day]
    del incidents[:-50]
    data["updated"] = iso(t)
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    main()
