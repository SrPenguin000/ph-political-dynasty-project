import os
import sys
import json
import requests
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from datasets import load_dataset

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]

raw_env = os.getenv("DATA_RAW_DIR", "data/raw").lstrip("/\\")
if raw_env.startswith("opt/airflow/"):
    raw_env = raw_env.replace("opt/airflow/", "")

RAW_DIR = PROJECT_ROOT / raw_env
RAW_DIR.mkdir(parents=True, exist_ok=True)
print(f"Target directory: {RAW_DIR}")

ALLOW_FALLBACK = os.getenv("ALLOW_FALLBACK", "0") == "1"
FORCE_DOWNLOAD = os.getenv("FORCE_DOWNLOAD", "0") == "1"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _valid_pdf(path, min_bytes=10_000):
    """True if path exists, is large enough, and starts with the PDF magic bytes."""
    if not path.exists() or path.stat().st_size < min_bytes:
        return False
    with open(path, "rb") as f:
        return f.read(4) == b"%PDF"


def ingest_huggingface():
    """Pulls the primary Parquet dataset from Hugging Face."""
    print("Ingesting BetterGovPH from Hugging Face...")
    hf_url = os.getenv("PRIMARY_HF_DATASET")
    if not hf_url:
        raise RuntimeError("PRIMARY_HF_DATASET is not set in .env")

    repo_id = hf_url.replace("https://huggingface.co/datasets/", "")

    for table in ("persons", "memberships"):
        print(f" -> Downloading '{table}' table...")
        ds = load_dataset(repo_id, table, split="train")
        if len(ds) == 0:
            raise RuntimeError(f"HF table '{table}' is empty")
        ds.to_parquet(RAW_DIR / f"hf_{table}.parquet")
        print(f"    {len(ds):,} rows saved")


def ingest_openhalalan():
    """Downloads OpenHalalan release files (winners 2001-2025; optional vote counts)."""
    print("Ingesting OpenHalalan...")
    base = "https://github.com/RobertRLeung/OpenHalalan/releases/download/data-latest"
    winners_url = os.getenv("OPENHALALAN_WINNERS_URL", f"{base}/NLE_Winners_2004-2025.csv")
    votes_url = os.getenv("OPENHALALAN_VOTES_URL", f"{base}/NLE_Vote_Counts_2007-2025.csv.gz")

    def download(url, dest):
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=300, stream=True, allow_redirects=True)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} for {url}")
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)

    try:
        winners_path = RAW_DIR / "openhalalan_winners.csv"
        download(winners_url, winners_path)
        n = len(pd.read_csv(winners_path, low_memory=False))
        if n < 1000:
            raise RuntimeError(f"Only {n} rows in winners file; expected a real dataset")
        print(f"OpenHalalan winners saved ({n:,} rows).")

        if os.getenv("OPENHALALAN_VOTES", "0") == "1":
            download(votes_url, RAW_DIR / "openhalalan_vote_counts.csv.gz")
            print("OpenHalalan vote counts saved.")
    except Exception as e:
        if not ALLOW_FALLBACK:
            raise RuntimeError(f"OpenHalalan ingest failed: {e}") from e
        print(f"Download failed ({e}). Writing FALLBACK stub...")
        pd.DataFrame({
            "candidate_id": [101, 102],
            "name": ["Juan Marcos", "Maria Singson"],
            "position": ["Mayor", "Governor"],
            "location": ["Manila", "Ilocos Sur"],
            "election_year": [2016, 2016],
        }).to_csv(RAW_DIR / "openhalalan_winners_FALLBACK.csv", index=False)


def ingest_psa_poverty():
    """Gets PSA provincial poverty data: keeps a manual download (PDF/CSV/JSON), else tries the OpenSTAT API."""
    print("Ingesting PSA poverty data...")
    json_path = RAW_DIR / "psa_poverty.json"
    csv_path = RAW_DIR / "psa_poverty.csv"
    pdf_path = RAW_DIR / "psa_poverty.pdf"

    if not FORCE_DOWNLOAD:
        if _valid_pdf(pdf_path):
            print(f"Found manual download {pdf_path.name}. Keeping it.")
            return
        if csv_path.exists() and csv_path.stat().st_size > 500:
            print(f"Found manual download {csv_path.name}. Keeping it.")
            return
        if json_path.exists() and json_path.stat().st_size > 500:
            try:
                json.loads(json_path.read_text(encoding="utf-8"))
                print(f"Found existing {json_path.name}. Keeping it.")
                return
            except ValueError:
                print(f"Existing {json_path.name} is not valid JSON; re-downloading.")

    api_url = os.environ.get(
        "TERTIARY_SOURCE_URL",
        "https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/DB__1E/DB__1E__FY/0011E3DF010.px",
    )
    payload = {"query": [], "response": {"format": "json-stat"}}

    try:
        response = requests.post(api_url, json=payload, headers=BROWSER_HEADERS, timeout=30)
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")
        data = response.json()
        if len(response.text) < 500:
            raise RuntimeError("Response too small to be a real dataset")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        print("PSA Poverty JSON saved.")
    except Exception as e:
        if ALLOW_FALLBACK:
            print(f"PSA API failed ({e}). Writing FALLBACK stub...")
            with open(RAW_DIR / "psa_poverty_FALLBACK.json", "w", encoding="utf-8") as f:
                f.write('{"dataset": {"dimension": {"region": {"category": {"index": {"NCR": 0}}}}}}')
            return
        raise RuntimeError(
            f"PSA ingest failed: {e}. Download the data manually and save it in {RAW_DIR} as "
            f"{pdf_path.name} (PSA Official Poverty Statistics publication), "
            f"{csv_path.name} or {json_path.name} (OpenSTAT export)."
        ) from e


def ingest_historical_roster():
    """Gets the House roster PDF: keeps a local copy, else tries the original URL, then the Wayback Machine."""
    print("Ingesting Historical Roster PDF...")
    dest = RAW_DIR / "roster_legislators.pdf"

    if _valid_pdf(dest) and not FORCE_DOWNLOAD:
        print(f"Found existing roster PDF ({dest.stat().st_size / 1024:.0f} KB). Keeping it.")
        return

    pdf_url = os.environ.get(
        "HISTORICAL_ROSTER_URL",
        "https://hrep-website.s3.ap-southeast-1.amazonaws.com/download/docs/roster-legislators.pdf",
    )
    candidates = [pdf_url, f"https://web.archive.org/web/2023id_/{pdf_url}"]
    headers = {**BROWSER_HEADERS, "Referer": "https://www.congress.gov.ph/", "Accept": "application/pdf,*/*"}

    errors = []
    for url in candidates:
        try:
            response = requests.get(url, headers=headers, timeout=120, allow_redirects=True)
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            content = response.content
            if not content.startswith(b"%PDF") or len(content) < 10_000:
                raise RuntimeError(f"Not a valid PDF ({len(content)} bytes)")
            dest.write_bytes(content)
            print(f"Historical Roster PDF saved from {url} ({len(content) / 1024:.0f} KB).")
            return
        except Exception as e:
            errors.append(f"{url} -> {e}")

    raise RuntimeError(
        "Roster PDF ingest failed:\n  " + "\n  ".join(errors)
        + f"\nDownload it manually (e.g. via the Wayback Machine) and save it to {dest}"
    )


if __name__ == "__main__":
    print("Starting Raw Data Ingestion Pipeline...")

    steps = [
        ("huggingface", ingest_huggingface),
        ("openhalalan", ingest_openhalalan),
        ("psa_poverty", ingest_psa_poverty),
        ("historical_roster", ingest_historical_roster),
    ]

    failures = {}
    for name, fn in steps:
        try:
            fn()
        except Exception as e:
            failures[name] = str(e)
            print(f"[FAILED] {name}: {e}")

    print("\n=== Ingestion summary ===")
    for name, _ in steps:
        print(f"{'FAIL' if name in failures else 'OK  '}  {name}")

    if failures:
        print("\nSome sources failed. Fix the errors above and re-run.")
        sys.exit(1)

    print("All raw ingestion complete!")