import json
import re
from typing import Dict, Any, List, Optional, Tuple


def _to_str(val: Any) -> Optional[str]:
    if val is None or val == "":
        return None
    return str(val).strip()


def _to_float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = re.sub(r"[^\d.-]", "", str(val))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _to_int(val: Any) -> Optional[int]:
    f = _to_float(val)
    return int(f) if f is not None else None


def _to_str_list(val: Any, delimiter: str = ",") -> List[str]:
    if val is None or val == "":
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    s = str(val).strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass
    # If category path contains ">", preserve the whole string as 1 category entry unless comma-separated
    if ">" in s and "," not in s:
        return [s]
    return [x.strip() for x in s.split(delimiter) if x.strip()]


def build_base_mapped_row(raw_row: Dict[str, Any], mapping_config: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Constructs the initial mapped dictionary based on user's field mapping rules.
    """
    extracted = {}

    for field_id, rule in mapping_config.items():
        mode = rule.get("mode", "none")
        source_col = rule.get("source_column", "")
        default_val = rule.get("default_value", "")

        val = None
        if mode == "column" and source_col in raw_row:
            val = raw_row[source_col]
            if (val is None or str(val).strip() == "") and default_val != "":
                val = default_val
        elif mode == "static":
            val = default_val

        extracted[field_id] = val

    return extracted


def apply_enrichment_to_extracted(
    extracted: Dict[str, Any],
    enrichment_outputs: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Merges AI enrichment outputs into the extracted field dictionary.
    """
    updated = dict(extracted)
    if "extra_attributes" not in updated:
        updated["extra_attributes"] = []

    for item in enrichment_outputs:
        if item.get("status") != "success":
            continue
        target = item.get("target_field", "")
        res = item.get("parsed_result")
        if res is None:
            continue

        if target == "attributes.tags" or target == "attributes[key='tags']":
            tags_list = res if isinstance(res, list) else _to_str_list(res)
            if tags_list:
                updated["extra_attributes"].append({
                    "key": "tags",
                    "value": {"text": tags_list, "numbers": []}
                })
        elif target == "attributes":
            if isinstance(res, list):
                for attr in res:
                    if isinstance(attr, dict) and "key" in attr:
                        updated["extra_attributes"].append(attr)
            elif isinstance(res, dict):
                for k, v in res.items():
                    t_list = [str(x) for x in v] if isinstance(v, list) else [str(v)]
                    updated["extra_attributes"].append({
                        "key": str(k),
                        "value": {"text": t_list, "numbers": []}
                    })
        elif target in ("tags", "categories", "brands", "sizes", "materials", "patterns", "conditions"):
            existing = _to_str_list(updated.get(target))
            new_items = res if isinstance(res, list) else _to_str_list(res)
            # Deduplicate preserving order
            merged = list(dict.fromkeys(existing + [str(x).strip() for x in new_items if str(x).strip()]))
            updated[target] = merged
        else:
            updated[target] = res

    return updated


def format_to_bigquery_schema(
    extracted: Dict[str, Any],
    project_id: str = "retail-search-jp-demo-minsoo"
) -> Dict[str, Any]:
    """
    Formats extracted & enriched values strictly into the 31 fields of AI Commerce Search BigQuery Schema.
    """
    prod_id = _to_str(extracted.get("id")) or "UNKNOWN_ID"
    prod_title = _to_str(extracted.get("title")) or "Untitled Product"

    prod_name = _to_str(extracted.get("name"))
    if not prod_name and prod_id != "UNKNOWN_ID":
        prod_name = f"projects/{project_id}/locations/global/catalogs/default_catalog/branches/0/products/{prod_id}"

    # Build priceInfo RECORD
    price_val = _to_float(extracted.get("priceInfo.price"))
    orig_price_val = _to_float(extracted.get("priceInfo.originalPrice"))
    cost_val = _to_float(extracted.get("priceInfo.cost"))
    currency = _to_str(extracted.get("priceInfo.currencyCode")) or "JPY"

    price_info = None
    if price_val is not None or orig_price_val is not None:
        price_info = {
            "currencyCode": currency,
            "price": price_val if price_val is not None else orig_price_val,
            "originalPrice": orig_price_val if orig_price_val is not None else price_val,
            "cost": cost_val,
            "priceEffectiveTime": _to_str(extracted.get("priceInfo.priceEffectiveTime")),
            "priceExpireTime": _to_str(extracted.get("priceInfo.priceExpireTime"))
        }

    # Build rating RECORD
    avg_rating = _to_float(extracted.get("rating.averageRating"))
    rating_count = _to_int(extracted.get("rating.ratingCount"))
    rating_record = None
    if avg_rating is not None or rating_count is not None:
        rating_record = {
            "ratingCount": rating_count or 0,
            "averageRating": avg_rating or 0.0,
            "ratingHistogram": []
        }

    # Build images REPEATED RECORD
    img_uris = _to_str_list(extracted.get("images.uri"))
    images_record = []
    for uri in img_uris:
        images_record.append({
            "uri": uri,
            "height": 300,
            "width": 300
        })

    # Build colorInfo RECORD
    colors = _to_str_list(extracted.get("colorInfo.colors"))
    color_families = _to_str_list(extracted.get("colorInfo.colorFamilies"))
    color_info = None
    if colors or color_families:
        color_info = {
            "colorFamilies": color_families if color_families else colors,
            "colors": colors if colors else color_families
        }

    # Build audience RECORD
    genders = _to_str_list(extracted.get("audience.genders"))
    age_groups = _to_str_list(extracted.get("audience.ageGroups"))
    audience_record = None
    if genders or age_groups:
        audience_record = {
            "genders": genders,
            "ageGroups": age_groups
        }

    # Build attributes REPEATED RECORD
    attributes_record = []
    raw_attr = extracted.get("attributes")
    if raw_attr:
        if isinstance(raw_attr, list):
            for item in raw_attr:
                if isinstance(item, dict) and "key" in item:
                    val = item.get("value", {})
                    t_list = val.get("text", []) if isinstance(val, dict) else [str(val)]
                    n_list = val.get("numbers", []) if isinstance(val, dict) else []
                    attributes_record.append({
                        "key": str(item["key"]),
                        "value": {"text": [str(x) for x in t_list], "numbers": [float(n) for n in n_list]}
                    })
        elif isinstance(raw_attr, str):
            try:
                parsed = json.loads(raw_attr)
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        attributes_record.append({
                            "key": str(k),
                            "value": {"text": [str(v)], "numbers": []}
                        })
            except Exception:
                pass

    # Merge extra_attributes from AI enrichment
    for extra in extracted.get("extra_attributes", []):
        key = extra.get("key")
        if not key:
            continue
        # Remove existing attribute with same key if present so we update cleanly
        attributes_record = [a for a in attributes_record if a.get("key") != key]
        val = extra.get("value", {})
        t_list = val.get("text", []) if isinstance(val, dict) else [str(val)]
        n_list = val.get("numbers", []) if isinstance(val, dict) else []
        attributes_record.append({
            "key": str(key),
            "value": {
                "text": [str(x) for x in t_list if str(x).strip()],
                "numbers": [float(n) for n in n_list]
            }
        })

    bq_row = {
        "name": prod_name,
        "id": prod_id,
        "type": _to_str(extracted.get("type")) or "PRIMARY",
        "primaryProductId": _to_str(extracted.get("primaryProductId")),
        "collectionMemberIds": _to_str_list(extracted.get("collectionMemberIds")),
        "gtin": _to_str(extracted.get("gtin")),
        "categories": _to_str_list(extracted.get("categories")),
        "title": prod_title,
        "brands": _to_str_list(extracted.get("brands")),
        "description": _to_str(extracted.get("description")),
        "languageCode": _to_str(extracted.get("languageCode")) or "ja",
        "attributes": attributes_record,
        "tags": _to_str_list(extracted.get("tags")),
        "priceInfo": price_info,
        "rating": rating_record,
        "expireTime": _to_str(extracted.get("expireTime")),
        "ttl": None,
        "availableTime": _to_str(extracted.get("availableTime")),
        "availability": _to_str(extracted.get("availability")) or "IN_STOCK",
        "availableQuantity": _to_int(extracted.get("availableQuantity")),
        "fulfillmentInfo": [],
        "uri": _to_str(extracted.get("uri")),
        "images": images_record,
        "audience": audience_record,
        "colorInfo": color_info,
        "sizes": _to_str_list(extracted.get("sizes")),
        "materials": _to_str_list(extracted.get("materials")),
        "patterns": _to_str_list(extracted.get("patterns")),
        "conditions": _to_str_list(extracted.get("conditions")) or ["NEW"],
        "publishTime": _to_str(extracted.get("publishTime")),
        "promotions": []
    }

    return bq_row


def validate_bigquery_row(bq_row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates a formatted BigQuery row against AI Commerce Search schema requirements.
    """
    errors = []
    warnings = []

    if not bq_row.get("id") or bq_row.get("id") == "UNKNOWN_ID":
        errors.append("必須項目 'id' が未設定です。")
    if not bq_row.get("title") or bq_row.get("title") == "Untitled Product":
        errors.append("必須項目 'title' が未設定です。")

    if not bq_row.get("categories"):
        warnings.append("'categories' が空です。検索精度向上のためカテゴリ設定を推奨します。")
    if not bq_row.get("tags") and not any(a.get("key") == "tags" for a in bq_row.get("attributes", [])):
        warnings.append("検索タグ（'tags' または 'attributes.tags'）が設定されていません。")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }
