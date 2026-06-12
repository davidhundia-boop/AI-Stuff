import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import quant_score as qs  # noqa: E402


def test_sector_mask_exists_for_financials():
    assert "gross_margin" in qs.SECTOR_MASKS["financial-services"]
