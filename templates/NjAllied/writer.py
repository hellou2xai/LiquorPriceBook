"""Write scraped sections to an Excel workbook (one sheet per section)."""

from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment

SHEET_NAMES = {
    "inventory_reduction": "InventoryReduction",
    "new_items":           "NewItems",
    "partials_rips":       "Partials_RIPs",
    "partials_pricing":    "Partials_Pricing",
    "keg_list":            "KegList",
    "combos":              "Combos",
    "main_catalog":        "MainCatalog",
}

# Code-like columns must stay as strings so leading zeros survive the round-trip.
STRING_COLUMNS = {
    "product_code", "sku", "code", "abg_code", "product_number",
}


def force_string_columns(df):
    for col in df.columns:
        if col in STRING_COLUMNS:
            df[col] = df[col].astype("string").fillna("")
    return df


def write_workbook(results, diagnostics, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        # Diagnostics first
        diag_rows = diagnostics.get("sections_detected", [])
        if diag_rows:
            pd.DataFrame(diag_rows).to_excel(xw, sheet_name="_Diagnostics", index=False)
        for section, sheet in SHEET_NAMES.items():
            rows = results.get(section, [])
            if rows:
                df = force_string_columns(pd.DataFrame(rows))
                df.to_excel(xw, sheet_name=sheet, index=False)
                # Format the code-string columns as Text in Excel so leading zeros stick
                ws = xw.sheets[sheet]
                for col_idx, col_name in enumerate(df.columns, start=1):
                    if col_name in STRING_COLUMNS:
                        for row in range(2, len(df) + 2):
                            cell = ws.cell(row=row, column=col_idx)
                            cell.number_format = "@"
            else:
                pd.DataFrame([{"note": f"No rows extracted for {section}"}]).to_excel(
                    xw, sheet_name=sheet, index=False
                )
    return out_path
