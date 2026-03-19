# Tracking Link Builder

Applies test values (click ID, device ID) to AppsFlyer tracking links.

## Quick Usage (for AI Agents)

When a user shares an AppsFlyer link with device ID and click ID, **run the script immediately**:

```bash
cd "Tracking Links" && python3 builder.py \
  --link "<APPSFLYER_URL>" \
  --device-id "<DEVICE_ID>" \
  --click-id "<CLICK_ID>"
```

**Do NOT:**
- Explore the codebase first
- Read files before running
- Make documentation changes unless explicitly requested

## Web UI

Open `index.html` in a browser for interactive use.

## Parameters

| Flag | Description | Required |
|------|-------------|----------|
| `--link` | Raw AppsFlyer tracking link | Yes |
| `--device-id` | GAID/AAID (UUID or SHA-1 hash) | Yes |
| `--click-id` | Test click ID value | No (default: `Onurthegamer`) |

## Example

```bash
python3 builder.py \
  --link "https://app.appsflyer.com/com.makemytrip?pid=onedigitalturbine_int&clickid=[ClickID]&sha1_advertising_id=[AAID_SHA1]" \
  --device-id "65a53a0f-87a1-43aa-9df8-da3ed7f6c954" \
  --click-id "Onurthegamer"
```

The script auto-detects:
- Integration type (Legacy vs OneDigitalTurbine) from `pid`
- Whether SHA-1 hashing is needed (from `sha1_*` params)
- Auto-hashes UUID device IDs when SHA-1 is required
