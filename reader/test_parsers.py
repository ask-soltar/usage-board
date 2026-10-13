"""Checks the regex readers against page text captured on Oct 13, 2026."""
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import read_usage as r

now = datetime(2026, 10, 13, 11, 20)

GEMINI = """Usage limits
PLUS

Updated just now

Current usage

0% used

Resets at 13:05

Weekly limit

Resets on 18 Oct at 09:05

2% used"""

GLM = """Usage
Last refresh time: 2026-10-13 11:15:22
5 Hours Quota
1
%
Used
Weekly Quota
1
%
Used
Reset Time: 2026-10-19 10:51
MCP Quota
0
%
Used
Reset Time: 2026-10-22 10:51"""

# Claude's modal reads: label, reset line, percent (layout as seen on screen).
CLAUDE = """Your usage Pro
Heads up. At this pace you'll run out Thursday afternoon, before Sunday's reset.
Current session
Resets at 2:30 PM
10% used
This week
Resets Sunday 3:00 AM
53% used"""


GEMINI_US = """Plus
Usage limits
PLUS
Your plan's limits determine how much you can use Gemini over time.
Current usage
65% used
Resets at 1:10 PM
Weekly limit
Resets Oct 20 at 11:10 AM
2% used
Get 2x more usage with AI Pro"""

CHATGPT = """Piano Keys Explained
2% usage remaining
5h
2% remaining
Resets at 12:17 PM
Add credits"""


def show(ms):
    return datetime.fromtimestamp(ms / 1000).strftime("%a %Y-%m-%d %H:%M")


for name, fn, text in [("claude", r.parse_claude, CLAUDE), ("gemini", r.parse_gemini, GEMINI), ("glm", r.parse_glm, GLM)]:
    out = fn(text, now)
    assert out, name + " did not parse"
    for m in out:
        print(name, m["label"], m["used"], "%", "resets", show(m["resetAt"]))

c = r.parse_claude(CLAUDE, now)
assert [m["used"] for m in c] == [10, 53] and show(c[1]["resetAt"]).startswith("Sun 2026-10-18 03:00")
g = r.parse_gemini(GEMINI, now)
assert [m["used"] for m in g] == [0, 2] and show(g[0]["resetAt"]).endswith("13:05") and show(g[1]["resetAt"]).startswith("Sun 2026-10-18 09:05")
z = r.parse_glm(GLM, now)
assert [m["used"] for m in z] == [1, 1] and show(z[1]["resetAt"]).endswith("2026-10-19 10:51")
assert r.parse_gemini("nothing here", now) is None
gu = r.parse_gemini(GEMINI_US, now)
assert [m["used"] for m in gu] == [65, 2], gu
assert show(gu[0]["resetAt"]).endswith("13:10") and show(gu[1]["resetAt"]) .startswith("Tue 2026-10-20 11:10"), [show(m["resetAt"]) for m in gu]
cg = r.parse_chatgpt(CHATGPT, datetime(2026, 10, 13, 12, 6))
assert len(cg) == 1 and cg[0]["used"] == 98 and show(cg[0]["resetAt"]).endswith("12:17"), cg
assert r.parse_chatgpt("nothing", now) is None
print("all parser checks passed")
