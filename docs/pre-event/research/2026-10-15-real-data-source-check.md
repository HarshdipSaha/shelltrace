# Task 21 real-data source check

Retrieved 2026-10-15 using public HTTPS without authentication. Read R4 and Task 21 before inspection. These are observed source facts and local acquisition results, not an evaluation result. `data/raw/` is ignored by Git. Root CONTEXT.md and docs/adr/ were absent.

## Inputs ready for local implementation

| Local file | Contents and provenance |
|---|---|
| `data/raw/os_sanctions.ftm.json` | Full authentic OpenSanctions sanctions FtM JSONL; 376,485,852 bytes. Includes people; never commit. |
| `data/raw/os_company_vessel_slice.ftm.jsonl` | Extracted 32,169 Company/Organization/LegalEntity/Vessel records plus Sanction records pointing to those records; no Person records or Ownership edges. Raw corporate descriptions may still mention people, so keep local. |
| `data/raw/os_company_designation_sample.ftm.jsonl` | 32 sanitized authentic records: corporate entities, their mapped-authority Sanction records, and three vessels. Properties explicitly allowlisted; no person records or natural-person identifiers copied. Intended authentic fixture source; attribute OpenSanctions and observe NC restriction. |
| `data/raw/gleif_rr.csv.zip` | Authentic GLEIF 2026-10-15 08:00 RR golden copy, 24,475,993 bytes. |
| `data/raw/rr.csv` | Full extracted RR CSV, 491,037 rows. |
| `data/raw/gleif_rr_sample.csv` | 26 authentic rows with original 54-column header. Selected candidate parent paths then first 20 ACTIVE direct rows, deduplicated by child. Not representative; sample is for parser testing. |
| `data/raw/gleif_rr_header.json` | Exact original header for mapping. |
| `data/raw/e3_source_candidates.json` | Nine authority/ancestor candidate records, before temporal eligibility. Company names and LEIs only. |
| `data/raw/source_manifest.json` | Acquisition metadata, pinned URLs, sizes and SHA256s. |
| `data/raw/os_sanctions_index.json`, `gem_index.json`, `gleif_publish.json` | Retrieved source metadata. |
| `data/raw/upstream_gem_crawler.py`, `upstream_gem_gem_energy_ownership.yml` | Public upstream conversion code, saved for inspection. |

## OpenSanctions snapshot and actual structure

Pinned [index](https://data.opensanctions.org/artifacts/sanctions/20261015074704-lqt/index.json) and [FtM bulk download](https://data.opensanctions.org/artifacts/sanctions/20261015074704-lqt/entities.ftm.json). Version `20261015074704-lqt`; index resource checksum `1517136812887432961689004042c8bccb1fe2c9` (upstream checksum, not assumed algorithm). The `latest` URL advanced during research: browsing first returned `20261015014705-pvx`, direct acquisition returned the later version above. Pin artifact URLs, not latest.

Each line is one JSON object. Top-level fields observed: `id`, `caption`, `schema`, `referents`, `datasets`, `origin`, `first_seen`, `last_seen`, `last_change`, `properties`, `target`. Property values are arrays. Referenced entity IDs on Sanction records are canonical entity IDs. Actual bulk schema counts: Company 2,993; Organization 21,600; LegalEntity 5,556; Vessel 2,020; Person 43,921; Sanction 173,600. Keep legal schemas intentionally: Organization also includes noncommercial/state bodies.

All proposed authority mappings occur in the pinned collection and actual Sanction records: `us_ofac_sdn` -> OFAC, `eu_fsf` -> EU, `gb_fcdo_sanctions` -> UK. Among Sanction records referencing kept non-person nodes: OFAC 11,588 records; EU 1,775; UK 2,350. These are records, not distinct targets. Only 31 of those OFAC records have listingDate or startDate; all EU/UK records do. `first_seen` is an ingestion observation, **not the legal listing date**. If used as the plan fallback, expose `listed_on_basis=first_seen` and distinguish approximate-history E3 from source-dated E3. Do not silently describe first_seen as an official listing date.

Corporate node `properties.leiCode` appeared 2,638 times. `properties.imoNumber` can contain an `IMO` prefix (e.g. `IMO9422964`), so normalize before cross-source matching. Sanctions' own datasets, rather than the target's combined datasets, determine authority. Sanction records may lack caption in sanitized fixtures; use schema and properties.

The publisher permits bulk downloads for personal noncommercial use under CC BY-NC 4.0; use within a for-profit business requires a data licence. Local availability does not establish commercial permission. Keep downloaded/derived bulk data ignored, provide attribution, and do not claim an unrestricted licence. [Publisher licence guidance](https://www.opensanctions.org/docs/commercial/exemption/).

## GLEIF exact mapping and semantics

Metadata endpoint: [latest publication](https://goldencopy.gleif.org/api/v2/golden-copies/publishes/latest). Actual pinned RR download: [2026-10-15 08:00 RR CSV ZIP](https://goldencopy.gleif.org/storage/golden-copy-files/2026/10/15/1288820/20261015-0800-gleif-goldencopy-rr-golden-copy.csv.zip). Format RR_2.1, 491,037 records. Archive member `20261015-0800-gleif-goldencopy-rr-golden-copy.csv`.

Header has **54 columns**. Exact important names (all relationship fields have the prefix):

- `Relationship.StartNode.NodeID`, `Relationship.StartNode.NodeIDType` (child).
- `Relationship.EndNode.NodeID`, `Relationship.EndNode.NodeIDType` (parent).
- `Relationship.RelationshipType`, `Relationship.RelationshipStatus`.
- `Relationship.Period.{1..5}.startDate`, `.endDate`, `.periodType`.
- `Relationship.Qualifiers.{1..5}.QualifierDimension`, `.QualifierCategory`.
- `Relationship.Quantifiers.{1..5}.MeasurementMethod`, `.QuantifierAmount`, `.QuantifierUnits`.
- `Registration.InitialRegistrationDate`, `.LastUpdateDate`, `.RegistrationStatus`, `.NextRenewalDate`, `.ManagingLOU`, `.ValidationSources`, `.ValidationDocuments`, `.ValidationReference`.

Select `IS_DIRECTLY_CONSOLIDATED_BY` AND `ACTIVE`: **127,226** rows observed, versus 127,249 direct rows before ACTIVE filtering. Parent -> child reverses the file's start/end orientation. Never replace this relation with a legal shareholding assertion. Preserve accounting-consolidation basis on controls and amounts; statutory ownership computation must not treat it as observed shareholding. Retain LAPSED registration rows when relationship itself is ACTIVE. Select interval slots by `periodType == RELATIONSHIP_PERIOD`; slot 1 is not guaranteed to be that interval. Dates observed as full ISO UTC timestamps; normalize date portions explicitly.

Crucial unit caveat: 25,212 populated quantifier slots on ACTIVE direct relationships all have `MeasurementMethod=ACCOUNTING_CONSOLIDATION`; **16,731** have `QuantifierUnits=PERCENTAGE`, **8,481** have blank units. An amount with missing units must not automatically become an ownership percentage. Scan all five slots and attach amount, unit and basis; use a percentage only when the source documents that unit. Otherwise retain a basis-labelled control relation with unknown percentage and a data-quality reason.

GLEIF data access licence is CC0; do not imply GLEIF endorsement. [GLEIF terms](https://www.gleif.org/en/meta/lei-data-terms-of-use). Legal entities may include sole traders in the broad GLEIF population: do not equate CC0 with absence of personal data. The fixture selection here contains corporate LEIs and relation metadata, not natural-person names.

## GEM: direct file unavailable and imputation issue

Retrieved [GEM OpenSanctions index](https://data.opensanctions.org/artifacts/gem_energy_ownership/20260921082002-ggb/index.json): version `20260921082002-ggb`, entity_count 48,324, target_count 0, thing_count 27,198, `resources: []`. The assumed [FtM endpoint](https://data.opensanctions.org/datasets/latest/gem_energy_ownership/entities.ftm.json) returned **HTTP 404**. No GEM FtM file or authentic GEM fixture was acquired; do not manufacture one and call it real.

Upstream [dataset configuration](https://github.com/opensanctions/opensanctions/blob/main/datasets/_global/gem_energy_ownership/gem_energy_ownership.yml) declares only statistics export and explains a manually stored internal workbook is used while direct downloads are unavailable. [Crawler source](https://github.com/opensanctions/opensanctions/blob/main/datasets/_global/gem_energy_ownership/crawler.py) calls internal-data for `gem_energy_ownership/Global-Energy-Ownership-Tracker-August-2026-V2.xlsx`; sheets `All Entities` and `Entity Ownership`. Ownership source fields include `subject_entity_id` (child), `interested_party_id` (owner), `share_of_ownership`, `data_source_url`, `share_imputed`. It emits `Ownership.owner`, `.asset`, `.percentage`, `.sourceUrl` and **ignores share_imputed**. Thus an FtM percentage extracted from this conversion does not prove it was observed.

The [GEM publisher page](https://globalenergymonitor.org/projects/global-energy-ownership-tracker) describes September 2026 as its latest release and explicitly describes marked imputed shares used for attribution. Preserve `share_imputed` from the workbook, and keep imputed numbers out of legal ownership decisions. An alternative raw GEM workbook acquisition/permission or source export with that flag is still required. OpenSanctions' index describes GEM data under CC BY 4.0; that does not remove OpenSanctions' NC conditions on a transformed combined export. Do not treat the old 2024 coverage date in its index as proof that the underlying current workbook is 2024; it conflicts with the crawler's 2026 filename and should be reported as stale metadata.

## E3 availability: bounded evidence, no performance claim

Research scanned the full ACTIVE direct GLEIF graph and all mapped non-person sanctions. Join was exact LEI only; breadth-first upstream traversal capped at six edges, deduplicated ancestors per child, no OpenSanctions Ownership edges used. Nine same-authority designated child/ancestor pairs were found: **OFAC 5, UK 3, EU 1**. These are candidate pairs, **not final eligible positive counts**: designation ordering, interval validity, identity resolution and parser semantics still need evaluation.

OFAC candidate pairs: GTLK Europe Capital -> GTLK Europe; National Clearing Centre -> Moscow Exchange; Golden Global Portfoy -> Golden Global investment bank; National Settlement Depository -> Moscow Exchange; Xing Ao Energy -> Hebei Xinhai Chemical. OFAC source dates are missing on these candidates, so the plan's first_seen fallback cannot support a strong historical legal claim. UK includes National Clearing Centre and National Settlement Depository -> Moscow Exchange (same listed date 2024-06-13); Bank Zenit -> Tatneft has parent listed later and is ineligible under source dates. The EU National Settlement Depository candidate also has parent listed later and is ineligible. Relation-period validity can reduce counts further.

This establishes nonzero *structural* OFAC availability, not the requested nonzero temporally valid E3 metric. Report `small n` without a percentage for any authority with n < 30; report zero honestly. Company fixture was chosen from these authentic candidate endpoints and their mapped Sanction records, with free text removed and three authentic vessels added. Negative Person rejection tests should use an explicitly synthetic marker record, not copied natural-person data.

Implementation can proceed with authentic sanctions and GLEIF now. A full GEM-backed ownership evaluation remains unresolved. No synthetic rows have been represented as real, and no evaluation accuracy result is claimed.
