from .models import RulePack


_BASIS = ("shareholding", "synthetic")

OFAC = RulePack(
    id="OFAC",
    version="ofac-2014-faq398-402+2026-03+shareholding-only",
    authorities=("OFAC",),
    threshold=50.0,
    inclusive=True,
    aggregate=True,
    control_limb=False,
    basis_accepted=_BASIS,
    citations=(
        "OFAC Revised Guidance on Entities Owned by Persons Whose Property Is Blocked (2014)",
        "OFAC FAQs 398-402: https://ofac.treasury.gov/faqs/401",
        "OFAC Guidance on Sham Transactions and Sanctions Evasion (31 Mar 2026)",
    ),
    interpretation_note=(
        "Modeled input: direct and indirect ownership is aggregated, including ownership through entities "
        "that themselves meet the 50 Percent Rule; threshold is inclusive (50% or more), based on OFAC FAQ 401."
    ),
)

EU = RulePack(
    id="EU",
    version="eu-bp-11623-24+reg-2025-2037+shareholding-only",
    authorities=("EU",),
    threshold=50.0,
    inclusive=True,
    aggregate=True,
    control_limb=True,
    basis_accepted=_BASIS,
    citations=(
        "Council Best Practices 11623/24 paras 63-67: https://data.consilium.europa.eu/doc/document/ST-11623-2024-INIT/en/pdf",
        "Commission FAQ 8-9",
        "Regulation (EU) 2025/2037 Art. 1(i): https://eur-lex.europa.eu/eli/reg/2025/2037/oj/eng",
    ),
    interpretation_note=(
        "Modeled input: Regulation 2025/2037 Article 1(i) says 50% or more for Regulation 269/2014; "
        "aggregation/control follow Council Best Practices 11623/24 paras 63-65 and are rebuttable case by case. "
        "Chain arithmetic uses full attribution because EU texts give no explicit chain example; that is ShellTrace's interpretation."
    ),
)

UK = RulePack(
    id="UK",
    version="ofsi-gg-4.1-2026-05+shareholding-only",
    authorities=("UK",),
    threshold=50.0,
    inclusive=False,
    aggregate=False,
    control_limb=True,
    basis_accepted=_BASIS,
    citations=(
        "OFSI General Guidance 4.1 (updated 12 May 2026): https://www.gov.uk/government/publications/financial-sanctions-general-guidance/uk-financial-sanctions-general-guidance",
        "Russia (Sanctions) (EU Exit) Regulations 2019 reg 7",
        "OFAC-OFSI joint comparative guidance (23 Jun 2026)",
    ),
    interpretation_note=(
        "Modeled input: more than 50% plus the listed control grounds in OFSI General Guidance 4.1. "
        "Different designated persons' holdings are not simply aggregated absent a joint arrangement or control of rights (OFSI 4.1.4)."
    ),
)

PACKS = {pack.id: pack for pack in (OFAC, EU, UK)}


def get_pack(pack_id: str) -> RulePack:
    return PACKS[pack_id]
