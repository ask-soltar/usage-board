# AI Usage Limits

A static page (`index.html`) that shows `data.json`, plus a script on your PC that refreshes `data.json` from the four usage screens and pushes it.

```
your PC (every few hours)           GitHub                     the live site
reader/read_usage.py  ── push ──▶  data.json  ── Pages ──▶  index.html reads it
```

## Quick start (Windows)

Open PowerShell and paste:

```
git clone https://github.com/ask-soltar/usage-board $HOME\usage-board; powershell -ExecutionPolicy Bypass -File $HOME\usage-board\setup.ps1
```

`setup.ps1` checks Python and Chrome, installs the packages, optionally saves your Z.ai key, opens Chrome so you can sign in to the four sites, does a first reading and push, and schedules a refresh every 2 hours. The manual steps below are the same thing done by hand.

## One-time setup (manual)

1. **Make the repo.** On GitHub create a new **public** repo (GitHub Pages is free only for public repos), e.g. `usage-board`. Upload everything in this folder, or clone it empty and copy the files in.
2. **Turn on Pages.** Repo → Settings → Pages → Source: "Deploy from a branch", branch `main`, folder `/ (root)`. Your site will be at `https://<your-username>.github.io/usage-board/`.
3. **Clone it on the PC** that will run the reader, and make sure `git push` works there without asking for a password (GitHub Desktop, a credential manager, or an SSH key).
4. **Install the reader's tools** (needs Python 3 and Google Chrome):
   ```
   pip install playwright requests
   ```
   Chrome itself is used, so there is no extra browser download.
5. **Sign in once.** This opens a separate Chrome profile just for this tool:
   ```
   python reader/read_usage.py login
   ```
   Log in to Claude, ChatGPT, Gemini and Z.ai in the four tabs, then press Enter in the terminal. You type the passwords yourself; the script never sees them, only the saved session.
6. **Test a run without pushing:**
   ```
   python reader/read_usage.py run --no-push
   ```
   You should see an `ok` line for each provider. Open `data.json` to check the numbers against the apps.
7. **Optional GLM fallback.** If a page changes layout, the script can ask GLM to read it. Put your Z.ai API key in an environment variable called `GLM_API_KEY` on the PC (never in the repo, never in chat). `GLM_MODEL` defaults to `glm-5.3-flash`; change it if Z.ai lists a different model name for your plan.

## Schedule it

Percentages move fast, so every 2 hours is better than once a day. It costs nothing.

- **Windows:** `schtasks /Create /SC HOURLY /MO 2 /TN "UsageBoard" /TR "python C:\path\to\usage-board\reader\read_usage.py run"`
- **Mac / Linux (cron):** `0 */2 * * * cd /path/to/usage-board && python3 reader/read_usage.py run`

The PC has to be on and signed in for the run to happen.

## If something goes wrong

- **A card says "Last attempt failed":** the script keeps the previous reading and says why. "Signed out" means run the `login` command again.
- **Google or ChatGPT blocks the automated sign-in:** set `HEADLESS=0` so a visible window opens, and do the login with `login` slowly like a normal visit.
- **Check the readers:** `python reader/test_parsers.py` re-runs the page-text checks.

## Notes

- The Claude, Gemini and GLM readers were built from the page text as it looked on Oct 13, 2026. The ChatGPT page had not been read yet, so it relies on the GLM fallback until you check it.
- The site is public. It shows only percentages and reset times, no account details.
- Z.ai does not print the 5-hour reset time, so that one is an estimate.
