"""Fedway main catalog parser (Spirits, Wine, Cans & Cocktails, etc.).

Fedway catalog pages use a 3-column layout with these elements:
- **Category headers**: Uppercase text like "WHISKIES", "STILL", "SPARKLING"
- **Country/region headers**: "USA", "SCOTLAND", "CALIFORNIA", "RUSSIAN RIVER VALLEY"
- **Brand headers**: Uppercase brand names, sometimes with F/LA/GP/JNC/SC attributes
- **Product description**: Uppercase text describing the product variant
- **Item code line**: 4-9 digit code + size + pack + vintage/proof + attributes + buy deal
- **RIP line**: "RIP: <number>" + tier pricing
- **Price lines**: "1CASE $X.XX $Y.YY", "1BOTTLE $X.XX", "nCASES $X.XX $Y.YY"

Column headers are:
  Row 1: ITEM #  SIZE  PACK  VTG/PF  ATTRIB  BUY  BEST RIP
  Row 2: RIP #   QTY   FMT   PER UNIT UNIT   PER CS PER BT
"""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from ..config import CATALOG_LANES_X

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

_ITEM_CODE_RE = re.compile(r"^\+?\s*(\d{4,9})\s+(.+)")
_SIZE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(ML|LT|OZ|GAL|PK|CL)\b",
    re.IGNORECASE,
)
_PACK_RE = re.compile(r"(\d+)\s*PK\b", re.IGNORECASE)
_PROOF_RE = re.compile(r"(\d+(?:\.\d+)?)\s*PF\b", re.IGNORECASE)
_VINTAGE_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_BUY_DEAL_RE = re.compile(
    r"(\d+[CB]\\?\$\d+(?:\.\d+)?(?:\s*,\s*\d+[CB]\\?\$\d+(?:\.\d+)?)*)"
    r"|"
    r"(AD)\b"
)
_RIP_NUM_RE = re.compile(r"RIP:\s*([\d]+(?:\s*,\s*\d+)*)")
_PRICE_LINE_RE = re.compile(
    r"(\d+)(CASE|CASES|BOTTLE|BOTTLES|SLEEVE|SLEEVES)\s+"
    r"\$?([\d.,/OZoz]+)\s*"
    r"(?:\$?([\d.,]+))?\s*"
    r"(?:\$?([\d.,]+))?"
)
_DOLLAR_RE = re.compile(r"\$([\d,.]+)")
_ATTRIB_TOKENS = {"F", "LA", "GP", "JNC", "SC", "AD", "K", "E"}

# Category-level header words that indicate a category, not a brand
_CATEGORY_WORDS = {
    "WHISKIES", "WHISKEY", "WHISKY", "BOURBON", "RYE", "SCOTCH",
    "VODKA", "GIN", "RUM", "TEQUILA", "MEZCAL", "BRANDY", "BRANDIES",
    "COGNAC", "LIQUEURS", "LIQUEUR", "CORDIALS", "BITTERS",
    "SPIRITS", "WINE", "WINES", "STILL", "SPARKLING", "FORTIFIED",
    "CHAMPAGNE", "PROSECCO", "CAVA", "SAKE", "SOJU",
    "READY TO DRINK", "READY TO SERVE", "CIDER", "MALT",
    "BEER", "NON ALCOHOLIC", "MOCKTAILS", "MIXERS",
    "GLASSWARE", "CARBONATED", "OIL",
    "CANS AND COCKTAILS", "MALT PRODUCTS",
    # Sake sub-categories (Fedway uses these as headers within sake)
    "JUNMAI", "JUNMAI GINJO", "JUNMAI DAIGINJO", "DAIGINJO",
    "GINJO", "NIGORI", "HONJOZO", "SHOCHU", "INFUSED SAKE",
    "JUNMAI DAIGINGO", "DAIGINGO", "SPARKLING SAKE",
    "GARNISHES", "VERMOUTH", "ASIAN SPIRITS", "GRAIN SPIRITS",
}

# Sub-category words
_SUBCATEGORY_WORDS = {
    "BLENDED", "SINGLE MALT", "SINGLE BARREL", "SMALL BATCH",
    "STRAIGHT", "BONDED", "BARREL PROOF", "CASK STRENGTH",
    "CABERNET SAUVIGNON", "CHARDONNAY", "PINOT NOIR", "MERLOT",
    "SAUVIGNON BLANC", "PINOT GRIGIO", "RIESLING", "ROSE",
    "ZINFANDEL", "SYRAH", "SHIRAZ", "MALBEC", "TEMPRANILLO",
    "RED BLEND", "WHITE BLEND", "SANGIOVESE", "NEBBIOLO",
    "BARBARESCO", "BAROLO", "CHIANTI", "BRUNELLO",
    "TUSCAN RED", "TUSCAN WHITE",
}

# Country / region names that appear as headers
_COUNTRY_REGION_WORDS = {
    "USA", "SCOTLAND", "IRELAND", "CANADA", "JAPAN", "TAIWAN", "SWEDEN",
    "FRANCE", "ITALY", "SPAIN", "PORTUGAL", "GERMANY", "AUSTRIA",
    "AUSTRALIA", "NEW ZEALAND", "SOUTH AFRICA", "CHILE", "ARGENTINA",
    "MEXICO", "BRAZIL", "PERU", "URUGUAY", "COLOMBIA",
    "ENGLAND", "WALES", "NETHERLANDS", "BELGIUM", "SWITZERLAND",
    "GREECE", "HUNGARY", "CROATIA", "CZECH REPUBLIC", "POLAND",
    "INDIA", "CHINA", "KOREA", "THAILAND", "PHILIPPINES",
    "ISRAEL", "LEBANON", "TURKEY", "MOROCCO",
    "MARTINIQUE", "BARBADOS", "JAMAICA", "TRINIDAD", "PUERTO RICO",
    "GUATEMALA", "NICARAGUA", "PANAMA", "DOMINICAN REPUBLIC",
    "SLOVAKIA", "ROMANIA",
    # US States / Regions
    "CALIFORNIA", "OREGON", "WASHINGTON", "NEW YORK", "NEW JERSEY",
    "VIRGINIA", "PENNSYLVANIA", "TEXAS", "KENTUCKY", "TENNESSEE",
    "COLORADO", "MICHIGAN", "NORTH CAROLINA",
    # Wine sub-regions
    "NAPA VALLEY", "SONOMA", "RUSSIAN RIVER VALLEY", "PASO ROBLES",
    "NORTH COAST", "CENTRAL COAST", "SANTA BARBARA", "WILLAMETTE VALLEY",
    "COLUMBIA VALLEY", "WALLA WALLA", "FINGER LAKES", "LONG ISLAND",
    "BORDEAUX", "BURGUNDY", "RHONE", "LOIRE", "ALSACE", "CHAMPAGNE",
    "LANGUEDOC", "PROVENCE", "SOUTH OF FRANCE",
    "TUSCANY", "PIEDMONT", "VENETO", "SICILY", "PUGLIA", "ABRUZZO",
    "FRIULI", "SARDINIA", "UMBRIA", "CAMPANIA", "EMILIA ROMAGNA",
    "RIOJA", "RIBERA DEL DUERO", "GALICIA", "PRIORAT",
    "MENDOZA", "MAIPO VALLEY", "COLCHAGUA", "CASABLANCA",
    "STELLENBOSCH", "SWARTLAND",
    "BAROSSA VALLEY", "MCLAREN VALE", "MARGARET RIVER", "HUNTER VALLEY",
    "MARLBOROUGH", "HAWKES BAY", "CENTRAL OTAGO",
}

# --------------------------------------------------------------------------
# Fedway → DB category mapping
# --------------------------------------------------------------------------
# Fedway in-page headers are broad terms. We need to map them to the DB
# category display_names (which the CategoryResolver already recognises).
# Some mappings depend on country context (e.g., "WHISKIES" + "SCOTLAND" = Scotch).

_FEDWAY_CATEGORY_MAP: dict[str, str] = {
    # Direct mappings (no country context needed)
    "VODKA": "Vodka",
    "GIN": "Gin",
    "RUM": "Rum",
    "TEQUILA": "Tequila",
    "MEZCAL": "Mezcal",
    "COGNAC": "Cognac",
    "BOURBON": "Straight Whiskey, Bourbon & Moonshine",
    "RYE": "Rye Whiskey",
    "SCOTCH": "Scotch Whiskey",
    "WHISKEY": "Blended Whiskey",
    "LIQUEURS": "Cordials",
    "LIQUEUR": "Cordials",
    "CORDIALS": "Cordials",
    "BITTERS": "Cordials",
    "BRANDIES": "Brandy",
    "BRANDY": "Brandy",
    "CHAMPAGNE": "French Sparkling",
    "PROSECCO": "Italian Sparkling",
    "CAVA": "Spain Sparkling",
    "SAKE": "Wines of Japan / Sake",
    "READY TO DRINK": "Ready to Serve",
    "READY TO SERVE": "Ready to Serve",
    "CIDER": "Ready to Serve",
    "MOCKTAILS": "Non-alcoholic Juices & Mixers",
    "CARBONATED": "Non-alcoholic Juices & Mixers",
    "MIXERS": "Non-alcoholic Juices & Mixers",
    "GLASSWARE": "Glassware",
    "SOJU": "Cordials",
    "MALT": "Cans",
    "MALT PRODUCTS": "Cans",
    "NON ALCOHOLIC": "Non-alcoholic Juices & Mixers",
    "CANS AND COCKTAILS": "Cans",
    "OIL": "Non-alcoholic Juices & Mixers",
    # Section-name labels that can also appear as categories
    "MIXERS AND MORE": "Non-alcoholic Juices & Mixers",
    "WINES": "Wines of France",
    # Sake sub-categories
    "JUNMAI": "Wines of Japan / Sake",
    "JUNMAI GINJO": "Wines of Japan / Sake",
    "JUNMAI DAIGINJO": "Wines of Japan / Sake",
    "DAIGINJO": "Wines of Japan / Sake",
    "GINJO": "Wines of Japan / Sake",
    "NIGORI": "Wines of Japan / Sake",
    "HONJOZO": "Wines of Japan / Sake",
    "SHOCHU": "Wines of Japan / Sake",
    "INFUSED SAKE": "Wines of Japan / Sake",
    "WHISKY": "Blended Whiskey",
    "CRAFT DISTILLED": "Cordials",
    "GARNISHES": "Non-alcoholic Juices & Mixers",
    "JUNMAI DAIGINGO": "Wines of Japan / Sake",
    "DAIGINGO": "Wines of Japan / Sake",
    "SPARKLING SAKE": "Wines of Japan / Sake",
    "VERMOUTH": "Aperitifs",
    "BEER": "Cans",
    "JUICE/SYRUP": "Non-alcoholic Juices & Mixers",
    "ASIAN SPIRITS": "Cordials",
    "GRAIN SPIRITS": "Vodka",
}

# For "WHISKIES" header, the country determines the sub-category.
_WHISKEY_COUNTRY_MAP: dict[str, str] = {
    "SCOTLAND": "Scotch Whiskey",
    "IRELAND": "Irish Whiskey",
    "CANADA": "Canadian Whiskey",
    "JAPAN": "Japanese Whiskey",
    "TAIWAN": "Taiwanese Whisky",
    "INDIA": "Indian Whiskey",
    "CHINA": "Chinese Whiskey",
    "USA": "Straight Whiskey, Bourbon & Moonshine",
}

# For "STILL" / "SPARKLING" / "FORTIFIED" wine headers, country → category.
_WINE_COUNTRY_MAP: dict[str, str] = {
    "CALIFORNIA": "Wines of California",
    "OREGON": "Wines of Oregon",
    "WASHINGTON": "Wines of California",
    "NEW YORK": "Wines of New York State",
    "NEW JERSEY": "Wines of New Jersey",
    "FRANCE": "Wines of France",
    "ITALY": "Wines of Italy",
    "SPAIN": "Wines of Spain",
    "PORTUGAL": "Wines of Portugal - Table Wines",
    "GERMANY": "Wines of France",
    "AUSTRIA": "Wines of Austria",
    "AUSTRALIA": "Wines of Australia",
    "NEW ZEALAND": "Wines of Australia",
    "SOUTH AFRICA": "Wines of South Africa",
    "CHILE": "Wines of Chile",
    "ARGENTINA": "Wines of Argentina",
    "GEORGIA": "Wines of Georgia",
    "LEBANON": "Wines of Lebanon",
    "JAPAN": "Wines of Japan / Sake",
}

# Sub-regions → country for wine category resolution
_REGION_TO_COUNTRY: dict[str, str] = {
    "NAPA VALLEY": "CALIFORNIA", "SONOMA": "CALIFORNIA",
    "RUSSIAN RIVER VALLEY": "CALIFORNIA", "PASO ROBLES": "CALIFORNIA",
    "NORTH COAST": "CALIFORNIA", "CENTRAL COAST": "CALIFORNIA",
    "SANTA BARBARA": "CALIFORNIA",
    "WILLAMETTE VALLEY": "OREGON", "COLUMBIA VALLEY": "WASHINGTON",
    "WALLA WALLA": "WASHINGTON",
    "FINGER LAKES": "NEW YORK", "LONG ISLAND": "NEW YORK",
    "BORDEAUX": "FRANCE", "BURGUNDY": "FRANCE", "RHONE": "FRANCE",
    "LOIRE": "FRANCE", "ALSACE": "FRANCE", "LANGUEDOC": "FRANCE",
    "PROVENCE": "FRANCE", "SOUTH OF FRANCE": "FRANCE",
    "TUSCANY": "ITALY", "PIEDMONT": "ITALY", "VENETO": "ITALY",
    "SICILY": "ITALY", "PUGLIA": "ITALY", "ABRUZZO": "ITALY",
    "FRIULI": "ITALY", "SARDINIA": "ITALY", "UMBRIA": "ITALY",
    "CAMPANIA": "ITALY", "EMILIA ROMAGNA": "ITALY",
    "RIOJA": "SPAIN", "RIBERA DEL DUERO": "SPAIN",
    "GALICIA": "SPAIN", "PRIORAT": "SPAIN",
    "MENDOZA": "ARGENTINA", "MAIPO VALLEY": "CHILE",
    "COLCHAGUA": "CHILE", "CASABLANCA": "CHILE",
    "STELLENBOSCH": "SOUTH AFRICA", "SWARTLAND": "SOUTH AFRICA",
    "BAROSSA VALLEY": "AUSTRALIA", "MCLAREN VALE": "AUSTRALIA",
    "MARGARET RIVER": "AUSTRALIA", "HUNTER VALLEY": "AUSTRALIA",
    "MARLBOROUGH": "NEW ZEALAND", "HAWKES BAY": "NEW ZEALAND",
    "CENTRAL OTAGO": "NEW ZEALAND",
}


def _resolve_fedway_category(
    header_category: str | None,
    country: str | None,
    region: str | None,
) -> str | None:
    """Map a Fedway in-page category header + country/region context to
    a DB-compatible category name.
    """
    if not header_category:
        return None

    upper = header_category.upper()

    # Direct mapping
    if upper in _FEDWAY_CATEGORY_MAP:
        return _FEDWAY_CATEGORY_MAP[upper]

    # "WHISKIES" → depends on country
    if upper == "WHISKIES":
        effective_country = country
        if not effective_country and region:
            effective_country = _REGION_TO_COUNTRY.get(region)
        if effective_country and effective_country in _WHISKEY_COUNTRY_MAP:
            return _WHISKEY_COUNTRY_MAP[effective_country]
        return "Blended Whiskey"  # fallback

    # Wine-related: "STILL", "SPARKLING", "FORTIFIED", "WINE", "WINES"
    if upper in ("STILL", "SPARKLING", "FORTIFIED", "WINE", "WINES"):
        # Resolve region → country if needed
        effective_country = country
        if not effective_country and region:
            effective_country = _REGION_TO_COUNTRY.get(region)

        if upper == "SPARKLING" and effective_country:
            sparkling_map = {
                "FRANCE": "French Sparkling",
                "ITALY": "Italian Sparkling",
                "SPAIN": "Spain Sparkling",
                "USA": "American Sparkling",
                "CALIFORNIA": "American Sparkling",
                "AUSTRIA": "Austria Sparkling",
                "ENGLAND": "English Sparkling",
                "AUSTRALIA": "Wines of Australia",
                "ARGENTINA": "Argentina Sparkling",
                "CHILE": "Chile Sparkling",
            }
            return sparkling_map.get(effective_country, "French Sparkling")

        if effective_country and effective_country in _WINE_COUNTRY_MAP:
            return _WINE_COUNTRY_MAP[effective_country]

        # No country context — generic
        return "Wines of France"  # fallback for unresolvable wines

    # "SPIRITS" — generic, no specific sub-category
    if upper == "SPIRITS":
        return "Cordials"  # best generic spirits fallback

    return header_category  # passthrough (let CategoryResolver try)


# Words that are brand-name modifiers, NOT standalone brands
_MODIFIER_WORDS = {
    "AGED", "YEAR", "YEARS", "OLD", "YR", "PROOF", "RESERVE",
    "LIMITED", "EDITION", "SPECIAL", "SELECT", "PRIVATE",
    "SMALL", "BATCH", "SINGLE", "BARREL", "CASK", "STRAIGHT",
    "BONDED", "BOTTLED", "IN", "BOND", "PREMIUM", "LINE",
    "MADE", "AT", "WINERY", "DISTILLERY", "ESTATE",
    "EACH", "PACK", "CONTAINS", "COMBO", "SAVINGS",
    "PK", "CASE", "CASES", "BOTTLE", "BOTTLES",
    "BLACK", "PINK", "AMBER", "COPPER", "PLATINUM", "BRONZE",
    "GOLD", "SILVER", "WHITE", "RED", "BLUE", "GREEN",
    "LIGHT", "DARK", "EXTRA", "ULTRA", "SUPER",
    "EXTREMELY", "VERY", "DOUBLE", "TRIPLE",
    "RAIN", "HIGH", "HONEY", "ICE", "CREAM", "RUN",
    "DOOR", "SPOT", "CLUB", "WAVE", "VOTE", "LIT",
    "VINTAGE", "CLASSIC", "ORIGINAL", "TRADITIONAL",
    "NORTH", "SOUTH", "EAST", "WEST", "COAST",
    "FRENCH", "OAK", "FINISH", "FINISHED",
    "KENTUCKY", "TENNESSEE", "TEXAS", "AMERICAN",
    "BBN", "RYE", "WHEAT", "CORN", "MALT",
    "THE", "OF", "AND", "FROM", "WITH", "FOR", "BY",
}


# Product descriptor words — lines made entirely of these are descriptions,
# not brands, even when short and uppercase.
_PRODUCT_DESC_WORDS = {
    # Spirits types / styles
    "VODKA", "GIN", "RUM", "TEQUILA", "MEZCAL", "WHISKEY", "WHISKY",
    "BOURBON", "BRANDY", "COGNAC", "SCOTCH", "LIQUEUR", "CORDIAL",
    "ABSINTHE", "APERITIF", "GRAPPA", "SCHNAPPS",
    # Tequila variants
    "BLANCO", "REPOSADO", "ANEJO", "CRISTALINO", "JOVEN", "PLATA",
    "EXTRA", "GRAN", "RESERVA",
    # Rum variants
    "SPICED", "DARK", "LIGHT", "GOLD", "WHITE", "COCONUT", "PINEAPPLE",
    "MANGO", "PASSION", "FRUIT", "CARIBBEAN", "OVERPROOF",
    # Vodka flavors
    "CITRON", "CITRUS", "RASPBERRY", "STRAWBERRY", "WATERMELON",
    "VANILLA", "CHERRY", "GRAPE", "APPLE", "GRAPEFRUIT", "CRANBERRY",
    "ESPRESSO", "COFFEE", "HONEY", "CUCUMBER", "BLUEBERRY",
    "BLACKBERRY", "PRICKLY", "PEAR", "PEACH", "LIME", "LEMON",
    "ORANGE", "TROPICAL", "BERRY", "MINT", "MENTHOL",
    # Wine varietals
    "CABERNET", "SAUVIGNON", "CHARDONNAY", "PINOT", "NOIR", "GRIGIO",
    "MERLOT", "ZINFANDEL", "SYRAH", "SHIRAZ", "MALBEC", "RIESLING",
    "MOSCATO", "PROSECCO", "ROSE", "BRUT", "BLANC", "ROUGE",
    "VIOGNIER", "TEMPRANILLO", "VERDEJO", "SANGIOVESE", "NEBBIOLO",
    "BAROLO", "CHIANTI", "BRUNELLO", "AMARONE", "VALPOLICELLA",
    "BARBARESCO", "CUVEE", "SEC", "DEMI", "IMPERIAL",
    # Wine regions that appear in product names
    "NAPA", "SONOMA", "RESERVE", "TABLE", "WINE",
    # Modifiers
    "RTD", "PET", "CINNAMON", "CARAMEL", "SALTED", "FIRE",
    "COSMOPOLITAN", "MARGARITA", "MARTINI", "PALOMA", "SPRITZ",
}


# --------------------------------------------------------------------------
# Line classification
# --------------------------------------------------------------------------

def _classify_line(text: str) -> str:
    """Classify a reconstructed line of text within one column lane.

    Returns one of: 'header', 'item', 'rip', 'price', 'description', 'brand', 'skip'
    """
    stripped = text.strip()
    if not stripped:
        return "skip"

    # Column header lines
    if stripped.startswith("ITEM #") or stripped.startswith("RIP #"):
        return "skip"

    # Item code line: starts with optional '+' then 4-9 digit code
    if re.match(r"^\+?\s*\d{4,9}\s+\d", stripped):
        return "item"

    # RIP line
    if "RIP:" in stripped:
        return "rip"

    # Price/tier line: starts with nCASE, nBOTTLE, nSLEEVE, nCASES
    if re.match(r"^\d+(CASE|BOTTLE|SLEEVE|CASES|BOTTLES|SLEEVES)\b", stripped):
        return "price"

    # OCR spaced-out fallback: collapse all spaces and re-check for price/item
    # patterns. Handles "1 CA S E $333.96" → "1CASE$333.96" and similar.
    collapsed = stripped.replace(" ", "")
    if re.match(r"^\d+(CASE|CASES|BOTTLE|BOTTLES|SLEEVE|SLEEVES)\b", collapsed):
        return "price"
    if re.match(r"^RIP:\d", collapsed):
        return "rip"

    # Check if it's a category/country header
    upper = stripped.upper()
    if upper in _CATEGORY_WORDS or upper in _COUNTRY_REGION_WORDS:
        return "header"
    # Multi-word categories
    for cat in _CATEGORY_WORDS:
        if upper == cat:
            return "header"
    for region in _COUNTRY_REGION_WORDS:
        if upper == region:
            return "header"

    # Price period labels: "06/09-06/10 ONLY", "ALL MONTH", "LIMITED TIME OFFER"
    if re.match(r"^\d{2}/\d{2}\s*-\s*\d{2}/\d{2}", stripped):
        return "price"
    if upper in ("ALL MONTH", "LIMITED TIME OFFER", "SPECTACULAR"):
        return "price"
    if upper.endswith("ONLY") and re.search(r"\d{2}/\d{2}", stripped):
        return "price"

    # Garbled OCR line that looks like an item code line with spaced-out
    # numbers/sizes/prices — skip these to avoid polluting descriptions.
    # Pattern: starts with digits and has a high digit-to-alpha ratio,
    # or starts with 5+ digits followed by size/pack patterns.
    if re.match(r"^\d", stripped):
        alpha = sum(1 for c in stripped if c.isalpha())
        digit = sum(1 for c in stripped if c.isdigit())
        if digit > alpha and "$" in stripped:
            return "price"
        if digit > alpha and len(stripped) > 15:
            return "skip"
        # Pure item-code data: 5+ leading digits then size/pack tokens
        if re.match(r"^\d{5,}\s*(?:ML|LT|ASST)", stripped, re.IGNORECASE):
            return "skip"

    # Brand or description text — if all uppercase and no dollar signs
    if "$" not in stripped and not re.search(r"\d{4,}", stripped):
        words = stripped.split()
        attr_count = sum(1 for w in words if w in _ATTRIB_TOKENS)
        non_attr = [w for w in words if w not in _ATTRIB_TOKENS]

        # Has attribute tokens (F, LA, GP, JNC, SC) → definite brand
        # But skip footer/boilerplate lines that happen to contain tokens
        if non_attr and attr_count > 0:
            core = " ".join(non_attr).lower()
            if any(kw in core for kw in ("organic", "kosher", "assorts",
                                          "items with", "company are",
                                          "off prem", "sales company",
                                          "attributes", "screw cap",
                                          "gluten free")):
                return "skip"
            return "brand"

        # Short, all-uppercase text with no size/proof keywords → maybe brand
        # In Fedway's layout, brands ALWAYS have division/attribute tokens
        # (F, LA, GP, JNC, SC) on the right side. Lines without these tokens
        # are always descriptions — even short uppercase ones like "STARWARD",
        # "VODKA", "CANADIAN WHISKEY". No need for maybe_brand heuristics.
        return "description"

    # Combo savings line
    if "COMBO SAVINGS:" in stripped:
        return "price"

    return "description"


# --------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------

def _parse_item_line(text: str) -> dict | None:
    """Parse an item code line into structured fields."""
    m = _ITEM_CODE_RE.match(text.strip())
    if not m:
        return None

    code = m.group(1)
    rest = m.group(2)

    # Extract size
    size_m = _SIZE_RE.search(rest)
    size = f"{size_m.group(1)} {size_m.group(2).upper()}" if size_m else None
    # Normalize size
    if size:
        size = size.replace("LT", "L").replace(" CL", "0 ML")

    # Extract pack
    pack_m = _PACK_RE.search(rest)
    pack = int(pack_m.group(1)) if pack_m else None

    # Extract proof
    proof_m = _PROOF_RE.search(rest)
    proof = proof_m.group(1) if proof_m else None

    # Extract vintage
    vintage_m = _VINTAGE_RE.search(rest)
    vintage = vintage_m.group(1) if vintage_m else None

    # Extract buy deal (e.g. "1C\$50", "3C\$120", "AD")
    buy_deal = None
    buy_m = _BUY_DEAL_RE.search(rest)
    if buy_m:
        buy_deal = (buy_m.group(1) or buy_m.group(2) or "").replace("\\", "")

    # Extract attributes (F, LA, GP, JNC, SC, etc.)
    attribs = []
    for tok in rest.split():
        if tok.upper() in _ATTRIB_TOKENS and tok.upper() not in {"AD"}:
            attribs.append(tok.upper())

    return {
        "code": code,
        "size": size,
        "pack": pack,
        "proof": proof,
        "vintage": vintage,
        "buy_deal": buy_deal,
        "attribs": " ".join(attribs) if attribs else None,
    }


_PER_UNIT_RE = re.compile(r"\$([\d,.]+)\s*/\s*(OZ|EA|ML|CL|LT)\b", re.IGNORECASE)


def _parse_price_line(text: str) -> dict:
    """Extract pricing info from a tier/price line."""
    result = {}

    # Determine tier
    tier_m = re.match(
        r"(\d+)(CASE|CASES|BOTTLE|BOTTLES|SLEEVE|SLEEVES)\b",
        text.strip(),
    )
    if tier_m:
        qty = int(tier_m.group(1))
        unit = tier_m.group(2).upper()
        if unit.startswith("CASE"):
            result["tier"] = f"{qty}CS"
            result["tier_cases"] = qty
        elif unit.startswith("BOTTLE"):
            result["tier"] = f"{qty}BT"
            result["tier_cases"] = 0
        elif unit.startswith("SLEEVE"):
            result["tier"] = f"{qty}SL"
            result["tier_cases"] = 0

    # Collect per-unit amounts ($/OZ, $/EA, $/ML) to exclude them
    per_unit_amounts = set()
    for m in _PER_UNIT_RE.finditer(text):
        per_unit_amounts.add(m.group(1).replace(",", ""))

    # Find all dollar amounts, skipping per-unit ones
    dollars = _DOLLAR_RE.findall(text)
    clean_dollars = []
    for d in dollars:
        d_clean = d.replace(",", "")
        if d_clean in per_unit_amounts:
            continue
        try:
            clean_dollars.append(Decimal(d_clean))
        except (InvalidOperation, ValueError):
            pass

    if len(clean_dollars) >= 2:
        result["case_cost"] = clean_dollars[-2]
        result["btl_cost"] = clean_dollars[-1]
    elif len(clean_dollars) == 1:
        result["btl_cost"] = clean_dollars[0]

    return result


def _parse_rip_line(text: str) -> list[dict]:
    """Extract RIP number and any pricing from a RIP line."""
    results = []
    # Extract RIP numbers
    rip_m = _RIP_NUM_RE.search(text)
    rip_numbers = []
    if rip_m:
        rip_str = rip_m.group(1)
        rip_numbers = [n.strip() for n in rip_str.split(",") if n.strip().isdigit()]

    # Also extract any pricing on the same line
    pricing = _parse_price_line(text)

    for rip_num in rip_numbers:
        result = {"rip_number": rip_num, **pricing}
        results.append(result)

    # If no RIP numbers found but there's pricing, return that
    if not rip_numbers and pricing:
        results.append(pricing)

    return results


def _extract_brand(text: str) -> str | None:
    """Extract brand name from a brand line.

    Only strips attribute tokens (F, LA, GP, JNC, SC) and articles.
    Does NOT strip modifier words — "BLACK VELVET", "CANADIAN CLUB",
    "CROWN ROYAL" must be preserved intact.
    """
    words = text.strip().split()
    # Remove trailing attribute tokens
    while words and words[-1].upper() in _ATTRIB_TOKENS:
        words.pop()
    # Only strip articles/prepositions from the front, not brand-name words
    _STRIP_LEADING = {"THE", "OF", "AND", "FROM", "WITH", "FOR", "BY"}
    while words and words[0].upper() in _STRIP_LEADING:
        words.pop(0)

    if not words:
        return None

    brand = " ".join(words)
    # Don't treat very long strings as brands (likely descriptions)
    if len(brand) > 60:
        return None
    # Don't treat single-char brands
    if len(brand) <= 1:
        return None
    # Check it's not a known category/country
    if brand.upper() in _CATEGORY_WORDS or brand.upper() in _COUNTRY_REGION_WORDS:
        return None
    # Reject garbled OCR text (lots of single-char words like "/ E A" or "S T R A I G H T")
    non_single = [w for w in words if len(w) > 1]
    if len(non_single) < len(words) / 2:
        return None
    # Reject brands that are just punctuation or symbols
    alpha_chars = sum(1 for c in brand if c.isalpha())
    if alpha_chars < 2:
        return None

    return brand


# Pattern to detect trailing item-code data that bled in from adjacent columns.
# Matches: code-like digits followed by size/pack/proof/price fragments.
_CROSS_COLUMN_BLEED_RE = re.compile(
    r"\s+\d{4,9}\s*\d*\s*(?:ML|LT|OZ|PK|PF|ASST)"
    r"|"
    r"\s+\+\s+\d\s+\d{4,}"       # "+ 3 69310" spaced-out code
    r"|"
    r"\s+\d{5,}\d*\s*(?:ML|LT|PK)"  # "5294501   LT"
    , re.IGNORECASE
)


def _clean_cross_column_bleed(desc: str) -> str:
    """Strip trailing cross-column bleed from description text.

    E.g.: "GENTLEMAN JACK 48710200   ML24   PK80.0   PFMAY" → "GENTLEMAN JACK"
    """
    m = _CROSS_COLUMN_BLEED_RE.search(desc)
    if m:
        cleaned = desc[:m.start()].strip()
        if cleaned:
            return cleaned
    return desc


# --------------------------------------------------------------------------
# Column-based parser
# --------------------------------------------------------------------------

def _group_words_into_lanes(words: list[dict], lanes: list[tuple]) -> list[list[dict]]:
    """Group page words into column lanes based on x-position."""
    lane_words = [[] for _ in lanes]
    for w in words:
        x_mid = (w["x0"] + w["x1"]) / 2
        for i, (x_min, x_max) in enumerate(lanes):
            if x_min <= x_mid <= x_max:
                lane_words[i].append(w)
                break
    return lane_words


_DESPACED_RE = re.compile(r"(?<!\S)((?:[A-Za-z0-9$./\\] ){3,}[A-Za-z0-9$./\\])(?!\S)")

# Also match runs with multi-space gaps between single chars:
# "1 0 8  P R O OF" or "17 3 8   A C CORD"
_DESPACED_MULTI_RE = re.compile(
    r"(?<!\S)((?:[A-Za-z0-9$./\\]\s+){2,}[A-Za-z0-9$./\\])(?=\s|$)"
)

_OCR_WORD_SPLITS = re.compile(
    r"\b(BOT)\s+(TLE)"          # BOTTLE → BOT TLE
    r"|(CAS)\s+(ES?)"           # CASE/CASES → CAS E/CAS ES
    r"|(SLEEV)\s+(ES?)"         # SLEEVE → SLEEV E
    r"|(DIS)\s*(TIL)\s*(LE)"    # DISTILLE → DIS TIL LE
    r"|(WHISK)\s*(EY)"          # WHISKEY → WHISK EY
    r"|(CO)\s+(GNAC)"           # COGNAC → CO GNAC
    r"|(LI)\s*Q\s*(U)\s*(EUR)"  # LIQUEUR → LI Q U EUR
    r"|(AN)\s*(EJ)\s*(O)"       # ANEJO → AN EJ O
    r"|(TEQU)\s*(IL)\s*(A)"     # TEQUILA → TEQU IL A
    r"|(BLAN)\s*(CO)"           # BLANCO → BLAN CO
    r"|(AC)\s*(CORD)"           # ACCORD → AC CORD
    r"|(DAN)\s*(IELS)"          # DANIELS → DAN IELS
    r"|(PR)\s*(OOF)"            # PROOF → PR OOF (multi-space variant)
    , re.IGNORECASE
)


def _despace_ocr(text: str) -> str:
    """Collapse spaced-out OCR text: 'C A S E' → 'CASE', '$ 1 .5 0' → '$1.50'."""
    def _collapse(m: re.Match) -> str:
        return m.group(0).replace(" ", "")
    text = _DESPACED_RE.sub(_collapse, text)
    # Collapse multi-space single-char runs: "1 0 8  P R O OF"
    text = _DESPACED_MULTI_RE.sub(_collapse, text)
    # Fix common OCR word splits
    text = _OCR_WORD_SPLITS.sub(_collapse, text)
    return text


def _reconstruct_lines(words: list[dict], y_tolerance: float = 4.0) -> list[tuple[float, str]]:
    """Reconstruct text lines from word positions within a lane.

    Returns list of (y_position, text) tuples sorted by y.
    """
    if not words:
        return []

    # Group by y position
    rows: dict[int, list[dict]] = defaultdict(list)
    for w in words:
        y_key = round(w["top"] / y_tolerance)
        rows[y_key].append(w)

    lines = []
    for y_key in sorted(rows.keys()):
        row_words = sorted(rows[y_key], key=lambda w: w["x0"])
        text = " ".join(w["text"] for w in row_words)
        # Fix spaced-out OCR artifacts
        text = _despace_ocr(text)
        y_pos = min(w["top"] for w in row_words)
        lines.append((y_pos, text))

    return lines


def _parse_lane(
    lines: list[tuple[float, str]],
    page_num: int,
    lane_idx: int,
    source: str,
    section_name: str,
    initial_brand: str | None = None,
    initial_category: str | None = None,
    initial_country: str | None = None,
    initial_region: str | None = None,
) -> list[dict]:
    """Parse one column lane's lines into product rows."""
    products = []
    current_category = initial_category or _resolve_fedway_category(section_name, None, None) or section_name
    current_country = initial_country
    current_region = initial_region
    current_brand = initial_brand
    current_description = None
    last_description = None  # Carries forward for size-variant items with no own description
    current_item = None
    current_rips = []
    current_prices = []
    saw_price_after_item = False  # Track if we've seen prices for the current item
    brand_set_in_lane = False  # True once a brand line is seen in THIS lane (not inherited)

    def _flush():
        nonlocal current_item, current_description, last_description, current_rips, current_prices
        if current_item is None:
            return

        # If no description was set for this item, inherit the last one
        # (Fedway often lists multiple sizes under one description)
        if not current_description and last_description:
            current_description = last_description
        if current_description:
            last_description = current_description

        # Compute best RIP save
        best_save = None
        best_case_cost = None
        best_btl_cost = None
        rip_tiers = []

        for price in current_prices:
            cc = price.get("case_cost")
            bc = price.get("btl_cost")
            if cc is not None and (best_case_cost is None or cc < best_case_cost):
                best_case_cost = cc
            if bc is not None and (best_btl_cost is None or bc < best_btl_cost):
                best_btl_cost = bc

        for rip in current_rips:
            tier = rip.get("tier")
            cc = rip.get("case_cost")
            bc = rip.get("btl_cost")
            rip_num = rip.get("rip_number")
            if tier:
                rip_tiers.append({
                    "tier": tier,
                    "tier_cases": rip.get("tier_cases", 0),
                    "case_price": cc,
                    "btl_price": bc,
                    "rip_number": rip_num,
                })

        # Build the product row
        desc_parts = []
        if current_brand:
            desc_parts.append(current_brand)
        if current_description:
            desc_parts.append(_clean_cross_column_bleed(current_description))
        description = " ".join(desc_parts) if desc_parts else None

        # Parse BUY deal as RIP offers.
        # Fedway format: "1C$50" = 1 case tier, $50 save per case
        # "3C$120" = 3 case tier, $120 save (total for 3 cases)
        # "1B$700" = 1 bottle, $700 save
        rip_offers = []
        buy_deal = current_item.get("buy_deal") or ""
        for buy_m in re.finditer(r"(\d+)([CB])\\?\$(\d+(?:\.\d+)?)", buy_deal):
            qty = int(buy_m.group(1))
            unit = buy_m.group(2)
            amount = Decimal(buy_m.group(3))
            if unit == "C" and qty > 0:
                tier_label = f"{qty}CS"
                # save_amount is per case
                save_per_case = amount / qty if qty > 1 else amount
                effective_case = best_case_cost - save_per_case if best_case_cost else None
                rip_offers.append({
                    "rip_tier": tier_label,
                    "rip_save_amount": save_per_case,
                    "rip_case_price": effective_case,
                    "rip_btl_price": None,
                })
                if best_save is None or save_per_case > best_save:
                    best_save = save_per_case
            elif unit == "B" and qty > 0:
                tier_label = f"{qty}BT"
                save_per_btl = amount / qty if qty > 1 else amount
                rip_offers.append({
                    "rip_tier": tier_label,
                    "rip_save_amount": save_per_btl,
                    "rip_case_price": None,
                    "rip_btl_price": best_btl_cost - save_per_btl if best_btl_cost else None,
                })

        # Resolve the category using Fedway→DB mapping
        resolved_cat = _resolve_fedway_category(
            current_category, current_country, current_region,
        )

        row = {
            "code": current_item["code"],
            # Pipeline uses sub_brand for the product description
            "sub_brand": description,
            "brand_header": current_brand,
            "category": resolved_cat or current_category,
            "country": current_country,
            "region": current_region,
            "size": current_item.get("size"),
            "pack": current_item.get("pack"),
            "proof": current_item.get("proof"),
            "vintage": current_item.get("vintage"),
            "case_cost": best_case_cost,
            "btl_cost": best_btl_cost,
            "best_buy": current_item.get("buy_deal"),
            "best_rip": None,
            "attribs": current_item.get("attribs"),
            "rip_offers": rip_offers,
            "page": page_num,
            "lane": lane_idx,
            "source": source,
        }

        # Set best_rip summary
        if best_save is not None:
            row["best_rip"] = f"${best_save}"

        products.append(row)
        current_item = None
        current_description = None
        current_rips = []
        current_prices = []

    for _y, text in lines:
        line_type = _classify_line(text)

        if line_type == "skip":
            continue

        elif line_type == "header":
            upper = text.strip().upper()
            # If we already have a brand (set in THIS lane, not inherited) but
            # no item yet, a category word (like "VODKA" after "GILBEY'S F LA
            # GP JNC") is a sub-brand description, not a new section header.
            # Don't apply this for brands carried from a previous lane, as
            # those category headers are genuine section transitions.
            if current_brand and brand_set_in_lane and current_item is None and upper in _CATEGORY_WORDS:
                if current_description:
                    current_description += " " + text.strip()
                else:
                    current_description = text.strip()
                continue
            _flush()
            last_description = None
            current_description = None
            if upper in _CATEGORY_WORDS:
                if upper != current_category:
                    # Genuinely new category → reset brand
                    current_brand = None
                current_category = upper
                current_country = None
                current_region = None
            elif upper in _COUNTRY_REGION_WORDS:
                # Determine if it's a country or sub-region
                if upper in {
                    "USA", "SCOTLAND", "IRELAND", "CANADA", "JAPAN", "TAIWAN",
                    "SWEDEN", "FRANCE", "ITALY", "SPAIN", "PORTUGAL", "GERMANY",
                    "AUSTRIA", "AUSTRALIA", "NEW ZEALAND", "SOUTH AFRICA",
                    "CHILE", "ARGENTINA", "MEXICO", "BRAZIL", "ENGLAND",
                    "NETHERLANDS", "BELGIUM", "SWITZERLAND", "GREECE", "HUNGARY",
                    "CROATIA", "CZECH REPUBLIC", "POLAND", "INDIA", "CHINA",
                    "KOREA", "MARTINIQUE", "BARBADOS", "JAMAICA", "TRINIDAD",
                    "SLOVAKIA", "ROMANIA", "PERU", "URUGUAY", "COLOMBIA",
                    "GUATEMALA", "NICARAGUA", "PANAMA", "DOMINICAN REPUBLIC",
                    "ISRAEL", "LEBANON", "TURKEY", "MOROCCO", "THAILAND",
                    "PHILIPPINES", "PUERTO RICO", "WALES",
                }:
                    if upper != current_country:
                        # New country → new brands expected
                        current_brand = None
                    current_country = upper
                    current_region = None
                else:
                    current_region = upper

        elif line_type == "brand":
            _flush()
            current_brand = _extract_brand(text)
            brand_set_in_lane = True
            current_description = None
            last_description = None

        elif line_type == "item":
            _flush()
            saw_price_after_item = False
            parsed = _parse_item_line(text)
            if parsed:
                current_item = parsed

        elif line_type == "rip":
            rips = _parse_rip_line(text)
            current_rips.extend(rips)

        elif line_type == "price":
            price = _parse_price_line(text)
            if price:
                current_prices.append(price)
            if current_item is not None:
                saw_price_after_item = True

        elif line_type == "description":
            if saw_price_after_item:
                # Description after pricing → this is the NEXT product's description.
                # Flush the current product first.
                _flush()
                saw_price_after_item = False
                current_description = text.strip()
            elif current_item is not None:
                # Description after item code but before pricing → belongs to current item
                if current_description:
                    current_description += " " + text.strip()
                else:
                    current_description = text.strip()
            else:
                # Description before item code (most common Fedway layout)
                if current_description:
                    current_description += " " + text.strip()
                else:
                    current_description = text.strip()

    # Flush last product
    _flush()

    # Return products and ending context for lane continuity
    return products, {
        "brand": current_brand,
        "category": current_category,
        "country": current_country,
        "region": current_region,
    }


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------

def parse_main_catalog(
    pages: list,
    source: str,
    section_name: str = "SPIRITS",
) -> list[dict]:
    """Parse Fedway main catalog pages (Spirits, Wine, etc.).

    Args:
        pages: list of pdfplumber page objects
        source: source filename for provenance
        section_name: the section being parsed (SPIRITS, WINE, etc.)

    Returns:
        List of product dicts compatible with the pipeline's main_catalog format.
    """
    all_products = []
    # Track ending context from the previous lane for continuity.
    # Content flows: lane 0 → lane 1 → lane 2 → next page lane 0 → ...
    carry_ctx: dict | None = None

    for page in pages:
        page_num = page.page_number
        words = page.extract_words(
            keep_blank_chars=True,
            x_tolerance=3,
            y_tolerance=3,
        )

        # Skip header words (top ~35px is the "Order Phone / Section / Order Fax" bar)
        content_words = [w for w in words if w["top"] > 35]

        # Group into lanes
        lane_words = _group_words_into_lanes(content_words, CATALOG_LANES_X)

        for lane_idx, lw in enumerate(lane_words):
            if not lw:
                continue
            lines = _reconstruct_lines(lw)
            products, carry_ctx = _parse_lane(
                lines, page_num, lane_idx, source, section_name,
                initial_brand=carry_ctx.get("brand") if carry_ctx else None,
                initial_category=carry_ctx.get("category") if carry_ctx else None,
                initial_country=carry_ctx.get("country") if carry_ctx else None,
                initial_region=carry_ctx.get("region") if carry_ctx else None,
            )
            all_products.extend(products)

    return all_products
