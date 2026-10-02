"""Parse PSA Table 1 (poverty incidence among families, by region and province: 2018, 2021, 2023)
from the 2023 Full Year Official Poverty Statistics PDF into a tidy long CSV.

Usage: python parse_psa_poverty.py [input.pdf] [output.csv]
"""
import re
import sys
import collections
from pathlib import Path

import pdfplumber
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # <root>/src/transform/<this file>

NUM = re.compile(r"^-?[\d,]+(\.\d+)?$")
YEARS = [2018, 2021, 2023]
# 18 numeric columns, left to right, as (measure, year)
COLUMNS = (
    [("poverty_threshold", y) for y in YEARS]
    + [("poverty_incidence", y) for y in YEARS]
    + [("cv", y) for y in YEARS]
    + [("std_error", y) for y in YEARS]
    + [(m, y) for y in YEARS for m in ("ci_lower", "ci_upper")]
)
REGION_RE = re.compile(
    r"^(PHILIPPINES|National Capital Region|Cordillera|Region [IVX]+|MIMAROPA|Negros Island|Bangsamoro)", re.I
)
DISTRICT_RE = re.compile(r"^\d+(st|nd|rd|th) District$")


def _rows(page):
    words = page.extract_words(x_tolerance=1.5)
    rows = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if rows and abs(rows[-1][0] - w["top"]) <= 2.5:
            rows[-1][1].append(w)
        else:
            rows.append([w["top"], [w]])
    return [sorted(ws, key=lambda w: w["x0"]) for _, ws in rows]


def _column_edges(rows):
    """Right edges of the 18 numeric columns, from rows that have exactly 18 clean numbers."""
    samples = []
    for ws in rows:
        nums = [w for w in ws if NUM.match(w["text"])]
        if len(nums) == 18:
            samples.append([w["x1"] for w in nums])
    if not samples:
        raise RuntimeError("Could not calibrate numeric columns on this page")
    return [sorted(col)[len(col) // 2] for col in zip(*samples)]


def _table1_pages(pdf):
    pages, started = [], False
    for i, pg in enumerate(pdf.pages):
        first = (pg.extract_text() or "").split("\n", 1)[0]
        if first.startswith("Table 1. Annual"):
            pages.append(i)
            started = True
        elif started and first.startswith("Table 1a"):
            break
    if not pages:
        raise RuntimeError("Table 1 not found in the PDF")
    return pages


def parse_psa(pdf_path):
    records = []
    region = None
    with pdfplumber.open(pdf_path) as pdf:
        for pi in _table1_pages(pdf):
            rows = _rows(pdf.pages[pi])
            edges = _column_edges(rows)
            first_left = edges[0] - 26  # words starting left of this are the area name
            prev = None
            for ws in rows:
                if ws and ws[0]["text"] == "Notes:":
                    break
                name_words = [w for w in ws if w["x0"] < first_left]
                tail = [w for w in ws if w["x0"] >= first_left]
                num_words = [w for w in tail if NUM.match(w["text"])]
                flag_words = [w for w in tail if not NUM.match(w["text"])]  # footnote markers: 1/, 2/, a/, r1, ...
                cells = collections.defaultdict(list)
                ok = True
                for w in num_words:
                    j = min(range(18), key=lambda k: abs(w["x1"] - edges[k]))
                    if abs(w["x1"] - edges[j]) > 14:
                        ok = False
                        break
                    cells[j].append(w["text"])
                name = " ".join(w["text"] for w in name_words).strip()
                if not num_words:
                    # wrapped area name, e.g. "(BARMM)" under the long BARMM name
                    if prev is not None and name.startswith("("):
                        prev["area"] = f"{prev['area']} {name}"
                        if prev["level"] == "region":
                            prev["region"] = region = prev["area"]
                    continue
                if not ok or not name or name.startswith("Table") or len(num_words) < 6:
                    continue
                vals = {}
                for j, parts in cells.items():
                    vals[COLUMNS[j]] = float("".join(parts).replace(",", ""))
                if DISTRICT_RE.match(name):
                    level = "district"
                elif name.upper() == "PHILIPPINES":
                    level, region = "national", None
                elif REGION_RE.match(name):
                    level, region = "region", name
                else:
                    level = "province"
                rec = {
                    "area": name,
                    "level": level,
                    "region": region if level != "national" else None,
                    "flags": " ".join(w["text"] for w in flag_words),
                    "page": pi + 1,
                    "_vals": vals,
                }
                records.append(rec)
                prev = rec
    return records


def to_long(records):
    rows = []
    for r in records:
        for y in YEARS:
            vals = {m: r["_vals"].get((m, y)) for m in
                    ("poverty_threshold", "poverty_incidence", "cv", "std_error", "ci_lower", "ci_upper")}
            if all(v is None for v in vals.values()):
                continue
            rows.append({"area": r["area"], "level": r["level"], "region": r["region"], "year": y, **vals,
                         "flags": r["flags"], "page": r["page"]})
    df = pd.DataFrame(rows)
    df["area_key"] = (
        df["area"].str.upper().str.replace(r"\s*\(.*?\)", "", regex=True).str.replace(r"[^A-Z0-9 ]", "", regex=True)
        .str.replace(r"\s+", " ", regex=True).str.strip()
    )
    aliases = {"MT PROVINCE": "MOUNTAIN PROVINCE", "TAWITAWI": "TAWI TAWI"}
    df["area_key"] = df["area_key"].replace(aliases)
    return df[["area", "area_key", "level", "region", "year", "poverty_incidence", "poverty_threshold",
               "cv", "std_error", "ci_lower", "ci_upper", "flags", "page"]]


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / "data" / "raw" / "psa_poverty.pdf"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else PROJECT_ROOT / "data" / "staging" / "psa_poverty.csv"
    df = to_long(parse_psa(src))
    dst.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(dst, index=False, encoding="utf-8")
    n = df.groupby("level")["area"].nunique().to_dict()
    print(f"Parsed {df['area'].nunique()} areas {n} into {len(df):,} area-year rows -> {dst}")