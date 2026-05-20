"""Write scraped sections to an Excel workbook (one sheet per section)."""

from pathlib import Path

import pandas as pd

SHEET_NAMES = {
    "main_catalog":        "MainCatalog",
    "combos":              "Combos",
    "partials_rips":       "Partials_RIPs",
    "partials_pricing":    "Partials_Pricing",
    "inventory_reduction": "InventoryReduction",
    "keg_list":            "KegList",
    "new_items":           "NewItems",
}

STRING_COLUMNS = {"code", "product_code", "sku", "deal_number"}


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
            else:
                pd.DataFrame([{"note": f"No rows extracted for {section}"}]).to_excel(
                    xw, sheet_name=sheet, index=False
                )
    return out_path
