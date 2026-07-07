#!/usr/bin/env python3
"""Build completeness_stats.json for the Geo Pharma admin panel.

Scans the four production data sources (USA extraction, USA product index,
Canada enriched CSV, Mexico data directory) and emits a single JSON file whose
shape matches the ``CompletenessStats`` TypeScript interface from
``/tmp/admin_panel/architecture_spec.md`` (§3).

The script is idempotent: running it repeatedly produces the same JSON (apart
from the ``generated_at`` timestamp).  Run it after any pipeline update to
refresh the stats consumed by the frontend ``AdminPanel`` component.

Usage
-----
    python3 build_completeness_stats.py [--out PATH] [--no-copy]

Outputs
-------
1.  ``<pipeline_dir>/completeness_stats.json`` (default, next to this script)
2.  ``geo_pharma_app/amplify/functions/adminStats/data/completeness_stats.json``
    (auto-copied unless ``--no-copy`` is given) so the Amplify ``adminStats``
    serverless function bundles it and serves it privately via
    ``GET /api/admin/stats`` (authenticated, HTTP-only cookie). The file is no
    longer placed in ``public/data/`` — that would expose it as a static,
    world-readable asset with no authentication.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path configuration
# ---------------------------------------------------------------------------

PIPELINE_DIR = Path(__file__).resolve().parent
PRODUCTION_DIR = PIPELINE_DIR.parent  # .../graph_workshop/scripts/production

USA_EXTRACTION = (
    PRODUCTION_DIR / "geo-ingestor/data_to_publish/full_geo_extraction_v25.jsonl"
)
USA_PRODUCT_INDEX = (
    PRODUCTION_DIR
    / "pricing/frontend/geo_pharma_app/public/product-ndc-index.json"
)
CANADA_DIR = PRODUCTION_DIR / "pricing/data/Canada"
CANADA_CSV = CANADA_DIR / "canadian_enriched.csv"
CANADA_PRICING_FILES = {
    "BC": CANADA_DIR / "bc_pharmacare/bc_pharmacare_plan_i_pricing.json",
    "NS": CANADA_DIR / "nova_scotia_data/nova_scotia_pharmacare.json",
    "ODB": CANADA_DIR / "ontario_odb/ontario_odb_formulary.json",
}
MEXICO_DIR = PRODUCTION_DIR / "pricing/data/Mexico"

MEXICO_SOURCE_FILES = {
    "SEMAR": MEXICO_DIR / "semar/semar_procurement.json",
    "INPRFM": MEXICO_DIR / "inprfm/inprfm_procurement.json",
    "ISSSTE": MEXICO_DIR / "issste/issste_catalog.json",
    "PROFECO": MEXICO_DIR / "profeco/profeco_retail_prices.json",
}

MEXICO_MATCHES = MEXICO_DIR / "mexican_rxcui_matches.json"
MEXICO_MATCH_SUMMARY = MEXICO_DIR / "mexico_matching_summary.json"
MEXICO_DATA_SUMMARY = MEXICO_DIR / "mexico_data_summary.json"
MEXICO_CACHE = MEXICO_DIR / "scd_sbd_cache.json"
MEXICO_ES_EN_MAP = MEXICO_DIR / "spanish_english_ingredient_map.json"

FRONTEND_DATA_DIR = (
    PRODUCTION_DIR
    / "pricing/frontend/geo_pharma_app/amplify/functions/adminStats/data"
)

RESEARCH_BRIEF_PATH = "/tmp/admin_panel/research_brief.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _human_size(num_bytes: float) -> str:
    """Return a human-readable size string (KB/MB/GB)."""
    if num_bytes >= 1_000_000_000:
        return f"{num_bytes / 1_000_000_000:.2f} GB"
    if num_bytes >= 1_000_000:
        return f"{num_bytes / 1_000_000:.2f} MB"
    return f"{num_bytes / 1_000:.0f} KB"


def _file_size_mb(path: Path) -> float:
    return round(os.path.getsize(path) / 1_000_000, 2)


def _count_jsonl_lines(path: Path) -> int:
    """Count lines in a (potentially large) JSONL file without loading it."""
    count = 0
    with open(path, "rb") as fh:
        for _ in fh:
            count += 1
    return count


def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# USA extraction scan
# ---------------------------------------------------------------------------

def scan_usa_extraction(path: Path) -> dict[str, Any]:
    """Stream ``full_geo_extraction_v25.jsonl`` and tally entity / NDC counts.

    Each line is one ingredient (IN).  The ``connections`` field is a dict with
    keys ``scd``, ``sbd``, ``bn``, ``pin``, ``min``, ``df``, each mapping to a
    list of entity objects.  NDC records live inside SCD/SBD entities as a
    nested ``ndcs`` list.
    """
    type_counts: dict[str, int] = {
        "IN": 0, "SCD": 0, "SBD": 0, "PIN": 0, "MIN": 0, "BN": 0, "DF": 0,
    }
    unique_ndcs: set[str] = set()
    unique_set_ids: set[str] = set()
    nested_ndc_records = 0
    ingredients_with_connections = 0
    ingredients_without_connections = 0

    conn_key_to_type = {
        "scd": "SCD", "sbd": "SBD", "bn": "BN",
        "pin": "PIN", "min": "MIN", "df": "DF",
    }

    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            type_counts["IN"] += 1
            connections = rec.get("connections") or {}
            has_conn = False
            for conn_key, entity_type in conn_key_to_type.items():
                entities = connections.get(conn_key) or []
                if entities:
                    has_conn = True
                type_counts[entity_type] += len(entities)
                # NDC records live inside SCD/SBD entities.
                if conn_key in ("scd", "sbd"):
                    for entity in entities:
                        for ndc_rec in entity.get("ndcs") or []:
                            nested_ndc_records += 1
                            ndc_val = ndc_rec.get("ndc")
                            if ndc_val:
                                unique_ndcs.add(ndc_val)
                            set_id = ndc_rec.get("spl_set_id")
                            if set_id:
                                unique_set_ids.add(set_id)
            if has_conn:
                ingredients_with_connections += 1
            else:
                ingredients_without_connections += 1

    total_entities = sum(type_counts.values())

    return {
        "source_file": path.name,
        "source_size_mb": _file_size_mb(path),
        "entities": {
            "ingredient_IN": type_counts["IN"],
            "clinical_drug_SCD": type_counts["SCD"],
            "branded_drug_SBD": type_counts["SBD"],
            "packaged_clinical_PIN": type_counts["PIN"],
            "manufactured_item_MIN": type_counts["MIN"],
            "brand_name_BN": type_counts["BN"],
            "dose_form_DF": type_counts["DF"],
            "total_entities": total_entities,
        },
        "ndc_records": nested_ndc_records,
        "unique_ndcs": len(unique_ndcs),
        "unique_set_ids": len(unique_set_ids),
        "orphan_ingredients": ingredients_without_connections,
    }


# ---------------------------------------------------------------------------
# USA product index scan
# ---------------------------------------------------------------------------

def scan_usa_product_index(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read ``product-ndc-index.json`` and extract declared + recounted stats.

    Returns a ``(product_index, cross_refs)`` tuple.
    """
    data = _load_json(path)

    meta = {
        "declared_total_products": data.get("totalProducts", 0),
        "products_with_ndc": data.get("productsWithNDC", 0),
        "products_with_set_id": data.get("productsWithSetId", 0),
        "products_with_din": data.get("productsWithDIN", 0),
        "products_with_either": data.get("productsWithEither", 0),
    }

    # Recount from the products array (dict keyed by rxcui).
    products = data.get("products") or {}
    if isinstance(products, dict):
        products_list = list(products.values())
    elif isinstance(products, list):
        products_list = products
    else:
        products_list = []

    scd_count = 0
    sbd_count = 0
    for prod in products_list:
        ptype = (prod.get("type") or "").upper()
        if ptype == "SCD":
            scd_count += 1
        elif ptype == "SBD":
            sbd_count += 1

    unlinked = meta["declared_total_products"] - len(products_list)

    cross_refs = {
        "canadian_products": len(data.get("canadianProducts") or {}),
        "us_rxcui_to_canadian_mappings": len(data.get("usRxcuiToCanadian") or {}),
        "canadian_dins": len(data.get("canadianDins") or {}),
        "ingredient_blacklist": len(data.get("ingredientBlacklist") or []),
    }

    return {
        "declared_total_products": meta["declared_total_products"],
        "products_with_ndc": meta["products_with_ndc"],
        "products_with_set_id": meta["products_with_set_id"],
        "products_with_din": meta["products_with_din"],
        "products_with_either": meta["products_with_either"],
        "scd_count": scd_count,
        "sbd_count": sbd_count,
        "unlinked_products": unlinked,
    }, cross_refs


# ---------------------------------------------------------------------------
# Canada scan
# ---------------------------------------------------------------------------

# Map each provincial source to its price field name.  BC and NS use
# ``effective_price``; Ontario ODB uses ``individual_price``.  See
# /tmp/admin_panel/data_audit_report.md §Issue 1 for field documentation.
CANADA_PRICE_FIELDS = {
    "BC": "effective_price",
    "NS": "effective_price",
    "ODB": "individual_price",
}


def scan_canada_pricing_files() -> list[dict[str, Any]]:
    """Scan the three provincial pricing JSON files and tally priced records.

    Each file has the shape ``{metadata: {...}, records: [{din, ..., <price_field>, ...}]}``.
    Returns one dict per source with total records, priced records, price
    range, and DIN coverage.  A record is counted as "priced" when its price
    field is non-null and non-empty.
    """
    sources: list[dict[str, Any]] = []
    for name, path in CANADA_PRICING_FILES.items():
        price_field = CANADA_PRICE_FIELDS[name]
        entry: dict[str, Any] = {
            "name": name,
            "source_file": path.name,
            "price_field": price_field,
            "exists": path.is_file(),
            "total_records": 0,
            "priced_records": 0,
            "price_min": None,
            "price_max": None,
            "din_populated": 0,
            "size_mb": 0.0,
        }
        if not entry["exists"]:
            sources.append(entry)
            continue
        entry["size_mb"] = _file_size_mb(path)
        try:
            data = _load_json(path)
        except Exception as exc:  # pragma: no cover - defensive
            entry["error"] = f"Failed to load: {exc}"
            sources.append(entry)
            continue
        records = data.get("records") or []
        prices: list[float] = []
        priced = 0
        din_count = 0
        for rec in records:
            if rec.get("din"):
                din_count += 1
            val = rec.get(price_field)
            if val is not None and str(val).strip() != "":
                priced += 1
                try:
                    prices.append(float(val))
                except (TypeError, ValueError):
                    pass
        entry["total_records"] = len(records)
        entry["priced_records"] = priced
        entry["din_populated"] = din_count
        if prices:
            entry["price_min"] = round(min(prices), 4)
            entry["price_max"] = round(max(prices), 4)
        sources.append(entry)
    return sources


def scan_canada(path: Path) -> dict[str, Any]:
    """Stream ``canadian_enriched.csv`` and compute coverage metrics."""
    total_rows = 0
    din_nonempty = 0
    matching_key_nonempty = 0
    atc_nonempty = 0
    biosimilar_true = 0
    type_breakdown: dict[str, int] = {}
    columns: list[str] = []

    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = list(reader.fieldnames or [])
        for row in reader:
            total_rows += 1
            if (row.get("din") or "").strip():
                din_nonempty += 1
            if (row.get("matching_key") or "").strip():
                matching_key_nonempty += 1
            if (row.get("atc_code") or "").strip():
                atc_nonempty += 1
            if (row.get("is_biosimilar") or "").strip().lower() in (
                "true", "1", "yes",
            ):
                biosimilar_true += 1
            rtype = (row.get("type") or "").strip()
            if rtype:
                type_breakdown[rtype] = type_breakdown.get(rtype, 0) + 1

    atc_missing = total_rows - atc_nonempty
    din_pct = round(din_nonempty / total_rows * 100, 1) if total_rows else 0.0
    mk_pct = round(matching_key_nonempty / total_rows * 100, 1) if total_rows else 0.0
    atc_pct = round(atc_nonempty / total_rows * 100, 1) if total_rows else 0.0
    bio_pct = round(biosimilar_true / total_rows * 100, 1) if total_rows else 0.0

    # ---- Provincial pricing files -------------------------------------
    pricing_sources = scan_canada_pricing_files()
    total_priced_records = sum(s["priced_records"] for s in pricing_sources)
    total_pricing_records = sum(s["total_records"] for s in pricing_sources)
    has_price_data = total_priced_records > 0

    pricing_notes: list[str] = []
    for src in pricing_sources:
        if not src["exists"]:
            pricing_notes.append(f"{src['name']}: file not found at {src['source_file']}.")
            continue
        pricing_notes.append(
            f"{src['name']} ({src['source_file']}): {src['priced_records']:,} priced / "
            f"{src['total_records']:,} total records (field={src['price_field']}, "
            f"price range {src['price_min']}–{src['price_max']} CAD)."
        )

    return {
        "source_file": path.name,
        "source_size_mb": _file_size_mb(path),
        "total_rows": total_rows,
        "columns": len(columns),
        "coverage": {
            "din_pct": din_pct,
            "matching_key_pct": mk_pct,
            "atc_pct": atc_pct,
            "atc_missing_rows": atc_missing,
            "biosimilar_count": biosimilar_true,
            "biosimilar_pct": bio_pct,
            "has_price_data": has_price_data,
            "priced_records_total": total_priced_records,
            "pricing_records_total": total_pricing_records,
        },
        "pricing_sources": pricing_sources,
        "type_breakdown": type_breakdown,
        "notes": [
            "Bilingual EN/FR fields: canonical/canonical_f, form/form_f, "
            "route_of_admin/route_of_admin_f, ingredient_full/ingredient_f.",
            f"CSV is product/DIN metadata only — pricing comes from {len(pricing_sources)} "
            f"provincial formulary JSON files ({total_priced_records:,} priced records total).",
            f"Type distribution: {', '.join(f'{k}={v}' for k, v in sorted(type_breakdown.items(), key=lambda x: -x[1]))}.",
            *pricing_notes,
        ],
    }


# ---------------------------------------------------------------------------
# Mexico scan
# ---------------------------------------------------------------------------

def scan_mexico(mexico_dir: Path) -> dict[str, Any]:
    """Scan Mexico sources and RxCUI matching artifacts.

    PROFECO is ~6 GB; we do **not** load it.  Record counts and file sizes come
    from ``mexico_data_summary.json`` (already curated by the pipeline) and the
    on-disk file size.
    """
    data_summary = _load_json(MEXICO_DATA_SUMMARY)
    match_summary = _load_json(MEXICO_MATCH_SUMMARY)

    # ---- Sources table -------------------------------------------------
    sources_meta = data_summary.get("sources", {})
    sources: list[dict[str, Any]] = []
    total_records = 0
    total_size_bytes = 0

    for name in ("SEMAR", "INPRFM", "ISSSTE", "PROFECO"):
        key = name.lower()
        meta = sources_meta.get(key, {})
        file_path = MEXICO_SOURCE_FILES[name]
        try:
            fsize = os.path.getsize(file_path)
        except OSError:
            fsize = meta.get("file_size_bytes", 0)
        records = meta.get("record_count", 0)
        total_records += records
        total_size_bytes += fsize
        fields = meta.get("fields_available", {})
        sources.append({
            "name": name,
            "file": file_path.name,
            "records": records,
            "size": _human_size(fsize),
            "has_prices": bool(fields.get("unit_price", False)),
            "date_range": meta.get("date_range", "N/A"),
        })

    # ---- RxCUI matching ------------------------------------------------
    overall = match_summary.get("overall", {})
    ds = match_summary.get("data_sources", {})

    def _src_match(src_key: str) -> dict[str, Any]:
        d = ds.get(src_key, {})
        conf = d.get("confidence", {})
        return {
            "source": src_key.upper(),
            "total_records": d.get("total_records", 0),
            "matched": d.get("matched_records") or d.get("matched_combos", 0),
            "match_rate_pct": d.get("match_rate") or d.get("combo_match_rate", 0.0),
            "high_conf": conf.get("high", 0),
            "medium": conf.get("medium", 0),
            "low": conf.get("low", 0),
        }

    by_source = [
        _src_match("semar"),
        _src_match("inprfm"),
        _src_match("profeco"),
    ]

    total_matches = overall.get("total_matches", 0)
    high_conf = overall.get("confidence", {}).get("high", 0)
    med_conf = overall.get("confidence", {}).get("medium", 0)
    low_conf = overall.get("confidence", {}).get("low", 0)
    high_pct = round(high_conf / total_matches * 100, 1) if total_matches else 0.0

    scd_matched, sbd_matched = _scd_sbd_from_matches()

    rxcui_matching = {
        "total_matches": total_matches,
        "high_confidence": high_conf,
        "medium_confidence": med_conf,
        "low_confidence": low_conf,
        "high_confidence_pct": high_pct,
        "scd_matched": scd_matched,
        "sbd_matched": sbd_matched,
        "by_source": by_source,
    }

    # ---- Ingredient cache ---------------------------------------------
    try:
        cache = _load_json(MEXICO_CACHE)
        cache_len = len(cache)
        # Cache entries use singular keys: "scd" and "sbd" (lists).
        ingredients_with_scd = sum(
            1 for v in cache.values()
            if isinstance(v, dict) and v.get("scd")
        )
        ingredients_with_sbd = sum(
            1 for v in cache.values()
            if isinstance(v, dict) and v.get("sbd")
        )
        total_scds = sum(
            len(v.get("scd") or []) for v in cache.values()
            if isinstance(v, dict)
        )
        total_sbds = sum(
            len(v.get("sbd") or []) for v in cache.values()
            if isinstance(v, dict)
        )
    except Exception:
        cache_len = 0
        ingredients_with_scd = 0
        ingredients_with_sbd = 0
        total_scds = 0
        total_sbds = 0

    try:
        es_en_map = _load_json(MEXICO_ES_EN_MAP)
        es_en_entries = len(es_en_map)
    except Exception:
        es_en_entries = 0

    return {
        "total_records": total_records,
        "total_size_gb": round(total_size_bytes / 1_000_000_000, 2),
        "sources": sources,
        "rxcui_matching": rxcui_matching,
        "ingredient_cache": {
            "unique_ingredients_queried": cache_len,
            "ingredients_with_scd": ingredients_with_scd,
            "ingredients_with_sbd": ingredients_with_sbd,
            "total_scds_cached": total_scds,
            "total_sbds_cached": total_sbds,
            "spanish_english_map_entries": es_en_entries,
        },
    }


def _scd_sbd_from_matches() -> tuple[int, int]:
    """Count SCD/SBD matches from ``mexican_rxcui_matches.json``."""
    try:
        matches = _load_json(MEXICO_MATCHES)
    except Exception:
        return 0, 0
    scd = 0
    sbd = 0
    for m in matches:
        if m.get("matched_scd_rxcui"):
            scd += 1
        if m.get("matched_sbd_rxcui"):
            sbd += 1
    return scd, sbd


# ---------------------------------------------------------------------------
# Cross-country bridges & gaps
# ---------------------------------------------------------------------------

def build_cross_country(
    usa_entities: dict[str, Any],
    usa_cross_refs: dict[str, Any],
    canada_rows: int,
    mexico: dict[str, Any],
) -> dict[str, Any]:
    """Derive bridge stats and the 19-gap list.

    ``usa_entities`` is the ``entities`` sub-dict (with ``ingredient_IN`` etc.)
    from ``scan_usa_extraction``.
    """
    us_ingredients = usa_entities["ingredient_IN"]
    ca_products = usa_cross_refs["canadian_products"]
    us_ca_mappings = usa_cross_refs["us_rxcui_to_canadian_mappings"]

    us_ca_coverage = round(us_ca_mappings / us_ingredients * 100, 1) if us_ingredients else 0.0
    us_ca_unmapped = us_ingredients - us_ca_mappings

    mx_us_matches = mexico["rxcui_matching"]["total_matches"]
    mx_ingredients_queried = mexico["ingredient_cache"]["unique_ingredients_queried"]
    mx_ingredients_with_scd = mexico["ingredient_cache"]["ingredients_with_scd"]
    # Bridge coverage is ingredient-level: how many of the queried Mexican
    # ingredients have at least one SCD/SBD match in RxNorm.  The raw match
    # count (3,147) is surfaced separately in the summary band and Mexico tab.
    mx_us_coverage = round(mx_ingredients_with_scd / mx_ingredients_queried * 100, 1) if mx_ingredients_queried else 0.0
    mx_us_unmapped = mx_ingredients_queried - mx_ingredients_with_scd

    return {
        "us_to_canada": {
            "mappings": us_ca_mappings,
            "source_total": us_ingredients,
            "target_total": ca_products,
            "coverage_pct": us_ca_coverage,
            "unmapped": us_ca_unmapped,
        },
        "mexico_to_us": {
            "mappings": mx_ingredients_with_scd,
            "source_total": mx_ingredients_queried,
            "target_total": usa_entities["clinical_drug_SCD"] + usa_entities["branded_drug_SBD"],
            "coverage_pct": mx_us_coverage,
            "unmapped": mx_us_unmapped,
        },
        "mexico_to_canada": {
            "direct_linkage": False,
            "hops_required": 2,
        },
    }


GAPS_DEFINITION: list[dict[str, Any]] = [
    # USA
    {"id": 1, "severity": "critical", "region": "USA",
     "text": "7,703 products without NDC linkage — totalProducts=20295 vs productsWithNDC=12592; dose-form/PIN entries never received NDCs, absent from frontend product index."},
    {"id": 2, "severity": "medium", "region": "USA",
     "text": "DIN coverage gap in product index — products array shows hasDIN=0 for all 12,592 entries; DIN linkage lives only in separate canadianProducts section (5,016); not unified at product level."},
    {"id": 3, "severity": "high", "region": "USA",
     "text": "canadianDins field is empty (length 0) despite productsWithDIN=5016; declared DIN list never populated."},
    {"id": 4, "severity": "medium", "region": "USA",
     "text": "MIN unique rxcuis (978) < MIN entries (3,068) — many manufactured items share rxcuis or lack them; possible dedup opportunity."},
    {"id": 5, "severity": "medium", "region": "USA",
     "text": "BN unique rxcuis (2,663) > IN count (2,634) — slightly more brand-name rxcuis than ingredients; some brands map to ingredients not in the IN set."},
    # Canada
    {"id": 6, "severity": "low", "region": "Canada",
     "text": "13 rows missing ATC code (99.9% coverage — minor)."},
    {"id": 7, "severity": "medium", "region": "Canada",
     "text": "No explicit SBD-equivalent count — CSV has type column (cSCD seen); distribution of cSBD/cPIN counts unknown."},
    {"id": 8, "severity": "low", "region": "Canada",
     "text": "Biosimilar segment small (224, 1.8%) — may be complete for the market but worth verifying against Health Canada's biosimilar list."},
    {"id": 9, "severity": "low", "region": "Canada",
     "text": "canadian_enriched.csv is metadata-only (no prices) — provincial pricing from BC/NS/ODB JSON files is scanned separately (~18,827 priced records across 3 sources)."},
    # Mexico
    {"id": 10, "severity": "high", "region": "Mexico",
     "text": "ISSSTE has NO prices (catalog only, unit_price=false) — 1,292 records cannot be used for price comparison."},
    {"id": 11, "severity": "critical", "region": "Mexico",
     "text": "PROFECO lacks clave_ssa (always null) — cannot link to SSA-coded regulatory data."},
    {"id": 12, "severity": "high", "region": "Mexico",
     "text": "PROFECO match confidence: 0 high-confidence matches out of 403; all matches are medium (180) or low (223) — weakest match quality of all sources."},
    {"id": 13, "severity": "high", "region": "Mexico",
     "text": "SBD coverage near-zero in Mexico — only 1 SBD match and 2 SBDs cached vs 2,566 SCD matches and 3,499 SCDs cached; Mexican data is essentially SCD-only."},
    {"id": 14, "severity": "low", "region": "Mexico",
     "text": "PROFECO is 6.05 GB — single largest file by far; loading it fully is expensive; record count (6,050,348) is estimated from source-field occurrences."},
    {"id": 15, "severity": "low", "region": "Mexico",
     "text": "Top unmatched drugs are non-medicinal (Agua, Alcohol, Algodón, Gasa, Venditas) — expected; these are medical supplies, not pharmaceuticals."},
    {"id": 16, "severity": "low", "region": "Mexico",
     "text": "Spanish→English ingredient map: 646 entries for 413 unique ingredients queried — good coverage, but 646 map entries suggest some ambiguity/duplicates worth cleaning."},
    # Cross-source
    {"id": 17, "severity": "high", "region": "Cross-source",
     "text": "US→Canada bridge: only 2,370 rxcui mappings for 2,634 US ingredients (89.8%) and 5,016 Canadian products (47.1%); ~364 US ingredients have no Canadian counterpart mapped."},
    {"id": 18, "severity": "medium", "region": "Cross-source",
     "text": "Mexico→US bridge: 413 ingredients queried, 245 with SCD (59.2%); 168 ingredients (40.8%) have no SCD match — likely OTC/supplies/topicals not in RxNorm."},
    {"id": 19, "severity": "critical", "region": "Cross-source",
     "text": "No Mexico→Canada direct linkage — Mexico matches to US RxCUI only; Canada linkage is US→Canada; Mexico→Canada requires a two-hop join through US rxcui."},
]


# ---------------------------------------------------------------------------
# Summary band
# ---------------------------------------------------------------------------

def build_summary(
    usa_entity_data: dict[str, Any],
    usa_stats: dict[str, Any],
    canada: dict[str, Any],
    mexico: dict[str, Any],
) -> dict[str, Any]:
    return {
        "us_entities": usa_entity_data["entities"]["total_entities"],
        "us_ndcs": usa_stats["unique_ndcs"],
        "canada_rows": canada["total_rows"],
        "canada_priced_records": canada["coverage"].get("priced_records_total", 0),
        "mexico_records": mexico["total_records"],
        "rxcui_bridges_us_ca": usa_stats["cross_refs"]["us_rxcui_to_canadian_mappings"],
        "rxcui_bridges_mx_us": mexico["rxcui_matching"]["total_matches"],
        "high_confidence_mx_pct": mexico["rxcui_matching"]["high_confidence_pct"],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_stats() -> dict[str, Any]:
    """Run all scanners and assemble the CompletenessStats document."""
    print(f"[1/4] Scanning USA extraction: {USA_EXTRACTION.name} …", file=sys.stderr)
    usa_entity_data = scan_usa_extraction(USA_EXTRACTION)

    print(f"[2/4] Scanning USA product index: {USA_PRODUCT_INDEX.name} …", file=sys.stderr)
    product_index, cross_refs = scan_usa_product_index(USA_PRODUCT_INDEX)
    usa_stats = {
        **usa_entity_data,
        "product_index": product_index,
        "cross_refs": cross_refs,
    }

    print(f"[3/4] Scanning Canada CSV + provincial pricing files …", file=sys.stderr)
    canada_stats = scan_canada(CANADA_CSV)

    print(f"[4/4] Scanning Mexico data directory …", file=sys.stderr)
    mexico_stats = scan_mexico(MEXICO_DIR)

    cross_country = build_cross_country(
        usa_entity_data["entities"], cross_refs, canada_stats["total_rows"], mexico_stats,
    )
    summary = build_summary(usa_entity_data, usa_stats, canada_stats, mexico_stats)

    # Filter out gaps that have been resolved
    active_gaps = []
    for gap in GAPS_DEFINITION:
        # Gap #3: canadianDins empty — resolved when canadianDins is populated
        if gap.get("id") == 3 and cross_refs.get("canadian_dins", 0) > 0:
            continue
        active_gaps.append(gap)

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_brief": RESEARCH_BRIEF_PATH,
        "summary": summary,
        "usa": usa_stats,
        "canada": canada_stats,
        "mexico": mexico_stats,
        "cross_country": cross_country,
        "gaps": active_gaps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(PIPELINE_DIR / "completeness_stats.json"),
        help="Output path for completeness_stats.json (default: next to this script).",
    )
    parser.add_argument(
        "--no-copy",
        action="store_true",
        help="Do not copy the output to the Amplify admin-auth function data dir.",
    )
    args = parser.parse_args()

    stats = build_stats()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(stats, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"Wrote {out_path}", file=sys.stderr)

    if not args.no_copy:
        dest = FRONTEND_DATA_DIR / "completeness_stats.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out_path, dest)
        print(f"Copied to {dest}", file=sys.stderr)

    # Echo the JSON to stdout so callers can capture it if desired.
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
