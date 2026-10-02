from datetime import date

import odoo_import.lead_service as lead_service
from odoo_streamlit.campaigns import (
    ACTIVE_TEMPORARY_CAMPAIGN,
    resolve_lead_tag,
)


def test_campaign_uses_jeremie_label_during_visibility_window():
    assert resolve_lead_tag(True, date(2026, 10, 11)) == (
        "Salon de la Boucherie Angers 2026"
    )


def test_campaign_falls_back_to_prospection_when_inactive_or_expired():
    assert resolve_lead_tag(False, date(2026, 10, 11)) == lead_service.PROSPECTION_TAG
    assert resolve_lead_tag(True, date(2026, 10, 13)) == lead_service.PROSPECTION_TAG


def test_build_vals_uses_campaign_tag_for_new_lead(monkeypatch):
    captured = {}

    def fake_find_or_create_tag(models, uid, tag_name):
        captured["uid"] = uid
        captured["tag_name"] = tag_name
        return 123

    monkeypatch.setattr(lead_service, "find_or_create_tag", fake_find_or_create_tag)

    vals = lead_service.build_vals_from_answers(
        {"_uid": 7, "partner_name": "Boucherie Test"},
        team_id=3,
        seller_user_id=9,
        replace_tags=True,
        tag_name=ACTIVE_TEMPORARY_CAMPAIGN.odoo_tag,
    )

    assert captured == {
        "uid": 7,
        "tag_name": "Salon de la Boucherie Angers 2026",
    }
    assert vals["tag_ids"] == [(6, 0, [123])]


def test_build_vals_adds_campaign_tag_without_replacing_existing_tags(monkeypatch):
    monkeypatch.setattr(
        lead_service,
        "find_or_create_tag",
        lambda models, uid, tag_name: 456,
    )

    vals = lead_service.build_vals_from_answers(
        {"_uid": 7, "partner_name": "Boucherie Existante"},
        team_id=3,
        seller_user_id=9,
        replace_tags=False,
        existing_description="Note existante",
        tag_name=ACTIVE_TEMPORARY_CAMPAIGN.odoo_tag,
    )

    assert vals["tag_ids"] == [(4, 456)]


def test_build_vals_keeps_default_prospection_tag(monkeypatch):
    captured = {}

    def fake_find_or_create_tag(models, uid, tag_name):
        captured["tag_name"] = tag_name
        return 789

    monkeypatch.setattr(lead_service, "find_or_create_tag", fake_find_or_create_tag)

    vals = lead_service.build_vals_from_answers(
        {"_uid": 7, "partner_name": "Prospect Normal"},
        team_id=3,
        seller_user_id=9,
        replace_tags=True,
    )

    assert captured["tag_name"] == "Prospection"
    assert vals["tag_ids"] == [(6, 0, [789])]
