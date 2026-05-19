"""seed distributors and canonical categories

Seeds the four NJ distributors we plan to support and a canonical category
taxonomy derived from inspecting the 2026-04 and 2026-05 Allied price books.
The ``raw_aliases`` JSONB array captures every OCR-garbled spelling we saw in
the source PDFs so the cleaning layer can normalise to the canonical slug.

Revision ID: 0002_seed_distributors_and_categories
Revises: 0001_initial
Create Date: 2026-05-19 12:30:00
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "0002_seed_distributors_and_categories"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DISTRIBUTORS = [
    # slug,         name,                                  state
    ("nj-allied",   "Allied Beverage Group",               "NJ"),
    ("nj-fedway",   "Fedway Associates",                   "NJ"),
    ("nj-opici",    "Opici Family Distributing",           "NJ"),
    ("nj-rndc",     "Republic National Distributing (NJ)", "NJ"),
]


CATEGORIES = [
    # slug, display_name, raw_aliases (every OCR garbling we have seen),
    # sort_order
    # ---- whiskey family ----
    ("blended-whiskey",          "Blended Whiskey",
     ["BLENDED WHISKEY"], 100),
    ("bottled-in-bond",          "Bottled in Bond",
     ["BOTTLED IN BOND"], 105),
    ("straight-whiskey-bourbon-moonshine", "Straight Whiskey, Bourbon & Moonshine",
     ["STRAIGHT WHISKEY, BOURBON, & MOONSHINE",
      "STRAIGHTW HISKEY,B OURBON,& M OONSHINE"], 110),
    ("single-barrel-bourbons",   "Single Barrel Bourbons",
     ["SINGLE BARREL BOURBONS"], 115),
    ("small-batch-bourbon",      "Small Batch Bourbon",
     ["SMALL BATCH BOURBON"], 120),
    ("sour-mash",                "Sour Mash", ["SOUR MASH"], 125),
    ("american-wheat-whiskey",   "American Wheat Whiskey",
     ["AMERICAN WHEAT WHISKEY"], 130),
    ("canadian-whiskey",         "Canadian Whiskey", ["CANADIAN WHISKEY"], 135),
    ("chinese-whiskey",          "Chinese Whiskey", ["CHINESE WHISKEY"], 140),
    ("corn-whiskey",             "Corn Whiskey", ["CORN WHISKEY"], 145),
    ("indian-whiskey",           "Indian Whiskey", ["INDIAN WHISKEY"], 150),
    ("irish-whiskey",            "Irish Whiskey", ["IRISH WHISKEY"], 155),
    ("japanese-whiskey",         "Japanese Whiskey", ["JAPANESE WHISKEY"], 160),
    ("rye-whiskey",              "Rye Whiskey", ["RYE WHISKEY"], 165),
    ("taiwanese-whisky",         "Taiwanese Whisky", ["TAIWANESE WHISKY"], 170),
    ("scotch-whiskey",           "Scotch Whiskey", ["SCOTCH WHISKEY"], 175),
    ("single-malts",             "Single Malts", ["SINGLE MALTS"], 180),
    ("vatted-malts",             "Vatted Malts", ["VATTED MALTS"], 185),
    ("white-whiskey",            "White Whiskey", ["WHITE WHISKEY"], 190),
    # ---- agave ----
    ("tequila",                  "Tequila", ["TEQUILA"], 200),
    ("cristalino",               "Cristalino", ["CRISTALINO"], 205),
    ("mezcal",                   "Mezcal", ["MEZCAL"], 210),
    # ---- vodka / gin / rum ----
    ("vodka",                    "Vodka", ["VODKA"], 220),
    ("gin",                      "Gin", ["GIN"], 230),
    ("genever",                  "Genever", ["GENEVER"], 235),
    ("rum",                      "Rum", ["RUM"], 240),
    # ---- brandy / cognac ----
    ("brandy",                   "Brandy", ["BRANDY"], 250),
    ("aguardiente",              "Aguardiente", ["AGUARDIENTE"], 255),
    ("armagnac",                 "Armagnac", ["ARMAGNAC"], 260),
    ("cognac",                   "Cognac", ["COGNAC"], 265),
    # ---- cocktails / specialty ----
    ("ready-to-serve",           "Ready to Serve", ["READY TO SERVE"], 280),
    ("cordials",                 "Cordials", ["CORDIALS"], 285),
    ("greek-spirits",            "Greek Spirits", ["GREEK SPIRITS"], 290),
    ("middle-eastern-specialties",
     "Middle Eastern Specialties", ["MIDDLE EASTERN SPECIALTIES"], 295),
    ("lifestyle-wine-spirits",
     "Lifestyle Wine & Spirits", ["LIFESTYLE WINE & SPIRITS"], 300),
    ("organic-wines-spirits",
     "Organic Wines & Spirits", ["ORGANIC WINES & SPIRITS"], 305),
    # ---- sparkling ----
    ("american-sparkling",       "American Sparkling", ["AMERICAN SPARKLING"], 320),
    ("austria-sparkling",        "Austria Sparkling", ["AUSTRIA SPARKLING"], 325),
    ("english-sparkling",        "English Sparkling", ["ENGLISH SPARKLING"], 330),
    ("french-sparkling",         "French Sparkling", ["FRENCH SPARKLING"], 335),
    ("argentina-sparkling",      "Argentina Sparkling", ["ARGENTINA SPARKLING"], 340),
    ("chile-sparkling",          "Chile Sparkling", ["CHILE SPARKLING"], 345),
    ("italian-sparkling",        "Italian Sparkling", ["ITALIAN SPARKLING"], 350),
    ("spain-sparkling",          "Spain Sparkling", ["SPAIN SPARKLING"], 355),
    # ---- wines by country ----
    ("wines-of-california",      "Wines of California", ["WINES OF CALIFORNIA"], 400),
    ("wines-of-new-jersey",      "Wines of New Jersey", ["WINES OF NEW JERSEY"], 405),
    ("wines-of-new-york-state",  "Wines of New York State", ["WINES OF NEW YORK STATE"], 410),
    ("wines-of-oregon",          "Wines of Oregon", ["WINES OF OREGON"], 415),
    ("wines-of-argentina",       "Wines of Argentina", ["WINES OF ARGENTINA"], 420),
    ("wines-of-australia",       "Wines of Australia", ["WINES OF AUSTRALIA"], 425),
    ("australian-fortified",     "Australian Fortified", ["AUSTRALIAN FORTIFIED"], 430),
    ("wines-of-austria",         "Wines of Austria", ["WINES OF AUSTRIA"], 435),
    ("wines-of-chile",           "Wines of Chile", ["WINES OF CHILE"], 440),
    ("wines-of-france",          "Wines of France", ["WINES OF FRANCE"], 445),
    ("bordeaux-red",             "Bordeaux Red", ["BORDEAUX RED"], 450),
    ("haut-medoc",               "Haut Medoc", ["HAUT MEDOC"], 455),
    ("burgundy-red",             "Burgundy Red", ["BURGUNDY RED"], 460),
    ("burgundy-white",           "Burgundy White", ["BURGUNDY WHITE"], 465),
    ("loire",                    "Loire", ["LOIRE"], 470),
    ("provence",                 "Provence", ["PROVENCE"], 475),
    ("rhone",                    "Rhone", ["RHONE"], 480),
    ("southwest",                "Southwest", ["SOUTHWEST"], 485),
    ("wines-of-georgia",         "Wines of Georgia", ["WINES OF GEORGIA"], 490),
    ("wines-of-italy",           "Wines of Italy", ["WINES OF ITALY"], 495),
    ("wines-of-japan-sake",      "Wines of Japan / Sake", ["WINES OF JAPAN / SAKE"], 500),
    ("wines-of-lebanon",         "Wines of Lebanon", ["WINES OF LEBANON"], 505),
    ("wines-of-portugal-table-wines",
     "Wines of Portugal - Table Wines",
     ["WINES OF PORTUGAL - TABLE WINES"], 510),
    ("wines-of-south-africa",    "Wines of South Africa", ["WINES OF SOUTH AFRICA"], 515),
    ("wines-of-spain",           "Wines of Spain", ["WINES OF SPAIN"], 520),
    ("port-madeira",             "Port & Madeira", ["PORT & MADEIRA"], 525),
    ("sherry",                   "Sherry", ["SHERRY"], 530),
    ("aperitifs",                "Aperitifs", ["APERITIFS"], 535),
    ("mead",                     "Mead", ["MEAD"], 540),
    # ---- non-alc / mixers / glass / hemp ----
    ("non-alcoholic-juices-mixers",
     "Non-alcoholic Juices & Mixers",
     ["NON-ALCOHOLIC JUICES & MIXERS"], 600),
    ("cans",                     "Cans", ["CANS"], 605),
    ("glassware",                "Glassware", ["GLASSWARE"], 610),
    ("hemp-beverages",           "Hemp Beverages", ["HEMP BEVERAGES"], 615),
]


def upgrade() -> None:
    conn = op.get_bind()
    # Distributors
    for slug, name, state in DISTRIBUTORS:
        conn.execute(
            text(
                "INSERT INTO distributors (slug, name, state) "
                "VALUES (:slug, :name, :state) "
                "ON CONFLICT (slug) DO NOTHING"
            ),
            {"slug": slug, "name": name, "state": state},
        )

    # Categories
    import json
    for slug, display, aliases, sort_order in CATEGORIES:
        conn.execute(
            text(
                "INSERT INTO categories (slug, display_name, raw_aliases, sort_order) "
                "VALUES (:slug, :display, CAST(:aliases AS jsonb), :sort_order) "
                "ON CONFLICT (slug) DO NOTHING"
            ),
            {
                "slug": slug,
                "display": display,
                "aliases": json.dumps(aliases),
                "sort_order": sort_order,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DELETE FROM categories WHERE slug = ANY(:slugs)"),
                 {"slugs": [c[0] for c in CATEGORIES]})
    conn.execute(text("DELETE FROM distributors WHERE slug = ANY(:slugs)"),
                 {"slugs": [d[0] for d in DISTRIBUTORS]})
