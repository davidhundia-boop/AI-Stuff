#!/usr/bin/env python3
"""
Tracking Link Builder
Applies test values (click ID, device ID) to a raw tracking link
based on integration type and parameter conventions.

Performance optimized version with:
- Pre-compiled regex patterns
- Frozenset for O(1) lookups
- Efficient string operations
- Single-pass parameter scanning
"""

import re
import hashlib
import argparse
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse, quote
from functools import lru_cache

# ── Constants ─────────────────────────────────────────────────────────────────

ODT_PID = "onedigitalturbine_int"
DEFAULT_CLICK_ID = "David1"

# ODT id2 channel-specific values
ODT_ID2_MAP = {
    "ODS": "dV9XX0xY",
    "DSP": "ckFCRVBW",
}

# Plain (non-SHA1) advertising ID param names as frozenset for O(1) lookup
PLAIN_AD_ID_PARAMS = frozenset({
    "advertising_id", "android_id", "device_id",
    "idfa", "gaid", "aaid", "af_idfa", "af_android_id",
})

# ── Pre-compiled regex patterns ───────────────────────────────────────────────

UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
SHA1_RE = re.compile(r'^[0-9a-f]{40}$', re.IGNORECASE)
SHA1_PARAM_RE = re.compile(r'sha1', re.IGNORECASE)

# ── Helpers (optimized) ───────────────────────────────────────────────────────

def is_uuid(value: str) -> bool:
    return UUID_RE.match(value.strip()) is not None


def is_sha1_hash(value: str) -> bool:
    return SHA1_RE.match(value.strip()) is not None


@lru_cache(maxsize=128)
def sha1_hash(value: str) -> str:
    """Return lowercase hex SHA-1 digest of value (lowercased before hashing).
    Cached for repeated calls with same value."""
    return hashlib.sha1(value.strip().lower().encode('utf-8')).hexdigest()


def resolve_device_id(device_id: str, sha1_required: bool) -> tuple[str, str | None]:
    """
    Return (resolved_device_id, info_message).
    If sha1_required:
      - already a SHA1 hash  → use as-is
      - UUID                 → hash it, return info message
      - anything else        → raise ValueError
    If not sha1_required:
      - use raw value as-is (warn if format looks unexpected)
    """
    device_id = device_id.strip()
    info = None

    if sha1_required:
        if is_sha1_hash(device_id):
            return device_id.lower(), info
        if is_uuid(device_id):
            hashed = sha1_hash(device_id)
            info = f"Device ID auto-hashed (SHA-1): {hashed}"
            return hashed, info
        raise ValueError(
            "The tracking link requires a SHA-1 hashed Device ID, but the value "
            "provided doesn't look like a UUID or a 40-char hex hash.\n"
            "  UUID example:  278d8c12-bdfc-4843-a4cd-043631edab0a\n"
            "  SHA-1 example: e9b0c0da16e7daca61515124da91f9f9b9ed2b80"
        )
    
    if not is_uuid(device_id) and not is_sha1_hash(device_id):
        info = "WARNING: Device ID format looks unexpected — verify the output."
    return device_id, info


def _custom_quote(s: str, safe: str, encoding: str, errors: str) -> str:
    """Custom quote function preserving bracket placeholders."""
    return quote(s, safe="[]")


# ── Core builder (optimized single-pass) ──────────────────────────────────────

def build_link(
    raw_link: str,
    device_id: str,
    click_id_val: str = DEFAULT_CLICK_ID,
    product_type: str | None = None,
) -> dict:
    """
    Process a raw tracking link and return a result dict:
      {
        "output_url":        str,
        "integration_type":  "Legacy" | "OneDigitalTurbine",
        "pid":               str,
        "sha1_required":     bool,
        "product_type":      str | None,
        "changes":           list[dict],   # {param, old, new, desc}
        "messages":          list[str],    # info / warnings
      }
    
    Performance: Single-pass parameter scanning with early detection.
    
    Args:
        raw_link: The tracking link URL to process
        device_id: GAID/AAID (UUID or SHA-1 hash)
        click_id_val: Test click ID value
        product_type: For ODT integrations, specify "ODS" or "DSP" to set id2
    """
    parsed = urlparse(raw_link.strip())
    params = parse_qsl(parsed.query, keep_blank_values=True)

    # Single-pass scan for pid, sha1 keys, click_id key, and id2 key
    pid = ""
    sha1_keys = []
    click_key = None
    has_id2 = False
    
    for key, value in params:
        key_lower = key.lower()
        if key == "pid":
            pid = value
        if SHA1_PARAM_RE.search(key):
            sha1_keys.append(key)
        if click_key is None and key_lower.replace("_", "") == "clickid":
            click_key = key
        if key == "id2":
            has_id2 = True

    is_odt = pid == ODT_PID
    integration_type = "OneDigitalTurbine" if is_odt else "Legacy"
    sha1_required = bool(sha1_keys)

    messages: list[str] = []
    changes: list[dict] = []

    # Validate product_type for ODT integrations with id2 parameter
    if is_odt and has_id2:
        if not product_type:
            raise ValueError(
                "OneDigitalTurbine integration with id2 parameter requires --product-type.\n"
                "  Use: --product-type ODS  or  --product-type DSP"
            )
        if product_type not in ODT_ID2_MAP:
            raise ValueError(
                f"Invalid product type '{product_type}'. Must be 'ODS' or 'DSP'."
            )

    resolved_id, id_msg = resolve_device_id(device_id, sha1_required)
    if id_msg:
        messages.append(id_msg)

    # Convert sha1_keys to set for O(1) lookup
    sha1_keys_set = frozenset(sha1_keys)

    # Build new params with substitutions
    new_params = []
    for key, value in params:
        new_value = value

        if click_key is not None and key == click_key:
            new_value = click_id_val
            changes.append({"param": key, "old": value, "new": new_value, "desc": "Test click ID"})
        elif key in sha1_keys_set:
            new_value = resolved_id
            changes.append({"param": key, "old": value, "new": new_value, "desc": "Hashed Device ID (SHA-1)"})
        elif not sha1_required and key.lower() in PLAIN_AD_ID_PARAMS:
            new_value = resolved_id
            changes.append({"param": key, "old": value, "new": new_value, "desc": "Raw Device ID"})
        elif is_odt and key == "id2" and product_type:
            new_value = ODT_ID2_MAP[product_type]
            changes.append({"param": key, "old": value, "new": new_value, "desc": f"Channel ID ({product_type})"})

        new_params.append((key, new_value))

    # Preserve [ ] characters in placeholder values (e.g. [CAMPAIGN_ID])
    output_url = urlunparse(parsed._replace(
        query=urlencode(new_params, quote_via=_custom_quote)
    ))

    return {
        "output_url":       output_url,
        "integration_type": integration_type,
        "pid":              pid,
        "sha1_required":    sha1_required,
        "product_type":     product_type if is_odt else None,
        "changes":          changes,
        "messages":         messages,
    }

# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Build a test-ready tracking link by injecting click ID and device ID.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python builder.py \\
    --link "https://app.appsflyer.com/com.example?pid=appia_int&clickid=[ClickID]&sha1_advertising_id=[AAID_SHA1]" \\
    --device-id "278d8c12-bdfc-4843-a4cd-043631edab0a"

  python builder.py \\
    --link "https://app.appsflyer.com/..." \\
    --device-id "e9b0c0da16e7daca61515124da91f9f9b9ed2b80" \\
    --click-id "TestClick99"

  # OneDigitalTurbine with product type (required for ODT with id2):
  python builder.py \\
    --link "https://app.appsflyer.com/...?pid=onedigitalturbine_int&id2=[CHANNEL]&..." \\
    --device-id "278d8c12-bdfc-4843-a4cd-043631edab0a" \\
    --product-type ODS
        """,
    )
    parser.add_argument("--link",      required=True, help="Raw tracking link")
    parser.add_argument("--device-id", required=True, help="Your GAID/AAID (UUID or SHA-1 hash)")
    parser.add_argument("--click-id",  default=DEFAULT_CLICK_ID, help=f"Test click ID value (default: {DEFAULT_CLICK_ID})")
    parser.add_argument("--product-type", choices=["ODS", "DSP"], help="Product type for ODT integrations (sets id2 channel value)")

    args = parser.parse_args()

    try:
        result = build_link(
            raw_link=args.link,
            device_id=args.device_id,
            click_id_val=args.click_id,
            product_type=args.product_type,
        )
    except ValueError as e:
        print(f"\n[ERROR] {e}\n")
        raise SystemExit(1)

    # ── Print summary ──────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print(f"  Integration : {result['integration_type']}")
    print(f"  PID         : {result['pid'] or '(none)'}")
    print(f"  SHA-1 mode  : {'yes' if result['sha1_required'] else 'no'}")
    if result['product_type']:
        print(f"  Product     : {result['product_type']} (id2={ODT_ID2_MAP[result['product_type']]})")
    print("=" * 70)

    for msg in result["messages"]:
        prefix = "[WARN]" if msg.startswith("WARNING") else "[INFO]"
        print(f"  {prefix} {msg}")

    if result["changes"]:
        print()
        print("  Changes applied:")
        for c in result["changes"]:
            print(f"    [+] {c['param']}  ->  {c['new']}   ({c['desc']})")
    else:
        print()
        print("  No parameters were modified.")

    print()
    print("  Output URL:")
    print(f"  {result['output_url']}")
    print()


if __name__ == "__main__":
    main()
