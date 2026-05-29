"""Tests for official checklist templates."""

from app.checklists import CHECKLISTS


def test_arr_and_neurips_checklists_keep_official_item_counts():
    assert len(CHECKLISTS["arr"]["items"]) == 18
    assert CHECKLISTS["arr"]["items"][0]["id"] == "A1"
    assert CHECKLISTS["arr"]["items"][-1]["id"] == "E1"

    assert len(CHECKLISTS["neurips"]["items"]) == 16
    assert CHECKLISTS["neurips"]["items"][0]["id"] == "1"
    assert CHECKLISTS["neurips"]["items"][-1]["id"] == "16"
