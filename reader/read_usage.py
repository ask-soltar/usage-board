#!/usr/bin/env python3
"""Reads the Claude, ChatGPT, Gemini and GLM usage screens and updates data.json.

  python reader/read_usage.py login            sign in once (opens a real Chrome window)
  python reader/read_usage.py run              read everything, write data.json, git push
  python reader/read_usage.py run --no-push    same, but leave the push to you

Plain regex readers come first. If one cannot find its numbers and GLM_API_KEY is
set, the page text goes to GLM, which hands the numbers back as JSON.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data.json"
PROFILE = Path(os.environ.get("USAGE_PROFILE", Path.home() / ".usage-board-profile"))
HEADLESS = os.environ.get("HEADLESS", "1") == "1"

PAGES = {
    # claude.ai blocks automated browsers, so Claude is refreshed separately into claude.json.
    "chatgpt": ("https://chatgpt.com/codex/settings/usage", "%"),
    "gemini": ("https://gemini.google.com/usage", "Weekly limit"),
    "glm": ("https://z.ai/manage-apikey/coding-plan/personal/usage", "Weekly Quota"),
}
SIGNED_OUT_HINTS = ("/auth/login", "accounts.google.com", "/login", "signin")

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def ms(dt):
    return int(dt.timestamp() * 1000)


# ---------- time helpers (all local time, same as the pages show) ----------

def next_clock(hour, minute, now):
    cand = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return cand if cand > now else cand + timedelta(days=1)


def ampm(text):
    m = re.match(r"(\d{1,2}):(\d{2})\s*([AP]M)", text.strip(), re.I)
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3).upper()
    if ap == "PM" and h != 12:
        h += 12
    if ap == "AM" and h == 12:
        h = 0
    return h, mi


def next_weekday(name, hour, minute, now):
    target = DAYS.index(name.lower())
    cand = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    cand += timedelta(days=(target - cand.weekday()) % 7)
    return cand if cand > now else cand + timedelta(days=7)


# ---------- regex readers: return a list of meters, or None ----------

def parse_claude(text, now):
    s = re.search(r"Current session\s*Resets at\s*(\d{1,2}:\d{2}\s*[AP]M)\s*(\d{1,3})%\s*used", text, re.I | re.S)
    w = re.search(r"This week\s*Resets\s*(\w+)\s*(\d{1,2}:\d{2}\s*[AP]M)\s*(\d{1,3})%\s*used", text, re.I | re.S)
    if not (s and w) or w.group(1).lower() not in DAYS:
        return None
    sh, sm = ampm(s.group(1))
    wh, wm = ampm(w.group(2))
    return [
        {"id": "cl5", "label": "Session", "hours": 5, "used": int(s.group(2)), "resetAt": ms(next_clock(sh, sm, now))},
        {"id": "clw", "label": "Weekly", "hours": 168, "used": int(w.group(3)), "resetAt": ms(next_weekday(w.group(1), wh, wm, now))},
    ]


def parse_gemini(text, now):
    c = re.search(r"Current usage\s*(\d{1,3})%\s*used\s*Resets at\s*(\d{1,2}):(\d{2})", text, re.I | re.S)
    w = re.search(r"Weekly limit\s*Resets on\s*(\d{1,2})\s+([A-Za-z]{3})\w*\s+at\s+(\d{1,2}):(\d{2})\s*(\d{1,3})%\s*used", text, re.I | re.S)
    if not (c and w):
        return None
    wd = datetime.strptime("%s %s %d %s:%s" % (w.group(1), w.group(2).title(), now.year, w.group(3), w.group(4)), "%d %b %Y %H:%M")
    if wd < now - timedelta(days=1):
        wd = wd.replace(year=now.year + 1)
    return [
        {"id": "ge5", "label": "Current usage", "hours": 5, "used": int(c.group(1)), "resetAt": ms(next_clock(int(c.group(2)), int(c.group(3)), now))},
        {"id": "gew", "label": "Weekly", "hours": 168, "used": int(w.group(5)), "resetAt": ms(wd)},
    ]


def parse_glm(text, now, previous=None):
    f = re.search(r"5 Hours Quota\s*(\d{1,3})\s*%\s*Used", text, re.I | re.S)
    w = re.search(r"Weekly Quota\s*(\d{1,3})\s*%\s*Used\s*Reset Time:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", text, re.I | re.S)
    if not (f and w):
        return None
    # Z.ai does not print the 5-hour reset time: keep the old one while it is still ahead, else estimate.
    reset5 = ms(now + timedelta(hours=5))
    for m in (previous or []):
        if m.get("id") == "gl5" and m.get("resetAt", 0) > ms(now):
            reset5 = m["resetAt"]
    return [
        {"id": "gl5", "label": "5-hour quota", "hours": 5, "used": int(f.group(1)), "resetAt": reset5},
        {"id": "glw", "label": "Weekly quota", "hours": 168, "used": int(w.group(1)),
         "resetAt": ms(datetime.strptime(w.group(2), "%Y-%m-%d %H:%M"))},
    ]


READERS = {"claude": parse_claude, "gemini": parse_gemini, "glm": parse_glm}


# ---------- GLM fallback ----------

def ask_glm(provider, text, now):
    key = os.environ.get("GLM_API_KEY")
    if not key:
        return None
    import requests
    prompt = (
        "Below is the text of the %s usage-limits page. Current local time is %s (%s).\n"
        "Return ONLY JSON like {\"meters\":[{\"label\":\"Session\",\"hours\":5,\"used\":10,\"resets_at\":\"YYYY-MM-DD HH:MM\"}]}\n"
        "One entry per limit window. hours is 5, 24 or 168. used is the percent used (0-100; if the page shows percent "
        "remaining, convert it). resets_at is local time. If a number is not on the page, leave that window out.\n\n%s"
        % (provider, now.strftime("%Y-%m-%d %H:%M"), now.strftime("%A"), text[:8000])
    )
    r = requests.post(
        os.environ.get("GLM_URL", "https://api.z.ai/api/coding/paas/v4/chat/completions"),
        headers={"Authorization": "Bearer " + key},
        json={"model": os.environ.get("GLM_MODEL", "glm-5.3-flash"), "temperature": 0,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=90,
    )
    r.raise_for_status()
    body = re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S)
    meters = []
    for i, m in enumerate(json.loads(body.group(0))["meters"]):
        used = float(m["used"])
        if not 0 <= used <= 100:
            raise ValueError("GLM returned an out-of-range percentage")
        meters.append({
            "id": "%s%d" % (provider[:2], i), "label": str(m["label"])[:30], "hours": int(m["hours"]),
            "used": round(used),
            "resetAt": ms(datetime.strptime(m["resets_at"], "%Y-%m-%d %H:%M")),
        })
    return meters or None


# ---------- browser ----------

def launch(p, headless):
    PROFILE.mkdir(parents=True, exist_ok=True)
    return p.chromium.launch_persistent_context(
        str(PROFILE), channel="chrome", headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )


def read_page(ctx, url, ready_text):
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_function("t => document.body.innerText.includes(t)", arg=ready_text, timeout=25000)
        except Exception:
            pass
        page.wait_for_timeout(1500)
        return page.inner_text("body"), page.url
    finally:
        page.close()


def cmd_login():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = launch(p, headless=False)
        for name, (url, _) in PAGES.items():
            ctx.new_page().goto(url)
        input("Sign in to each tab (ChatGPT, Gemini, Z.ai), then press Enter here to save the session... ")
        # Closing can hang if a tab is stuck, so give it 15 seconds and then exit anyway.
        import threading
        threading.Timer(15, lambda: os._exit(0)).start()
        try:
            ctx.close()
        except Exception:
            pass


def cmd_run(push):
    from playwright.sync_api import sync_playwright
    if push:
        subprocess.run(["git", "pull", "--rebase", "--autostash"], cwd=ROOT, check=False)
    now = datetime.now()
    data = json.loads(DATA.read_text())
    by_id = {p["id"]: p for p in data["providers"]}
    with sync_playwright() as p:
        ctx = launch(p, headless=HEADLESS)
        for pid, (url, ready) in PAGES.items():
            prov = by_id[pid]
            try:
                text, final_url = read_page(ctx, url, ready)
                if any(h in final_url for h in SIGNED_OUT_HINTS):
                    raise RuntimeError("signed out; run the login command again")
                reader = READERS.get(pid)
                meters = None
                if reader:
                    meters = reader(text, now, prov["meters"]) if pid == "glm" else reader(text, now)
                if not meters:
                    meters = ask_glm(pid, text, now)
                    how = "read by GLM"
                else:
                    how = None
                if not meters:
                    raise RuntimeError("could not find the numbers on the page")
                prov["meters"] = meters
                prov["checkedAt"] = ms(now)
                prov.pop("note", None)
                if how:
                    prov["note"] = "This reading was extracted by GLM because the usual reader did not match."
                if pid == "glm":
                    prov["note"] = "Z.ai does not show when the 5-hour window resets, so that time is an estimate."
                if prov.get("plan") == "Not read yet":
                    prov["plan"] = {"chatgpt": "ChatGPT plan"}.get(pid, prov["plan"])
                print("ok     ", pid, [(m["label"], m["used"]) for m in meters])
            except Exception as e:  # keep the previous reading, say so on the card
                prov["note"] = "Last attempt failed (%s). Showing the previous reading." % str(e)[:120]
                print("FAILED ", pid, e, file=sys.stderr)
        ctx.close()
    data["updatedAt"] = ms(now)
    DATA.write_text(json.dumps(data, indent=2) + "\n")
    ok_count = sum(1 for p in data["providers"] if p.get("checkedAt") == ms(now))
    if push:
        run = lambda *a: subprocess.run(a, cwd=ROOT, check=True)
        run("git", "add", "data.json")
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode != 0:
            run("git", "commit", "-m", "Usage readings " + now.strftime("%Y-%m-%d %H:%M"))
            run("git", "push")
    return ok_count


if __name__ == "__main__":
    args = sys.argv[1:]
    if sys.stdout is None or sys.stderr is None:  # scheduled run with no console
        log = open(ROOT / "reader" / "last_run.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
        print("---", datetime.now().isoformat(timespec="seconds"))
    if args[:1] == ["login"]:
        cmd_login()
    elif args[:1] == ["run"]:
        sys.exit(0 if cmd_run(push="--no-push" not in args) else 1)
    else:
        print(__doc__)
