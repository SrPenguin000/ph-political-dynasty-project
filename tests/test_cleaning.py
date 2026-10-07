"""Unit tests for the task 6 cleaning helpers. Run from the project folder: python -m pytest tests"""

import pandas as pd

from src.transform.clean_backfill import apply_town_maps, clean_ateneo_provinces
from src.transform.normalize import fix_mojibake, fix_ocr_digits, name_key, norm_town, split_suffix


def test_fix_mojibake_repairs_broken_enye():
    broken = "PARAÑAQUE".encode("utf-8").decode("cp1252")  # breaks the text the same way the file did
    assert broken != "PARAÑAQUE"
    assert fix_mojibake(broken) == "PARAÑAQUE"


def test_fix_mojibake_leaves_clean_text_alone():
    assert fix_mojibake("PEÑA") == "PEÑA"
    assert fix_mojibake("SAN JUAN") == "SAN JUAN"
    assert fix_mojibake(None) is None


def test_fix_ocr_digits():
    assert fix_ocr_digits("CARIN0") == "CARINO"
    assert fix_ocr_digits("DOM1NADOR") == "DOMINADOR"
    assert fix_ocr_digits("ALAN1") == "ALAN1"  # a final 1 is not clearly a letter


def test_split_suffix():
    assert split_suffix("JOSE JR.") == ("JOSE", "Jr.")
    assert split_suffix("GREGORIO 111") == ("GREGORIO", "III")
    assert split_suffix("REYNOLD JR. II") == ("REYNOLD", "Jr. II")
    assert split_suffix("SERGIO ANTONIO V") == ("SERGIO ANTONIO V", None)


def test_glued_suffix_only_with_2019_rule():
    assert split_suffix("ADOLFOJR") == ("ADOLFOJR", None)
    assert split_suffix("ADOLFOJR", glued_ok=True) == ("ADOLFO", "Jr.")
    assert split_suffix("NASR", glued_ok=True) == ("NASR", None)


def test_norm_town_and_name_key():
    assert norm_town("Bacungan (Leon T. Postigo)") == "BACUNGAN"
    assert norm_town("City of San Fernando") == "SAN FERNANDO"
    assert name_key("dela Cruz Jr.") == "DELACRUZ"


def test_town_maps_use_province_groups():
    # A fix written for DAVAO DEL NORTE also applies to its towns listed under DAVAO DE ORO
    towns = pd.Series(["San Vicente", "San Vicente", "Kalookan City"])
    provinces = pd.Series(["DAVAO DE ORO", "PALAWAN", "NCR THIRD DISTRICT"])
    assert apply_town_maps(towns, provinces).tolist() == ["LAAK", "SAN VICENTE", "CALOOCAN"]


def test_clean_ateneo_provinces_long_format():
    sheet = pd.DataFrame({"province": ["TAWI-TAWI"], "fatdynshare1992": [10.0], "fatdynshare1995": [None]})
    long = clean_ateneo_provinces(sheet)
    assert long["year"].tolist() == [1992, 1995]
    assert long["province_std"].tolist() == ["TAWI TAWI", "TAWI TAWI"]
    assert long["fat_dynasty_share_pct"].isna().tolist() == [False, True]