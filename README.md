# Daily Brief

Sends you a daily 9 AM email with: one algorithm + sample problem, a few GRE
words, one CS concept, and an industry/interview tip. Tracks what's already
been sent so it doesn't repeat.

**Cost: $0.** Everything here runs on free tiers — no subscription, no
credit card required anywhere in this setup.

## How it works

- `daily_brief.py` calls the Gemini API (free tier) for content, formats it, and emails it.
- `history.json` stores everything sent so far (algorithm names, GRE words,
  CS concepts, tip titles). Each prompt tells Claude to avoid these.
- `.github/workflows/daily-brief.yml` runs the script every day at 9:00 AM IST
  via GitHub Actions — no need to keep your laptop on.
- After each successful send, the workflow commits the updated `history.json`
  back to the repo, so dedup persists across runs.

## Setup (10 minutes)

1. **Create a private GitHub repo** and push this folder to it.
   ```
   cd daily-brief
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin <your-repo-url>
   git push -u origin main
   ```

2. **Get a free Gemini API key**: go to aistudio.google.com/apikey, sign in
   with any Google account, click "Create API key". No credit card needed.
   The free tier gives you 250 requests/day on `gemini-2.5-flash` — this
   script uses 1/day, so you'll never come close to the limit.

3. **Set up a Gmail app password** (or use any SMTP provider):
   - Go to Google Account → Security → 2-Step Verification → App passwords.
   - Generate one for "Mail". Copy the 16-character password.

4. **Add repo secrets**: repo → Settings → Secrets and variables → Actions →
   New repository secret. Add all of these:
   - `GEMINI_API_KEY`
   - `SMTP_HOST` → `smtp.gmail.com`
   - `SMTP_PORT` → `587`
   - `SMTP_USER` → your Gmail address
   - `SMTP_PASS` → the app password from step 3
   - `MAIL_TO` → where you want the brief sent (can be the same address)

5. **Test it**: go to the repo's Actions tab → "Daily Brief" workflow →
   "Run workflow" to trigger it manually. Check your inbox, then check that
   `history.json` got updated with a commit.

6. Done — it'll now fire automatically every day at 9:00 AM IST.

## Adjusting the schedule

The cron line in the workflow (`30 3 * * *`) is in UTC. 9:00 AM IST is
3:30 AM UTC. If you ever change timezone, recalculate and update that line.

## Local testing

You can run it locally before pushing, by exporting the same env vars:
```
export GEMINI_API_KEY=...
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=you@gmail.com
export SMTP_PASS=your_app_password
export MAIL_TO=you@gmail.com
python3 daily_brief.py
```
