import re
import sys
import collections
from pathlib import Path

import pdfplumber
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # <root>/src/transform/<this file>

# Left edge (pt) of each table column, measured from the PDF.
EDGES = [("name", 45), ("prov", 186), ("dist", 295), ("period", 355), ("years", 497), ("notes", 549)]
FIELDS = ["name", "prov", "dist", "period", "years", "notes"]
HYPHENS = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2212": "-"})

YEAR_TOKEN = re.compile(r"(\d{4})\**\s*-?\s*(\d{4})?\**")
YEARS_FULL = re.compile(r"^\d{4}\**\s*(?:-\s*(?:\d{3,4})?\**)?$")
YEARS_AT_END = re.compile(r"\s(\d{4}\**\s*-\s*\d{4}\**|\d{4}\**)$")


def _col(x0):
    c = "name"
    for n, e in EDGES:
        if x0 >= e - 3:
            c = n
    return c


def _page_lines(page):
    words = [w for w in page.extract_words(x_tolerance=1.5)]
    lines = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if lines and abs(lines[-1][0] - w["top"]) <= 2.5:
            lines[-1][1].append(w)
        else:
            lines.append([w["top"], [w]])
    out = []
    for _, ws in lines:
        cells = collections.defaultdict(list)
        for w in sorted(ws, key=lambda w: w["x0"]):
            cells[_col(w["x0"])].append(w["text"].translate(HYPHENS))
        out.append({k: " ".join(v) for k, v in cells.items()})
    return out


def _is_header(line):
    return line.get("name") == "NAME" and "REGION/PROVINCE" in line.get("prov", "")


def _split_years(years, period):
    """Return (years, period); years may be glued to the end of the period cell (party-list rows)."""
    years, period = years.strip(), period.strip()
    if not years:
        m = YEARS_AT_END.search(" " + period)
        if m:
            years = m.group(1).strip()
            period = period[: len(period) - len(m.group(1))].strip()
    return years, period


def _is_years(s):
    return bool(s) and bool(YEARS_FULL.match(s.strip()))


def parse_roster(pdf_path):
    records = []
    current_name = ""
    pid = 0
    last = None  # last record dict
    xrefs = []

    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            lines = _page_lines(page)
            if not any(_is_header(l) for l in lines):
                if records:  # past the roster table (references/blank pages)
                    break
                continue
            for line in lines:
                if _is_header(line):
                    continue
                years, period = _split_years(line.get("years", ""), line.get("period", ""))
                has_years = _is_years(years)
                line_fields = {k: line.get(k, "").strip() for k in FIELDS}
                has_core = any(line_fields[k] for k in ("name", "prov", "dist", "period"))

                # Cross-reference rows ("see Villarosa, Ma. Amelita C.") are not terms of office.
                xref_text = line_fields["notes"] or line_fields["years"]
                if (not has_years and not line_fields["period"]
                        and re.match(r"\*?\s*see\b", xref_text, re.I)):
                    xrefs.append({"name": line_fields["name"], "see": xref_text, "page": pno})
                    continue

                new_record = has_years or (line_fields["period"] and (line_fields["name"] or line_fields["prov"]) and not last is None and _looks_like_period(line_fields["period"]))
                if new_record:
                    if line_fields["name"]:
                        current_name = line_fields["name"]
                        pid += 1
                    last = {
                        "pid": pid,
                        "name": current_name,
                        "region_province": line_fields["prov"],
                        "district": line_fields["dist"],
                        "period": period,
                        "years_raw": years,
                        "notes": line_fields["notes"],
                        "page": pno,
                        "_name_cont": [],
                    }
                    records.append(last)
                elif last is not None and (has_core or line_fields["notes"]):
                    # continuation of a wrapped cell: append to the previous record
                    if line_fields["name"]:
                        last["_name_cont"].append(line_fields["name"])
                    if line_fields["prov"]:
                        last["region_province"] = f"{last['region_province']} {line_fields['prov']}".strip()
                    if line_fields["dist"]:
                        last["district"] = f"{last['district']} {line_fields['dist']}".strip()
                    if line_fields["period"]:
                        last["period"] = f"{last['period']} {line_fields['period']}".strip()
                    if years:
                        last["notes"] = f"{last['notes']} {years}".strip()
                    if line_fields["notes"]:
                        last["notes"] = f"{last['notes']} {line_fields['notes']}".strip()
    return records, xrefs


# Official Congress terms, used only to repair obvious typos in the source PDF (e.g. "1922-1995" for the 9th).
CONGRESS_TERMS = {
    2: (1949, 1953), 3: (1954, 1957), 4: (1958, 1961), 5: (1962, 1965), 6: (1966, 1969),
    7: (1970, 1972), 8: (1987, 1992), 9: (1992, 1995), 10: (1995, 1998), 11: (1998, 2001),
    12: (2001, 2004), 13: (2004, 2007), 14: (2007, 2010), 15: (2010, 2013), 16: (2013, 2016),
    17: (2016, 2019),
}

PERIOD_RE = re.compile(r"(Congress|Legislature|Commonwealth|Assembly|Batasang|Pambansa)", re.I)


def _looks_like_period(s):
    return bool(PERIOD_RE.search(s))


def to_dataframe(records):
    # A wrapped name ("... ANGELICA" / "ROSEDELL M.") is attached to a record line; apply it to every
    # record of the same person.
    conts = collections.defaultdict(list)
    for r in records:
        conts[r["pid"]].extend(r["_name_cont"])
    fixed = []
    for r in records:
        r = dict(r)
        r["name"] = " ".join([r["name"]] + conts[r["pid"]]).strip()
        fixed.append(r)
    df = pd.DataFrame(fixed).drop(columns=["_name_cont", "pid"])
    df["name"] = df["name"].str.replace(r"\*+$", "", regex=True).str.strip()

    def parse_years(s):
        nums = re.findall(r"\d{4}", s or "")
        start = int(nums[0]) if nums else None
        end = int(nums[1]) if len(nums) > 1 else (start if nums else None)
        return start, end

    ys = df["years_raw"].apply(parse_years)
    df["start_year"] = [y[0] for y in ys]
    df["end_year"] = [y[1] for y in ys]
    span = df["end_year"] - df["start_year"]
    df["years_suspect"] = (span < 0) | (span > 12) | df["start_year"].isna()
    df["period_clean"] = df["period"].str.replace(r"\*+", "", regex=True).str.strip()
    num = df["period_clean"].str.extract(r"^(\d+)(?:st|nd|rd|th)\s+Congress$")[0]
    df["congress_number"] = pd.to_numeric(num, errors="coerce")
    df["years_corrected"] = False
    has_raw = df["years_raw"].fillna("").str.strip().ne("")
    fix = df["years_suspect"] & has_raw & df["congress_number"].isin(CONGRESS_TERMS)
    for idx in df.index[fix]:
        st, en = CONGRESS_TERMS[int(df.at[idx, "congress_number"])]
        df.at[idx, "start_year"], df.at[idx, "end_year"] = st, en
        df.at[idx, "years_corrected"] = True
    # The Regular Batasang Pambansa always sat 1984-1986.
    rbp = df["years_suspect"] & has_raw & df["period_clean"].eq("Regular Batasang Pambansa")
    df.loc[rbp, ["start_year", "end_year", "years_corrected"]] = [1984, 1986, True]
    df["years_suspect"] = df["years_suspect"] & ~df["years_corrected"]
    df["has_note_marker"] = df["years_raw"].str.contains(r"\*", na=False) | df["notes"].ne("")
    df["is_party_list"] = df["region_province"].str.contains("Party-List", case=False, na=False)
    df["is_sectoral"] = df["region_province"].str.contains("Sectoral", case=False, na=False)
    surname = df["name"].str.split(",", n=1).str[0].str.strip()
    df["surname"] = surname
    return df[
        ["name", "surname", "region_province", "district", "period_clean", "congress_number",
         "start_year", "end_year", "years_raw", "years_corrected", "years_suspect", "notes",
         "is_party_list", "is_sectoral", "page"]
    ]


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / "data" / "raw" / "roster_legislators.pdf"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else PROJECT_ROOT / "data" / "staging" / "roster_legislators.csv"
    recs, xrefs = parse_roster(src)
    df = to_dataframe(recs)
    dst.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(dst, index=False, encoding="utf-8")
    print(f"Parsed {len(df):,} term records, {df['name'].nunique():,} legislators -> {dst}")
    print(f"Skipped {len(xrefs)} cross-reference rows; {int(df['years_suspect'].sum())} rows flagged years_suspect")