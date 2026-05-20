"""CLI entry point.

Usage:
  python -m templates.Fedway.run <pdf> [<pdf> ...] [-o output.xlsx]
"""

import argparse
import sys
from pathlib import Path

from .scraper import scrape_pdf
from .writer import write_workbook


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fedway PDF price-book scraper")
    parser.add_argument("pdfs", nargs="+", type=Path,
                        help="Path(s) to one or more Fedway Price Book PDFs")
    parser.add_argument("-o", "--out", type=Path, default=None,
                        help="Output .xlsx (default: 'Fedway Price Book.xlsx' "
                             "next to the first PDF)")
    args = parser.parse_args(argv)

    for p in args.pdfs:
        if not p.exists():
            print(f"PDF not found: {p}", file=sys.stderr)
            return 2

    out = args.out or (args.pdfs[0].parent / "Fedway Price Book.xlsx")

    combined_results = None
    combined_diagnostics = {"books": []}

    for pdf in args.pdfs:
        print(f"\nScraping {pdf.name} ...")
        results, diagnostics = scrape_pdf(pdf)
        combined_diagnostics["books"].append({
            "source": diagnostics["source"],
            "book_year": diagnostics["book_year"],
            "book_month": diagnostics["book_month"],
            "book_label": diagnostics["book_label"],
            "sections_detected": diagnostics["sections_detected"],
        })

        if combined_results is None:
            combined_results = {k: list(v) for k, v in results.items()}
        else:
            for sec, rows in results.items():
                combined_results.setdefault(sec, []).extend(rows)

        print(f"  edition: {diagnostics['book_label']}  ({diagnostics['source']})")
        print(f"  row counts: " + ", ".join(
            f"{k}={len(v)}" for k, v in results.items() if v))

    diag_for_writer = {"sections_detected": []}
    for book in combined_diagnostics["books"]:
        for s in book["sections_detected"]:
            diag_for_writer["sections_detected"].append({
                "book_label": book["book_label"],
                "source": book["source"],
                **s,
            })

    write_workbook(combined_results, diag_for_writer, out)
    print(f"\nWritten: {out}")
    print(f"Combined row counts:")
    for sec, rows in combined_results.items():
        print(f"  {sec:24s}  {len(rows):6d} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
