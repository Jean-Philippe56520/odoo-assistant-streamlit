from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from odoo_import.lead_service import PROSPECTION_TAG


@dataclass(frozen=True)
class LeadCampaign:
    """Configuration d'une campagne temporaire de saisie de pistes."""

    key: str
    title: str
    button_label: str
    odoo_tag: str
    event_dates_label: str
    visible_from: date
    visible_until: date

    def is_available(self, on_date: date | None = None) -> bool:
        check_date = on_date or date.today()
        return self.visible_from <= check_date <= self.visible_until


# Pour un prochain salon, cette configuration peut être remplacée sans modifier
# la logique du formulaire ni la logique d'écriture Odoo.
ACTIVE_TEMPORARY_CAMPAIGN = LeadCampaign(
    key="salon_bct_angers_2026",
    title="Salon BCT Angers 2026",
    button_label="Activer le mode Salon BCT",
    odoo_tag="Salon de la Boucherie Angers 2026",
    event_dates_label="11 et 12 octobre 2026",
    visible_from=date(2026, 10, 2),
    visible_until=date(2026, 10, 12),
)


def resolve_lead_tag(
    campaign_active: bool,
    on_date: date | None = None,
    campaign: LeadCampaign = ACTIVE_TEMPORARY_CAMPAIGN,
) -> str:
    """Retourne l'étiquette à utiliser sans jamais altérer le mode normal."""
    if campaign_active and campaign.is_available(on_date):
        return campaign.odoo_tag
    return PROSPECTION_TAG
