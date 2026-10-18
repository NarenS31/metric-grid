"""Tiny stdlib .xlsx reader (first sheet or named sheet) so we do not need openpyxl for two EIA-861 tables."""
import re
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(path, header_row: int = 0) -> pd.DataFrame:
    """Read the first worksheet to a DataFrame of strings; header_row is the 0-based row holding column names."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")) for si in root.findall("m:si", NS)]
        sheet = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))[0]
        rows = []
        for row in ET.fromstring(z.read(sheet)).iter(f"{{{NS['m']}}}row"):
            vals = {}
            for c in row.findall("m:c", NS):
                v = c.find("m:v", NS)
                if v is None:
                    inline = c.find("m:is", NS)
                    val = "".join(t.text or "" for t in inline.iter(f"{{{NS['m']}}}t")) if inline is not None else None
                else:
                    val = shared[int(v.text)] if c.get("t") == "s" else v.text
                vals[_col_index(c.get("r"))] = val
            rows.append([vals.get(i) for i in range(max(vals) + 1)] if vals else [])
    width = max(len(r) for r in rows)
    rows = [r + [None] * (width - len(r)) for r in rows]
    return pd.DataFrame(rows[header_row + 1:], columns=rows[header_row])
