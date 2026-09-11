# Nursing Home Email Finder

This project finds public contact emails for U.S. nursing homes by searching the web with the Brave Search API.

It starts from a CMS nursing-home list, removes duplicate facilities, then looks up each facility one by one. Results are split into two files:

| File | Contents |
|---|---|
| `nursing_homes_with_emails.csv` | Facilities where at least one email was found |
| `nursing_homes_no_email.csv` | Facilities searched with no usable email found |

The script is **resumable**: if you stop and run it again, it skips any facility already listed in either output file.

---

## What’s in this folder

| File | Purpose |
|---|---|
| `Nursery Homes.csv` | Original CMS source list |
| `deduplicate_nursing_homes.py` | Builds a unique facility list |
| `nursing_homes_deduplicated.csv` | Deduplicated input used by the email finder |
| `find_nursing_home_emails.py` | Main email-search script |
| `run_finder.sh` | Easy launcher (loads `.env`, runs the script) |
| `.env` | Your Brave API key (do **not** share this file) |
| `brave_request_tracker.json` | Counts Brave API requests used so far |
| `nursing_homes_with_emails.csv` | Output: emails found |
| `nursing_homes_no_email.csv` | Output: no email found |
| `requirements.txt` | Python dependencies |

---

## Prerequisites

- macOS or Linux
- Python 3.10+ (3.11+ recommended)
- A Brave Search API key (see below)

---

## 1. Get a Brave Search API key

1. Go to the [Brave Search API dashboard](https://api-dashboard.search.brave.com/) and create an account.
2. Verify your email, then log in.
3. Open **Plans**, choose a plan, and activate it.  
   Brave currently requires a card to activate a plan. Plans typically include a small monthly credit; check the dashboard for current pricing. To avoid unexpected charges, set a monthly spending/credit limit in the dashboard (for example, equal to the included credit).
4. Go to **API Keys** → **Add API Key** → copy the key.
5. Keep the key private. Do not commit it to git or email it in plain text if you can avoid it.

Official quickstart: https://api-dashboard.search.brave.com/documentation/quickstart

---

## 2. One-time setup

In Terminal, go to this project folder:

```bash
cd "/path/to/nursing_home_email_project"
```

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in this folder with your key (one line):

```bash
export BRAVE_API_KEY=paste_your_key_here
```

Example:

```bash
export BRAVE_API_KEY=BSAXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

---

## 3. Run the email finder

With the virtual environment activated:

```bash
chmod +x run_finder.sh
./run_finder.sh
```

To limit the run to specific states (2-letter codes), pass `--states`:

```bash
./run_finder.sh --states IL
./run_finder.sh --states IL IN WI
./run_finder.sh --states IL,IN,WI
```

If you omit `--states`, it processes all states.

Or run Python directly:

```bash
export BRAVE_API_KEY="$(python3 -c "from pathlib import Path; s=Path('.env').read_text().strip(); print(s.split('=',1)[1].strip())")"
python -u find_nursing_home_emails.py
python -u find_nursing_home_emails.py --states IL WI
```

### What you’ll see while it runs

Progress lines like:

```text
[2208/14699] SOME NURSING HOME (FL) | Skipped already done: 1605 | Brave requests used: 500/1000
```

- Facilities with emails are appended to `nursing_homes_with_emails.csv`
- Facilities without emails are appended to `nursing_homes_no_email.csv`
- There is a short pause between requests to avoid rate limits

### Request limit (important)

The script stops automatically at **1000 Brave requests** (tracked in `brave_request_tracker.json`). That is an intentional safety cap so a single run does not burn through a large quota.

When you hit the cap, you’ll see:

```text
Brave request limit reached (1000/1000). Stop now and provide a new API key.
```

To continue later with a **new key / fresh quota**:

1. Put the new key in `.env`
2. Reset the counter:

```bash
echo '{
  "request_count": 0
}' > brave_request_tracker.json
```

3. Run `./run_finder.sh` again — it will resume where it left off.

---

## Optional: rebuild the deduplicated list

Only needed if you replace `Nursery Homes.csv` with a newer CMS export:

```bash
python deduplicate_nursing_homes.py
```

This overwrites `nursing_homes_deduplicated.csv`.

---

## Notes for whoever receives this

- Existing `nursing_homes_with_emails.csv` and `nursing_homes_no_email.csv` already contain progress from earlier runs. Leave them in place if you want to continue; delete them only if you want to start over from scratch.
- Emails are extracted from Brave search result text. They may be general contact addresses, not always a specific administrator.
- Some facilities will never yield a public email; those correctly end up in `nursing_homes_no_email.csv`.
- Do not share your `.env` file when sending this project to others.
