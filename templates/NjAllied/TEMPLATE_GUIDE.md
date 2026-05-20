# NJ Allied Price Book Extraction Template

Complete guide for ingesting Allied Beverage Group (NJ) monthly price book PDFs into the LiquorPriceBook database.

---

## Quick Start (One Command)

```bash
# Scrape locally + push to Render API
python -m scripts.local_ingest "2026-06 Price Book.pdf" \
  --api-url https://lpb-api-41nh.onrender.com \
  --token <LPB_ADMIN_TOKEN>

# Dry run (scrape only, verify output, no upload)
python -m scripts.local_ingest "2026-06 Price Book.pdf" --dry-run

# Scrape to Excel (no API push)
python -m templates.NjAllied.run "2026-06 Price Book.pdf" -o output.xlsx

# Multiple PDFs merged into one workbook
python -m templates.NjAllied.run "2026-05 Price Book.pdf" "2026-06 Price Book.pdf"
```

**Requirements:** PDF filename must contain `YYYY-MM` (e.g. `2026-06 Price Book.pdf`), or pass `--year` / `--month` flags.

---

## Architecture Overview

```
PDF file (local machine)
  |
  v
templates/NjAllied/scraper.py   -- pdfplumber, runs locally (unlimited RAM)
  |  classifies pages -> section parsers -> structured dicts
  v
scripts/local_ingest.py          -- POSTs JSON to Render API
  |
  v
POST /api/v1/admin/ingest/prescraped   -- Render API endpoint
  |
  v
src/lpb_worker/ingestion/pipeline.py   -- normalises + upserts to Postgres
  |  CategoryResolver, BrandDeriver, FuzzyProductMatcher
  v
Database tables: products, product_editions, rip_offers,
  partials_pricing, partials_rips, inventory_reduction, combos, keg_list
```

The split exists because Render's 512MB RAM limit can't handle pdfplumber. Local scrape is unlimited RAM; only lightweight JSON goes to the server.

---

## PDF Structure (Allied Beverage Group Monthly Price Book)

Typical page count: ~260 pages. Sections in order:

| Pages (approx) | Section | Detection Pattern | Parser |
|-----------------|---------|-------------------|--------|
| 1 | Table of Contents | `Table of Contents` | skipped |
| 2-7 | Inventory Reduction (closeouts) | `INVENTORY REDUCTION` | `inventory_reduction.py` |
| 8-9 | New Items | `NEW ITEMS` | `new_items.py` |
| 10-11 | Partials/Web RIPs | `PARTIALS/WEB RIPS` | `partials_rips.py` |
| 12-13 | Partials/Web Pricing | `PARTIALS/WEB PRICING` | `partials_pricing.py` |
| 14 | Keg List | `Keg List` | `keg_list.py` |
| 15-23 | Combos | `ABG\s+\w+\s+\d{4}\s+COMBOS` | `combos.py` |
| 24-31 | Alphabetical Index | `Alphabetical Index` | skipped |
| 32-73 | Producer Pages | `Retail Incentives for` | skipped |
| 75-256 | Main Catalog | `Code\s+Size\s+Pk\s+P\.O\.` | `main_catalog.py` |

**Section detection is pattern-based, not page-number-based.** Pages shift between monthly editions; the regex patterns in `config.py:SECTION_PATTERNS` handle this automatically.

---

## Section Parsers

### 1. Main Catalog (`sections/main_catalog.py`)

The largest section (~13,000 product rows). Three-column layout per page.

**Page layout:**
```
+-- Category Banner (top, centered: "BLENDED WHISKEY", "VODKA", etc.) --+
|                                                                        |
|  Column 1 (x: 28-215)    Column 2 (x: 218-400)   Column 3 (x: 401-595) |
|                                                                        |
|  Brand Header: "THE GLENLIVET ( L GS FB IV )"                         |
|  Sub-variant: "12 YR OLD"                                              |
|  Code  Size  Pk  PO.Cost  CaseCost  BtlCost  BestBuy  BestRip         |
|  0050840  750ML  12  $30.00  $360.00  $30.00  $29.00  $28.00           |
|  RIP annotation: "$12.00 ON 1CS 348.00 29.00"                         |
|  Another product...                                                     |
+------------------------------------------------------------------------+
```

**8 fields per product row** (snapped by x-coordinate):
- `code` (7-digit, left-aligned)
- `size` (left-aligned)
- `pack` (left-aligned)
- `po_cost`, `case_cost`, `btl_cost`, `best_buy`, `best_rip` (right-aligned)

**Extraction strategy:**
1. `extract_words()` gets word positions with (x0, x1, top) coordinates
2. Words clustered into rows by y-coordinate (tolerance: 2.5pt)
3. Each row's words split into 3 lanes by x-coordinate ranges
4. First word = 7-digit code? -> product row, snap remaining words to field anchors
5. Otherwise -> brand header, sub-variant, or RIP annotation

**RIP annotations** sit between product rows:
- Pattern: `$12.00 ON 1CS 348.00 29.00` (save $12/cs on 1-case tier, new case price $348, new btl price $29)
- Multiple tiers per product (1CS, 3CS, 5CS) -> stored in `rip_offers[]` array
- Best (highest save) promoted to top-level fields

**Brand headers** contain division codes in parentheses:
- `"THE GLENLIVET ( L GS FB IV )"` -> brand="THE GLENLIVET", divisions="L GS FB IV"
- 7 valid NJ Allied divisions: `L`, `S`, `D`, `GS`, `FB`, `JD`, `IV`
- Division codes mean: which sales territories can order this product

**Known quirks:**
- `brand_header` gets overwritten by sub-headers within the same lane (e.g. "REPOSADO" overwrites "PATRON TEQUILA"). The pipeline uses description-based brand derivation as fallback.
- Category banners near y=12-18 at page top. Must filter out "ELIZABETH", "(800)", "272-1323", "Allied", "Beverage", "Group" boilerplate.
- Some RIP lines come through pdfplumber as single-glyph words: `"$ 1 2 . 0 0 O N 1 CS"`. The parser has a compressed regex fallback.

**Column x-anchors** (measured from May 2026 p75, defined in `config.py:CATALOG_COLUMN_ANCHORS`):
```
Lane 1: code@32, size@58, pack@80, po_cost@105, case_cost@126, btl_cost@149, best_buy@181, best_rip@213
Lane 2: code@218, size@243, pack@264, po_cost@289, case_cost@310, btl_cost@333, best_buy@365, best_rip@397
Lane 3: code@401, size@426, pack@447, po_cost@473, case_cost@494, btl_cost@517, best_buy@549, best_rip@581
```
Snap tolerance: 12px. If nearest anchor is farther, word is discarded.

**Output fields per row:**
```python
{
    "source": "2026-05 Price Book.pdf",
    "section": "MainCatalog",
    "category": "BLENDED WHISKEY",
    "brand_header": "THE GLENLIVET ( L GS FB IV )",
    "sub_brand": "12 YR OLD",
    "divisions": "L GS FB IV",
    "code": "0050840",
    "size": "750ML",
    "pack": 12,
    "po_cost": "30.00",
    "case_cost": "360.00",
    "btl_cost": "30.00",
    "best_buy": "29.00",
    "best_rip": "28.00",
    "rip_save_amount": 12.0,       # best tier
    "rip_tier": "1CS",
    "rip_case_price": 348.0,
    "rip_btl_price": 29.0,
    "rip_offers": [                 # all tiers
        {"rip_save_amount": 12.0, "rip_tier": "1CS", "rip_case_price": 348.0, "rip_btl_price": 29.0},
        {"rip_save_amount": 30.0, "rip_tier": "3CS", "rip_case_price": 330.0, "rip_btl_price": 27.5},
    ],
    "page": 75,
    "lane": 1,
    "book_year": 2026,
    "book_month": 5,
    "book_label": "2026-05",
}
```

---

### 2. Inventory Reduction / Closeouts (`sections/inventory_reduction.py`)

Discontinued products at reduced prices.

**Line format (regex):**
```
CODE(7)  DESCRIPTION  SIZE  PACK  $ORIG_CASE  $ORIG_BTL  $BEST_CASE  $BEST_BTL  $CASE_SAVE  $BTL_SAVE
```

**Subcategories:** `SPIRITS`, `WINES`, `NON ALCOHOL`

**Output fields:**
```python
{
    "source", "section": "InventoryReduction", "subcategory",
    "product_code", "description", "size", "pack",
    "original_case", "original_bottle",
    "best_case", "best_bottle",
    "case_save", "bottle_save",
    "page"
}
```

---

### 3. Partials/Web RIPs (`sections/partials_rips.py`)

Time-limited RIP (Rebate Incentive Program) offers.

**Line format:**
```
DESCRIPTION  SIZE  START_DATE  END_DATE  TIER=$AMOUNT
    continuation: 2CASES=$90  (tier-only, belongs to previous item)
```

**Output fields:**
```python
{
    "source", "section": "Partials_RIPs",
    "description", "size",
    "start_date", "end_date",  # date objects
    "tier": "1CASE",           # e.g. "1CASE", "2CASES", "3CASES"
    "rip_price": 36.0,         # dollar amount of rebate
    "rip_raw": "1CASE=$36",
    "page"
}
```

**Note:** Multi-tier items produce multiple rows (one per tier), all sharing the same base fields.

---

### 4. Partials/Web Pricing (`sections/partials_pricing.py`)

Time-limited special pricing (not rebates, but actual reduced prices).

**Line format:**
```
DESCRIPTION  PRODUCT#(6-7)  START_DATE  END_DATE  $BEST_CASE[/TIER]  $BEST_BTL
```

**Output fields:**
```python
{
    "source", "section": "Partials_Pricing",
    "description", "product_number",
    "start_date", "end_date",
    "best_case_price", "best_case_tier",  # e.g. "5CASES"
    "best_bottle_price",
    "page"
}
```

---

### 5. Combos (`sections/combos.py`)

Pre-built combo/gift packs.

**Line format:**
```
CATEGORY  SKU(7)  ITEM_CODE  CONTAINS_DESCRIPTION  $FRONT_LINE
```

**Price quirk:** pdfplumber renders prices as `$ 2 65.00` (space between leading digit and rest). The `normalize_combo_price()` function handles this.

**Output fields:**
```python
{
    "source", "section": "Combos",
    "subcategory": "WINES" | "SPIRITS" | "NON ALCOHOL",
    "sku", "item_code", "contains",
    "front_line_price", "front_line_raw",
    "page"
}
```

---

### 6. Keg List (`sections/keg_list.py`)

Keg products (one page typically).

**Line format:**
```
TYPE(Deposit|Disposable)  ABG_CODE(7)  DESCRIPTION  SIZE  $KEG_PRICE  $750ML_VALUE  $BTL_REG  $PER_OUNCE  [x=in_stock]
```

**Output fields:**
```python
{
    "source", "section": "KegList",
    "type", "abg_code", "description", "size",
    "best_keg_price", "value_per_750ml", "best_btl_reg", "per_ounce_estimate",
    "in_stock": True|False,
    "page"
}
```

---

### 7. New Items (`sections/new_items.py`)

New products added this month.

**Line format:**
```
CATEGORY  BRAND(ALL-CAPS)  DESCRIPTION  SIZE  SKU(7)  PACK  ABG_DIVISION
```

**Categories:** `WINE`, `WINES`, `SPIRITS`, `SPARKLING`, `NON ALC`, `NON ALCOHOL`, `THCB`, `GLASS`

**Output fields:**
```python
{
    "source", "section": "NewItems",
    "category", "brand", "description", "size",
    "sku", "pack", "abg",
    "page"
}
```

---

## Pipeline Stages (Server-Side)

After scraping, `pipeline.py` runs these stages:

### Stage 1: Normalise Main Catalog
- **CategoryResolver**: Maps raw category strings (e.g. "STRAIGHTW HISKEY") to canonical `categories` table via `raw_aliases` JSONB array
- **BrandDeriver**: Derives brand from description (first 2 non-modifier tokens). Prefers brand_header if it's not a sales-rep tag
- **resolve_duplicate_code_categories**: Same product code under 2+ categories? Picks the most frequent one

### Stage 2: Upsert Products + Product Editions
- Products keyed on `(distributor_id, code)` -- ON CONFLICT UPDATE
- Product editions keyed on `(product_id, book_edition_id)` -- DELETE + re-INSERT per edition
- Carries: category, brand, description, divisions, size, pack, all prices

### Stage 3: RIP Offers
- Multiple tiers per product edition (1CS, 3CS, 5CS, etc.)
- Keyed on `(product_edition_id, tier)`
- NJ ABC rules: tier_cases capped at 50

### Stage 4: Fuzzy-Linked Sections
- **FuzzyProductMatcher**: Token-set Jaccard similarity on descriptions, with size match boost (+0.10) / mismatch penalty (-0.20)
- Exact code match = confidence 1.0
- Below 0.85 confidence -> `low_confidence_matches` review queue
- Used for: partials_pricing, partials_rips, inventory_reduction, keg_list

### Stage 5: Refresh + Alerts
- Refreshes materialized views (`mv_price_changes`)
- Evaluates alert rules for user notifications

---

## Configuration Files

### `config.py` - Section Detection + Layout Constants

**SECTION_PATTERNS**: Ordered list of `(section_name, regex)`. First match wins. Tested against first ~6 lines of each page.

**CATALOG_COLUMN_ANCHORS**: x-coordinate anchors for the 3-column main catalog layout. Each column has 8 fields. Measured from a specific page; may need re-measurement if Allied changes their PDF layout software.

**CATALOG_LANES_X**: x-ranges for grouping words into the 3 columns: `[(28, 215), (218, 400), (401, 595)]`

**CATALOG_SNAP_TOL**: Maximum x-distance (12px) for snapping a word to its nearest field anchor.

### `utils.py` - Shared Helpers

- `parse_money(s)`: Extract `$XX.XX` from string
- `parse_date(s)`: Parse `M/D/YYYY` to date
- `is_product_code(token)`: Exactly 7 digits
- `looks_like_size(token)`: Matches known sizes (50ML, 750ML, 1.75L, etc.)
- `clean(s)`: Collapse whitespace
- `split_first_money(line)`: Split at first `$`

---

## Handling New Monthly PDFs

### Normal case (same format, new month):
```bash
python -m scripts.local_ingest "2026-07 Price Book.pdf" \
  --api-url https://lpb-api-41nh.onrender.com \
  --token $LPB_ADMIN_TOKEN
```
That's it. The system:
1. Detects sections by regex patterns (survives page-count drift)
2. Parses each section with its dedicated parser
3. POSTs structured JSON to the API
4. Server normalises, upserts, and links fuzzy matches
5. Idempotent: safe to re-run on the same PDF

### If Allied changes their PDF layout:
1. **New section added?** -> Add pattern to `config.py:SECTION_PATTERNS`, add parser to `sections/`, add handler to `scraper.py:SECTION_HANDLERS`
2. **Column positions shifted?** -> Re-measure x-anchors from a representative page and update `config.py:CATALOG_COLUMN_ANCHORS` and `CATALOG_LANES_X`
3. **New category names?** -> Add to `categories.raw_aliases` in the database
4. **New division codes?** -> Add to `main_catalog.py:_VALID_DIVISIONS`
5. **New subcategories?** (e.g. in Combos) -> Add to the relevant parser's category set

### Verification after ingestion:
```bash
# Check row counts in terminal output
# Expected ranges (May 2026):
#   main_catalog:     ~13,000 rows
#   rip_offers:       ~2,500 rows
#   inventory_reduction: ~100-300 rows
#   partials_rips:    ~50-150 rows
#   partials_pricing: ~50-150 rows
#   combos:           ~200-500 rows
#   keg_list:         ~30-80 rows
#   new_items:        ~20-100 rows
```

---

## File Map

```
templates/NjAllied/
  __init__.py              # exports scrape_pdf()
  config.py                # section patterns, column anchors, lane x-ranges
  scraper.py               # orchestrator: classify pages -> dispatch to parsers
  writer.py                # Excel output (one sheet per section)
  utils.py                 # shared: parse_money, parse_date, is_product_code
  run.py                   # CLI: python -m templates.NjAllied.run <pdf>
  sections/
    __init__.py            # re-exports all parsers
    main_catalog.py        # 3-column coordinate-based extraction
    inventory_reduction.py # regex-based row extraction
    partials_rips.py       # regex + continuation lines
    partials_pricing.py    # regex with optional tier suffix
    combos.py              # regex with price normalisation
    keg_list.py            # regex-based
    new_items.py           # token-based brand/description/size splitting

scripts/
  local_ingest.py          # local scrape + POST to Render API

src/lpb_worker/ingestion/
  pipeline.py              # server-side: normalise + upsert all sections
  normalisers/
    categories.py          # CategoryResolver (raw_aliases lookup)
    brands.py              # BrandDeriver (2-token prefix heuristic)
    codes.py               # resolve_duplicate_code_categories (voting)
  matchers/
    fuzzy.py               # FuzzyProductMatcher (Jaccard + size boost)

src/lpb_api/routes/
  ingest.py                # POST /api/v1/admin/ingest/prescraped endpoint
```

---

## Adding a New Distributor Template

To support a different distributor's price book (not NJ Allied):

1. Create `templates/<DistributorName>/` with the same structure
2. Define `SECTION_PATTERNS` for their PDF layout
3. Write section parsers that return `list[dict]` with standardised field names
4. Export a `scrape_pdf(pdf_path, source_name)` function
5. Update `scripts/local_ingest.py` to select the right template by `--distributor` flag
6. Update `pipeline.py:_scrape_pdf_bytes()` to dispatch to the right template

The pipeline's normalisation (categories, brands, fuzzy matching) and upsert logic is distributor-agnostic -- only the scraper template is distributor-specific.
