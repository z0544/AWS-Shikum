from strands import tool
from strands_tools import retrieve
from boto3.session import Session
from botocore.exceptions import ClientError
import csv
import io
import json
import os
from collections import defaultdict
from pathlib import Path

boto_session = Session()
# Region where the Bedrock Knowledge Base retrieve tool runs (fixed for this project).
region = "eu-north-1"
# AgentCore / Docker often runs in another region — capture once before we touch os.environ.
_runtime_aws_region = (
    boto_session.region_name
    or os.environ.get("AWS_DEFAULT_REGION")
    or "us-west-2"
)
KNOWLEDGE_BASE_ID = "D2QPGXCHQW"

os.environ["KNOWLEDGE_BASE_ID"] = KNOWLEDGE_BASE_ID
os.environ["AWS_REGION"] = region
os.environ["MIN_SCORE"] = "0.4"

# ──────────────────────────────────────────────────────────────────────────────
# Rehab catalog: S3 layout + local fallback
# ──────────────────────────────────────────────────────────────────────────────
# S3: s3://$REHAB_DATA_S3_BUCKET/$REHAB_DATA_S3_PREFIX/{sku_catalog,suppliers,supplier_sku_links}.csv
# See rehab_s3_layout.json. CSVs must be UTF-8 (e.g. output of convert_csvs.py).
_DATA_DIR = Path(__file__).parent
_REHAB_BUCKET = os.environ.get("REHAB_DATA_S3_BUCKET", "").strip()
_REHAB_PREFIX = os.environ.get("REHAB_DATA_S3_PREFIX", "rehab-data/v1").strip().strip("/")
_REHAB_S3_REGION = (
    os.environ.get("REHAB_DATA_S3_REGION", "").strip()
    or os.environ.get("AWS_DEFAULT_REGION", "").strip()
    or _runtime_aws_region
)

_SKU_CSV = "sku_catalog.csv"
_SUP_CSV = "suppliers.csv"
_LINK_CSV = "supplier_sku_links.csv"


def _s3_client():
    return boto_session.client("s3", region_name=_REHAB_S3_REGION)


def _s3_get_utf8_text(key: str) -> str | None:
    if not _REHAB_BUCKET:
        return None
    full_key = f"{_REHAB_PREFIX}/{key}" if _REHAB_PREFIX else key
    try:
        resp = _s3_client().get_object(Bucket=_REHAB_BUCKET, Key=full_key)
        return resp["Body"].read().decode("utf-8")
    except ClientError as e:
        print(f"[Tools] S3 get_object s3://{_REHAB_BUCKET}/{full_key} failed: {e}")
        return None
    except Exception as e:
        print(f"[Tools] S3 read error: {e}")
        return None


def _read_text_source(filename: str) -> str | None:
    """Prefer S3 when bucket configured; else local file in agent directory."""
    if _REHAB_BUCKET:
        t = _s3_get_utf8_text(filename)
        if t is not None:
            return t
        print(f"[Tools] Falling back to local {filename} after S3 miss.")
    path = _DATA_DIR / filename
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _normalize_sku(value: str) -> str:
    """SKU codes may have leading zeros in links; catalog often without."""
    return (value or "").strip().lstrip("0") or "0"


def _normalize_supplier_id(value: str) -> str:
    return (value or "").strip()


def _parse_sku_catalog(text: str) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    """Summary sku -> row (first wins for find_suppliers); plus all rows per sku."""
    summary: dict[str, dict] = {}
    all_rows: dict[str, list[dict]] = defaultdict(list)
    f = io.StringIO(text)
    for row in csv.DictReader(f):
        sku = _normalize_sku(row.get("sku", ""))
        if not sku or sku == "0":
            continue
        clean = {k: (v or "").strip() for k, v in row.items()}
        all_rows[sku].append(clean)
        if sku not in summary:
            summary[sku] = {
                "sku": sku,
                "description": clean.get("description", ""),
                "amount": clean.get("amount", ""),
                "frequency": clean.get("frequency", ""),
            }
    return summary, dict(all_rows)


def _parse_links(text: str) -> tuple[dict[str, list[str]], list[dict], dict[str, list[dict]]]:
    """Active-only index sku->supplier_ids; all link rows; supplier_id->active link rows."""
    by_sku: dict[str, list[str]] = defaultdict(list)
    all_rows: list[dict] = []
    by_sup: dict[str, list[dict]] = defaultdict(list)
    f = io.StringIO(text)
    for row in csv.DictReader(f):
        clean = {k: (v or "").strip() for k, v in row.items()}
        all_rows.append(clean)
        is_active = clean.get("is_active", "")
        if is_active and is_active != "כן":
            continue
        sku = _normalize_sku(clean.get("sku", ""))
        sup_id = _normalize_supplier_id(clean.get("supplier_id_rehab", ""))
        if sku and sup_id:
            if sup_id not in by_sku[sku]:
                by_sku[sku].append(sup_id)
            by_sup[sup_id].append(clean)
    return dict(by_sku), all_rows, dict(by_sup)


def _parse_suppliers(text: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    f = io.StringIO(text)
    for row in csv.DictReader(f):
        clean = {k: (v or "").strip() for k, v in row.items()}
        sup_id = _normalize_supplier_id(clean.get("supplier_id_rehab", ""))
        if sup_id:
            result[sup_id] = clean
    return result


def _load_rehab_datasets() -> tuple[
    dict[str, dict],
    dict[str, list[dict]],
    dict[str, list[str]],
    list[dict],
    dict[str, list[dict]],
    dict[str, dict],
]:
    sku_t = _read_text_source(_SKU_CSV)
    link_t = _read_text_source(_LINK_CSV)
    sup_t = _read_text_source(_SUP_CSV)

    if not sku_t:
        print(f"[Tools] WARNING: {_SKU_CSV} missing (S3/local).")
        return {}, {}, [], [], {}, {}
    skus, sku_rows = _parse_sku_catalog(sku_t)
    links_by_sku: dict[str, list[str]] = {}
    link_all: list[dict] = []
    links_by_sup: dict[str, list[dict]] = {}
    if link_t:
        links_by_sku, link_all, links_by_sup = _parse_links(link_t)
    suppliers: dict[str, dict] = _parse_suppliers(sup_t) if sup_t else {}
    if not sup_t:
        print(f"[Tools] WARNING: {_SUP_CSV} missing — supplier details empty.")

    src = f"s3://{_REHAB_BUCKET}/{_REHAB_PREFIX}/" if _REHAB_BUCKET else str(_DATA_DIR)
    print(
        f"[Tools] Rehab data source: {src} — skus: {len(skus)}, "
        f"link-skus: {len(links_by_sku)}, suppliers: {len(suppliers)}, link-rows: {len(link_all)}"
    )
    return skus, sku_rows, links_by_sku, link_all, links_by_sup, suppliers


_SKUS, _SKU_ROWS, _LINKS, _LINK_ROWS_ALL, _LINKS_BY_SUPPLIER, _SUPPLIERS = _load_rehab_datasets()


def _format_row_he(title: str, row: dict) -> str:
    lines = [title]
    for k, v in row.items():
        if v:
            lines.append(f"  • {k}: {v}")
    return "\n".join(lines)


@tool
def search_knowledge_base(query: str) -> str:
    """Semantic search in the department regulations PDF documents."""
    try:
        tool_use = {"toolUseId": "search_kb", "input": {"text": query}}
        result = retrieve.retrieve(tool_use)
        if result["status"] == "success":
            return result["content"][0]["text"]
        else:
            return f"Unable to access knowledge base. Error: {result['content'][0]['text']}"
    except Exception as e:
        return f"Unable to access knowledge base. Error: {str(e)}"


@tool
def get_claim_status(claim_id: str) -> str:
    """Deterministic retrieval of a specific claim status from the CSV file based on claim ID."""
    file_path = "rights_claims.csv"

    if not os.path.exists(file_path):
        return "System Error: Data file is missing."

    try:
        with open(file_path, mode="r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if str(row.get("claim_id", "")).strip() == str(claim_id).strip():
                    return (
                        f"Claim data found:\n"
                        f"- Claim ID: {row.get('claim_id')}\n"
                        f"- Claim Type: {row.get('claim_type')}\n"
                        f"- Description: {row.get('claim_text')}\n"
                        f"- Status: {row.get('status')} \n"
                        f"- District: {row.get('district')}"
                    )
        return f"No claim found in the system for ID: {claim_id}."
    except Exception as e:
        return f"Error reading data: {str(e)}"


@tool
def find_suppliers_for_need(query: str) -> str:
    """Find active rehabilitation suppliers that can provide a specific item or service.

    Accepts either:
      - A free-text Hebrew need such as "כיסא גלגלים", "משקפי ראייה", "טיפול שיניים".
      - A SKU code (digits, 3-6 chars) such as "10177" or "618".

    The tool returns up to 3 best-matching SKUs. For each SKU it lists at most
    10 active suppliers (name, city, phone, e-mail and profession).
    Use this tool whenever the user asks WHO can provide a specific item/service.
    """
    q = (query or "").strip()
    if not q:
        return "יש להזין צורך (תיאור בעברית או מק\"ט)."

    if not _SKUS:
        return "מאגר המקטים אינו זמין כעת. (בדוק קבצי CSV או S3 REHAB_DATA_S3_BUCKET)"

    matching: list[dict] = []
    digits_only = q.replace(" ", "").replace("-", "")

    if digits_only.isdigit() and 3 <= len(digits_only) <= 6:
        key = _normalize_sku(digits_only)
        if key in _SKUS:
            matching = [_SKUS[key]]
    else:
        for info in _SKUS.values():
            if q in info["description"]:
                matching.append(info)
                if len(matching) >= 5:
                    break

        if not matching:
            terms = [t for t in q.split() if len(t.strip()) >= 2]
            if terms:
                scored = []
                for info in _SKUS.values():
                    desc = info["description"]
                    hits = sum(1 for t in terms if t in desc)
                    if hits:
                        scored.append((hits, info))
                scored.sort(key=lambda x: -x[0])
                matching = [info for _, info in scored[:5]]

    if not matching:
        return f"לא נמצאו מקטים התואמים ל-\"{q}\"."

    lines: list[str] = [f"נמצאו {len(matching)} מקטים מתאימים:"]

    for sku_info in matching[:3]:
        sku = sku_info["sku"]
        desc = sku_info["description"]
        amount = sku_info.get("amount", "")
        freq = sku_info.get("frequency", "")

        lines.append("")
        lines.append(f"📦 מק\"ט {sku}: {desc}")
        if amount:
            lines.append(f"   • סכום זכאות: {amount}")
        if freq and freq not in {"0", "999"}:
            lines.append(f"   • תדירות (חודשים): {freq}")

        sup_ids = _LINKS.get(sku, [])
        if not sup_ids:
            lines.append("   ⚠️ אין ספקים פעילים רשומים למק\"ט זה.")
            continue

        rich = [_SUPPLIERS[s] for s in sup_ids if s in _SUPPLIERS]

        if not rich:
            lines.append(
                f"   ℹ️ ישנם {len(sup_ids)} ספקים רשומים אך פרטיהם אינם בטבלת הספקים הפעילים."
            )
            continue

        lines.append(f"   ספקים פעילים ({min(len(rich), 10)} מתוך {len(rich)}):")
        for s in rich[:10]:
            name = s.get("name", "")
            city = s.get("city", "")
            phone = s.get("mobile") or s.get("work_phone") or s.get("landline") or ""
            email = s.get("email", "")
            prof = s.get("profession", "")

            parts = [f"      • {name}"]
            if city:
                parts.append(city)
            if prof:
                parts.append(prof)
            if phone:
                parts.append(f"טל' {phone}")
            if email:
                parts.append(email)
            lines.append(" | ".join(parts))

    return "\n".join(lines)


@tool
def lookup_rehab_catalog(
    makat: str = "",
    mispar_sapak_shikum: str = "",
    shem_sapak_chliga: str = "",
    teur_mikzoi: str = "",
) -> str:
    """שליפה מלאה ממאגר המקטים/ספקים/קישורים (CSV ב-S3 או מקומי).

    השתמש בכלי כשהמשתמש מבקש את כל הפרטים המדויקים על מק\"ט, ספק, או קשר ביניהם.
    לפחות אחד מהפרמטרים חייב להיות לא ריק.

    - makat: קוד מק\"ט (מספרים, עם או בלי אפסים מובילים).
    - mispar_sapak_shikum: מספר ספק שיקום (כפי שמופיע בדוח הספקים).
    - shem_sapak_chliga: מחרוזת חיפוש בשם הספק (ללא רווחים מיותרים).
    - teur_mikzoi: מילים מתוך תיאור הפריט במאגר המקטים (חיפוש טקסט חופשי).
    """
    m = (makat or "").strip()
    sid = (mispar_sapak_shikum or "").strip()
    name_q = (shem_sapak_chliga or "").strip()
    desc_q = (teur_mikzoi or "").strip()

    if not any([m, sid, name_q, desc_q]):
        return "יש למלא לפחות אחד: makat, mispar_sapak_shikum, shem_sapak_chliga, או teur_mikzoi."

    if not _SKUS and not _SUPPLIERS:
        return "מאגר הנתונים ריק. בדוק העלאה ל-S3 או קיום קבצי CSV מקומיים."

    out: list[str] = []
    data_src = (
        f"s3://{_REHAB_BUCKET}/{_REHAB_PREFIX}/" if _REHAB_BUCKET else f"מקומי: {_DATA_DIR}"
    )
    out.append(f"מקור נתונים: {data_src}")
    out.append("")

    # --- By supplier id ---
    if sid:
        sid_n = sid.lstrip("0") or "0"
        keys_to_try = [sid, sid.zfill(6) if sid.isdigit() else sid]
        sup_row = None
        for k in keys_to_try:
            if k in _SUPPLIERS:
                sup_row = _SUPPLIERS[k]
                break
            kn = k.lstrip("0") or "0"
            for pk, pv in _SUPPLIERS.items():
                if pk.lstrip("0") == kn or pk == k:
                    sup_row = pv
                    break
            if sup_row:
                break
        if not sup_row:
            out.append(f"לא נמצא ספק עם מזהה שיקום \"{sid}\".")
        else:
            out.append(_format_row_he("=== פרטי ספק (מלא) ===", sup_row))
            rehab_id = _normalize_supplier_id(sup_row.get("supplier_id_rehab", ""))
            lk = _LINKS_BY_SUPPLIER.get(rehab_id, [])
            if not lk:
                zid = sid.zfill(6) if sid.isdigit() else sid
                for k, v in _LINKS_BY_SUPPLIER.items():
                    if k.lstrip("0") == sid_n or k == zid:
                        lk = v
                        break
            skus_u = sorted({_normalize_sku(r.get("sku", "")) for r in lk if r.get("sku")})
            out.append("")
            out.append(f"=== מקטים מקושרים (פעילים, כן) — {len(skus_u)} ייחודיים ===")
            for sku_key in skus_u[:80]:
                rows = _SKU_ROWS.get(sku_key, [])
                if rows:
                    desc0 = rows[0].get("description", "")
                    out.append(f"  • מק\"ט {sku_key}: {desc0}  (שורות קטלוג: {len(rows)})")
                else:
                    out.append(f"  • מק\"ט {sku_key}: (אין שורה בקטלוג)")
            if len(skus_u) > 80:
                out.append(f"  … ועוד {len(skus_u) - 80} מקטים (קיצור פלט).")

    # --- By supplier name substring ---
    if name_q and not sid:
        hits = []
        for srow in _SUPPLIERS.values():
            nm = srow.get("name", "")
            if name_q in nm:
                hits.append(srow)
        hits = hits[:40]
        out.append(f"=== ספקים ששמותיהם מכילים \"{name_q}\" ({len(hits)} תוצאות מקסימום) ===")
        for srow in hits:
            out.append(_format_row_he(f"— {srow.get('name', '')} —", srow))
            out.append("")

    # --- By SKU ---
    if m:
        sku_key = _normalize_sku(m.replace(" ", "").replace("-", ""))
        rows = _SKU_ROWS.get(sku_key, [])
        if not rows:
            out.append(f"לא נמצא מק\"ט \"{m}\" בקטלוג.")
        else:
            out.append(f"=== כל שורות הקטלוג למק\"ט {sku_key} ({len(rows)} שורות) ===")
            for i, r in enumerate(rows, 1):
                out.append(_format_row_he(f"— שורה {i} —", r))
                out.append("")
            sup_ids = _LINKS.get(sku_key, [])
            out.append(f"=== ספקים פעילים למק\"ט (מקושרים, כן) — {len(sup_ids)} ===")
            for sup_id in sup_ids[:100]:
                sr = _SUPPLIERS.get(sup_id)
                if sr:
                    out.append(_format_row_he(f"ספק {sup_id}", sr))
                else:
                    out.append(f"ספק {sup_id}: אין רשומה מלאה בדוח הספקים.")
                out.append("")
            if len(sup_ids) > 100:
                out.append(f"… ועוד {len(sup_ids) - 100} ספקים.")
            link_for_sku = [
                r
                for r in _LINK_ROWS_ALL
                if _normalize_sku(r.get("sku", "")) == sku_key
            ][:80]
            out.append("")
            out.append(
                f"=== שורות קישור מקט–ספק מהקובץ (עד 80, כולל שדה is_active) — {len(link_for_sku)} ==="
            )
            for i, r in enumerate(link_for_sku, 1):
                out.append(_format_row_he(f"— קישור {i} —", r))
                out.append("")

    # --- Free-text on catalog description ---
    if desc_q and not m:
        matched_skus: list[str] = []
        for sku_key, rows in _SKU_ROWS.items():
            if any(desc_q in (rr.get("description") or "") for rr in rows):
                matched_skus.append(sku_key)
        matched_skus.sort(key=lambda x: int(x) if x.isdigit() else 0)
        matched_skus = matched_skus[:25]
        out.append(f"=== מקטים שתיאור הפריט מכיל \"{desc_q}\" (עד 25) ===")
        for sku_key in matched_skus:
            rows = _SKU_ROWS[sku_key]
            out.append(f"מק\"ט {sku_key}: {len(rows)} שורות קטלוג; תיאור ראשון: {rows[0].get('description', '')}")

    return "\n".join(out) if len(out) > 2 else "\n".join(out)


def _export_layout_hint() -> None:
    """Optional: print S3 keys from rehab_s3_layout.json once."""
    p = _DATA_DIR / "rehab_s3_layout.json"
    if p.exists() and _REHAB_BUCKET:
        try:
            spec = json.loads(p.read_text(encoding="utf-8"))
            objs = spec.get("objects", {})
            print(f"[Tools] S3 object map: {objs}")
        except Exception:
            pass


_export_layout_hint()
