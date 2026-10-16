from dataclasses import dataclass

@dataclass(frozen=True)
class GoldenCase:
    id: str
    entity_id: str
    as_of: str
    packs: tuple[str, ...]
    expect_disposition: str
    expect_verdicts: dict[str, str]
    expect_proof: set[str] | None
    expect_decisive: set[str] | None
    category: str

ALL = ("OFAC", "EU", "UK")
B, I, P, N = "BLOCKED", "INDETERMINATE", "PRESUMED_CONTROLLED", "NOT_BLOCKED"
GOLDEN = [
  GoldenCase("G1",   "c_nordharbor", "2024-01-01", ALL, "EXPOSED", {"OFAC": B, "EU": B, "UK": B},
             {"syn:G1-1", "syn:G1-2", "syn:G1-3", "syn:D-p_volkov-prog_ofac"}, None, "alias_chain"),
  GoldenCase("G2",   "c_nordharbor", "2020-06-01", ALL, "EXPOSED", {"OFAC": B, "EU": B, "UK": B},
             {"syn:G2-1", "syn:D-p_sokolov-prog_ofac"}, None, "temporal"),
  GoldenCase("G3",   "c_birch", "2024-01-01", ALL, "EXPOSED", {"OFAC": B, "EU": B, "UK": N},
             {"syn:G3-1", "syn:G3-2", "syn:D-p_volkov-prog_ofac"}, None, "chain_50_50"),
  GoldenCase("G3uk", "c_birch", "2024-01-01", ("UK",), "CLEAR_WITHIN_BOUNDS", {"UK": N}, None, None, "regime"),
  GoldenCase("G4",   "c_cedar", "2024-01-01", ALL, "EXPOSED", {"OFAC": B, "EU": B, "UK": N}, None, None, "aggregation"),
  GoldenCase("G4uk", "c_cedar", "2024-01-01", ("UK",), "CLEAR_WITHIN_BOUNDS", {"UK": N}, None, None, "regime"),
  GoldenCase("G5",   "c_dune", "2024-01-01", ALL, "ESCALATE", {"OFAC": I, "EU": I, "UK": I}, None, {"syn:G5-1"}, "unknown_stake"),
  GoldenCase("G6",   "c_elm", "2024-01-01", ALL, "CLEAR_WITHIN_BOUNDS", {"OFAC": N, "EU": N, "UK": N}, None, None, "unknown_bounded"),
  GoldenCase("G7",   "c_fjord", "2024-01-01", ALL, "ESCALATE", {"OFAC": N, "EU": N, "UK": N}, None, None, "restructuring_49"),
  GoldenCase("G7pre", "c_fjord", "2023-03-01", ALL, "CLEAR_WITHIN_BOUNDS", {"OFAC": N, "EU": N, "UK": N}, None, None, "temporal"),
  GoldenCase("G8",   "c_gamma", "2024-01-01", ALL, "ESCALATE", {"OFAC": N, "EU": N, "UK": N}, None, None, "circular"),
  GoldenCase("G9",   "c_harbor_trading", "2024-01-01", ALL, "CLEAR_WITHIN_BOUNDS", {"OFAC": N, "EU": N, "UK": N}, None, None, "lookalike"),
  GoldenCase("G10",  "c_juniper", "2024-01-01", ALL, "ESCALATE", {"OFAC": N, "EU": N, "UK": N}, None, None, "pending_alias"),
  GoldenCase("G11",  "c_kestrel", "2024-01-01", ALL, "EXPOSED", {"OFAC": B, "EU": B, "UK": B}, None, None, "injection_name"),
  GoldenCase("G11v", "v_kestrel_star", "2024-01-01", ALL, "EXPOSED", {"OFAC": B, "EU": B, "UK": B}, None, None, "vessel"),
  GoldenCase("G12",  "c_larch", "2022-06-01", ALL, "EXPOSED", {"OFAC": B, "EU": B, "UK": B}, None, None, "delisting"),
  GoldenCase("G12post", "c_larch", "2024-01-01", ALL, "CLEAR_WITHIN_BOUNDS", {"OFAC": N, "EU": N, "UK": N}, None, None, "delisting"),
  GoldenCase("G13",  "c_maple", "2024-01-01", ALL, "ESCALATE", {"OFAC": N, "EU": P, "UK": P}, None, None, "control_only"),
  GoldenCase("G14",  "c_aegean", "2024-03-01", ALL, "CLEAR_WITHIN_BOUNDS", {"OFAC": N, "EU": N, "UK": N}, None, None, "pre_event"),
  GoldenCase("G15",  "c_quartz", "2024-01-01", ALL, "ESCALATE", {"OFAC": N, "EU": N, "UK": N}, None, None, "mass_address"),
  GoldenCase("G16",  "c_rostok", "2024-01-01", ALL, "EXPOSED", {"OFAC": B, "EU": B, "UK": B}, None, None, "direct"),
  GoldenCase("G17",  "c_nimbus", "2024-01-01", ALL, "EXPOSED", {"OFAC": B, "EU": B, "UK": B}, None, None, "duplicate_records"),
  GoldenCase("G17c", "c_otter", "2024-01-01", ALL, "ESCALATE", {"OFAC": I, "EU": I, "UK": I}, None,
             {"syn:G17-2a", "syn:G17-2b"}, "conflicting_sources"),
  GoldenCase("G18",  "c_meridian", "2024-01-01", ALL, "EXPOSED", {"OFAC": B, "EU": B, "UK": B}, None, None, "one_hop"),
]   # 24 checks. The watch flip (G14 after designation) and the alias acceptance (G10 → EXPOSED) are covered in Tasks 15/7.
