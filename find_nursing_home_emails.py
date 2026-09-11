import argparse
import http.client
import json
import os
import random
import re
import time
from pathlib import Path
from typing import Iterable, Optional, Set
from urllib import error, parse, request

import pandas as pd

_SCRIPT_DIR = Path(__file__).resolve().parent
# Repo root used only to migrate an older tracker path (cwd-relative).
_LEGACY_REQUEST_TRACKER = _SCRIPT_DIR.parent / "brave_request_tracker.json"

INPUT_CSV = Path("nursing_homes_deduplicated.csv")
WITH_EMAILS_CSV = Path("nursing_homes_with_emails.csv")
NO_EMAIL_CSV = Path("nursing_homes_no_email.csv")
REQUEST_TRACKER_FILE = _SCRIPT_DIR / "brave_request_tracker.json"
BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
MAX_RETRIES = 3
REQUEST_LIMIT = 1000
STARTING_BRAVE_REQUEST_COUNT = 391

INVALID_DOMAIN_SNIPPETS = {
    "@example.com",
    "@sentry.io",
    "@domain.com",
}
PLACEHOLDER_PATTERNS = (
    "example",
    "placeholder",
    "yourname",
    "youremail",
    "email@",
    "name@",
    "test@",
)


class RequestLimitReached(Exception):
    """Raised when Brave request usage reaches the configured limit."""


def _migrate_legacy_tracker_if_needed() -> None:
    if REQUEST_TRACKER_FILE.exists():
        return
    if _LEGACY_REQUEST_TRACKER.exists():
        REQUEST_TRACKER_FILE.write_text(
            _LEGACY_REQUEST_TRACKER.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        try:
            _LEGACY_REQUEST_TRACKER.unlink()
        except OSError:
            pass


def load_request_count() -> int:
    _migrate_legacy_tracker_if_needed()
    if not REQUEST_TRACKER_FILE.exists():
        save_request_count(STARTING_BRAVE_REQUEST_COUNT)
        return STARTING_BRAVE_REQUEST_COUNT

    try:
        payload = json.loads(REQUEST_TRACKER_FILE.read_text(encoding="utf-8"))
        return int(payload.get("request_count", STARTING_BRAVE_REQUEST_COUNT))
    except (json.JSONDecodeError, OSError, ValueError):
        save_request_count(STARTING_BRAVE_REQUEST_COUNT)
        return STARTING_BRAVE_REQUEST_COUNT


def save_request_count(count: int) -> None:
    REQUEST_TRACKER_FILE.write_text(
        json.dumps({"request_count": count}, indent=2),
        encoding="utf-8",
    )


def increment_request_count_or_raise(count: int) -> int:
    if count >= REQUEST_LIMIT:
        raise RequestLimitReached(
            f"Brave request limit reached ({count}/{REQUEST_LIMIT}). "
            "Stop now and provide a new API key."
        )
    updated_count = count + 1
    save_request_count(updated_count)
    return updated_count


def load_processed_ccns(paths: Iterable[Path]) -> Set[str]:
    processed: Set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        try:
            df = pd.read_csv(path, dtype=str, usecols=["CMS Certification Number (CCN)"])
        except ValueError:
            # File exists but has unexpected headers; skip safely.
            continue
        processed.update(df["CMS Certification Number (CCN)"].dropna().astype(str).str.strip())
    return processed


def is_valid_email(candidate: str) -> bool:
    email = candidate.strip().lower()
    if not email:
        return False
    if any(snippet in email for snippet in INVALID_DOMAIN_SNIPPETS):
        return False
    if any(pattern in email for pattern in PLACEHOLDER_PATTERNS):
        return False
    return True


def extract_emails_from_payload(payload: dict) -> list[str]:
    raw_blob = json.dumps(payload, ensure_ascii=False)
    found = EMAIL_REGEX.findall(raw_blob)

    valid = []
    seen = set()
    for email in found:
        cleaned = email.strip(".,;:!?()[]{}<>\"'").lower()
        if cleaned in seen:
            continue
        if is_valid_email(cleaned):
            seen.add(cleaned)
            valid.append(cleaned)
    return valid


def search_with_retries(query: str, api_key: str, request_count: int) -> tuple[list[str], int]:
    params = parse.urlencode({"q": query})
    url = f"{BRAVE_API_URL}?{params}"

    for attempt in range(1, MAX_RETRIES + 1):
        request_count = increment_request_count_or_raise(request_count)
        req = request.Request(
            url,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
            },
            method="GET",
        )

        try:
            with request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
                return extract_emails_from_payload(data), request_count
        except error.HTTPError as exc:
            if exc.code == 429 and attempt < MAX_RETRIES:
                backoff_seconds = 2 ** (attempt - 1)
                print(f"Rate limited (429). Retrying in {backoff_seconds}s (attempt {attempt}/{MAX_RETRIES})...")
                time.sleep(backoff_seconds)
                continue
            if exc.code == 429:
                print(f"Rate limited (429) after {MAX_RETRIES} attempts; marking as no email found.")
                return [], request_count
            print(f"HTTP error {exc.code} for query: {query}")
            return [], request_count
        except (
            error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            http.client.IncompleteRead,
            ConnectionError,
            OSError,
        ) as exc:
            if attempt < MAX_RETRIES:
                backoff_seconds = 2 ** (attempt - 1)
                print(
                    f"Transport/read error for query '{query}' ({exc!r}). "
                    f"Retrying in {backoff_seconds}s (attempt {attempt}/{MAX_RETRIES})..."
                )
                time.sleep(backoff_seconds)
                continue
            print(f"Request/parsing error for query '{query}': {exc}")
            return [], request_count

    return [], request_count


def append_row(path: Path, row_df: pd.DataFrame) -> None:
    write_header = not path.exists()
    row_df.to_csv(path, mode="a", header=write_header, index=False)


def parse_states_arg(raw_states: Optional[list[str]]) -> Optional[Set[str]]:
    """Return an uppercase set of state codes, or None for all states."""
    if not raw_states:
        return None

    states: Set[str] = set()
    for item in raw_states:
        for part in item.replace(";", ",").split(","):
            code = part.strip().upper()
            if code:
                states.add(code)
    return states or None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find public contact emails for nursing homes via Brave Search. "
            "Optionally limit to one or more states; omit --states to process all."
        )
    )
    parser.add_argument(
        "--states",
        "-s",
        nargs="+",
        metavar="STATE",
        help=(
            "Optional 2-letter state codes to process (e.g. IL or IL IN WI). "
            "Comma-separated values also work (e.g. IL,IN,WI). "
            "If omitted, all states are processed."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected_states = parse_states_arg(args.states)

    api_key = os.environ.get("BRAVE_API_KEY")
    if not api_key:
        raise RuntimeError("BRAVE_API_KEY environment variable is not set.")

    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_CSV}")

    df = pd.read_csv(INPUT_CSV, dtype=str).fillna("")
    available_states = sorted(
        {str(s).strip().upper() for s in df["State"].tolist() if str(s).strip()}
    )

    if selected_states is not None:
        unknown = sorted(selected_states - set(available_states))
        if unknown:
            raise SystemExit(
                f"Unknown state code(s): {', '.join(unknown)}. "
                f"Available: {', '.join(available_states)}"
            )
        df = df[df["State"].astype(str).str.strip().str.upper().isin(selected_states)].copy()
        print(f"Filtering to states: {', '.join(sorted(selected_states))} ({len(df)} facilities)")
    else:
        print(f"Processing all states ({len(df)} facilities)")

    total_rows = len(df)

    processed_ccns = load_processed_ccns([WITH_EMAILS_CSV, NO_EMAIL_CSV])
    request_count = load_request_count()
    skipped_count = 0
    processed_count = 0

    for _, row in df.iterrows():
        ccn = str(row["CMS Certification Number (CCN)"]).strip()
        provider_name = str(row["Provider Name"]).strip()
        city = str(row["City/Town"]).strip()
        state = str(row["State"]).strip()

        if ccn in processed_ccns:
            skipped_count += 1
            processed_count += 1
            continue

        query = f"\"{provider_name}\" \"{city}\" \"{state}\" email contact"
        try:
            emails, request_count = search_with_retries(query, api_key=api_key, request_count=request_count)
        except RequestLimitReached as exc:
            print(exc)
            print(
                f"Stopped at Brave request count {request_count}/{REQUEST_LIMIT}. "
                "Please provide a new API key before continuing."
            )
            break
        email_str = ",".join(emails)

        output_row = row.to_dict()
        output_row["email"] = email_str
        output_df = pd.DataFrame([output_row])

        if emails:
            append_row(WITH_EMAILS_CSV, output_df)
        else:
            append_row(NO_EMAIL_CSV, output_df)

        processed_ccns.add(ccn)
        processed_count += 1
        print(
            f"[{processed_count}/{total_rows}] {provider_name} ({state}) | "
            f"Skipped already done: {skipped_count} | "
            f"Brave requests used: {request_count}/{REQUEST_LIMIT}"
        )

        time.sleep(random.uniform(1, 2))

    print(
        "Completed. "
        f"Processed {processed_count}/{total_rows}. "
        f"Skipped already done: {skipped_count}. "
        f"Brave requests used: {request_count}/{REQUEST_LIMIT}."
    )


if __name__ == "__main__":
    main()
