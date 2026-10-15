# R4 - Open data sources and evaluation-set design for ShellTrace

Research date: 2026-10-05. Research was cut short on coordinator instruction. Every claim below either cites a URL that was fetched today, or comes from my own inspection of a public file downloaded today (marked **[inspected]**). Claims I could not check today are marked **UNVERIFIED** or **NOT CHECKED**.

---

## Key findings that change the spec

1. **The `sanction.control` article exists, but its date is off.** The URL https://www.opensanctions.org/articles/2026-08-13-sanction-control/ works. The page footer says "Published: 2026-07-31", even though the slug says 08-13. The spec should cite the URL and give 2026-07-31 as the publication date. The topic means: "companies, assets, and vessels owned by a sanctioned person or company, whether the ownership is direct or through one or more layers of subsidiary ownership". The article also says "We apply no percentage threshold" and "An end date on a shareholding stops the chain". So it is **not** an OFAC 50% computation. It is a plain ownership-reachability flag.
2. **`sanction.control` is computed by OpenSanctions itself, by walking its own graph.** That makes it a leaky label. The topic is produced by the derived dataset `ann_graph_topics` ("Derived risk topics, computed by walking the resolved entity graph... `sanction.control` - an entity owned by a sanctioned or `sanction.control` entity, down the full ownership chain, regardless of the size of the stake... Relationships carrying an end date are ignored") (https://data.opensanctions.org/datasets/latest/ann_graph_topics/index.json). If ShellTrace loads the same OpenSanctions `Ownership` edges and "predicts" `sanction.control`, it is just re-running OpenSanctions' breadth-first search. The result is circular and trivially near-100%. It cannot be the headline metric.
3. **About 93% of `sanction.control` positives come from the Russian company register, and only 338 have an LEI.** **[inspected]** On 2026-10-05, 28,561 entities carry `sanction.control`: 28,531 LegalEntity and 30 Vessel. By source-ID prefix, 26,643 come from `ru-inn` (Russian EGRUL tax IDs), 367 from `gem-own`, 338 from `lei`, 320 from `ua-ws`, 312 from `icijol`, 220 from `oc-companies`, 200 from `ge-coreg` and 178 from `gb-fcdo`. A GLEIF-centred graph would therefore cover only about 1.2% of the label set. EGRUL ownership data also carries large numbers of named Russian private individuals as shareholders, which is personal data.
4. **GLEIF Level 2 does carry percentages, but they are accounting-consolidation percentages, not shareholdings, and coverage is sparse.** **[inspected]** I checked the RR golden copy of 2026-10-05. Of 260,305 direct and ultimate consolidation relationships, 49,528 have a `QuantifierAmount`, and every quantifier uses `MeasurementMethod=ACCOUNTING_CONSOLIDATION`. The amounts break down as 100%: 40,045; 50-99.99%: 8,385; exactly 50%: 376; below 50%: 722. Our `OWNS{pct}` should be filled only when a value exists, and must be flagged `pct_basis="accounting_consolidation"`.
5. **GLEIF's golden copy is effectively a current snapshot, not a history.** **[inspected]** Only 23 of 489,867 `RELATIONSHIP_PERIOD` entries have an `endDate`. So `valid_to` cannot come from GLEIF. Temporal-expiry typologies must come from OpenSanctions `Ownership.endDate` or from synthetic data.
6. **The OpenSanctions licence is a real risk for this team.** The licence is CC BY-NC 4.0, and "Any use inside a for-profit business requires a data license" (https://www.opensanctions.org/docs/commercial/exemption/). Hackathons are not mentioned. The builder's work identity is at a for-profit firm, so: (a) build in a personal, non-commercial capacity, or (b) email OpenSanctions to ask. In either case, ship a loader script plus attribution rather than redistributing OpenSanctions-derived data in the repo. GLEIF is CC0 and safe.
7. **OpenSanctions already contains a GLEIF subset.** `ext_gleif` holds 3,629 LEI entities matched to OpenSanctions entities. A full FtM conversion is published at https://github.com/opensanctions/gleif (https://data.opensanctions.org/datasets/latest/ext_gleif/index.json). This means GLEIF edges can be inside OpenSanctions' own graph, which partly contaminates even a "GLEIF-only" evaluation (see section 6).

---

## 1. OpenSanctions

### 1.1 Collections and bulk files (as of 2026-10-05)

| Collection | Entities / targets | Files (size) | Cadence | Source |
|---|---|---|---|---|
| `default` (version `20261005125304-opz`) | 4,090,811 / 1,234,399; 484 child datasets | `entities.ftm.json` 2.62 GB; `statements.csv` 9.47 GB; `targets.nested.json` 3.92 GB; `targets.simple.csv` 465 MB; `senzing.json` 1.46 GB; `names.txt` 110 MB | cron `0 */6 * * *` | https://data.opensanctions.org/datasets/latest/default/index.json |
| `sanctions` | 302,038 / 72,805 | `entities.ftm.json` 367 MB; `targets.nested.json` 449 MB; `targets.simple.csv` 74 MB; `names.txt` 11 MB; `senzing.json` 75 MB | cron `0 1,7,13,19 * * *` | https://data.opensanctions.org/datasets/latest/sanctions/index.json |
| `maritime` | 319,322 / 96,787 | `maritime.csv` 5.1 MB (columns: type VESSEL/ORGANIZATION, caption, imo, risk, countries, flag, mmsi, ...) | daily | https://data.opensanctions.org/datasets/latest/maritime/index.json |
| `ann_graph_topics` | 90,584 annotation patches | `entities.ftm.json` 28.9 MB | every 6 h | https://data.opensanctions.org/datasets/latest/ann_graph_topics/index.json |

Artifact URLs are versioned, for example `https://data.opensanctions.org/artifacts/default/20261005125304-opz/entities.ftm.json`. Each index also exposes `delta_url`, `statistics_url` and `issues_url` (same index.json). This allows a **frozen snapshot**: pin the version string in the spec. I did NOT CHECK whether old versions stay downloadable long-term.

### 1.2 Ownership-relevant child datasets inside `default` (same index; per-dataset index.json)

| Dataset | Entities | Notes |
|---|---|---|
| `ext_ru_egrul` | 470,608 | Russian register; "augmented with historic ownership and directorship data, sourced from snapshots ... dating back to 2022-01-01". Weekly. |
| `gem_energy_ownership` | 48,324 | Global Energy Ownership Tracker; ownership links "reported with the percentage of ownership" above a 5% threshold; licensed by GEM under **CC BY 4.0**; frequency "never", data to 2024-06-30. |
| `ext_gleif` | 3,629 | matched LEI subset; weekly. |
| `ext_icij_offshoreleaks` | 1,782 | matched subset of ICIJ Offshore Leaks. |
| `ext_gb_coh_psc` | 1,081 | UK PSC subset (people with significant control are natural persons, so personal data). |
| `opencorporates` | 1,219 | links only: "OpenCorporates customers with bulk data or API access can also use the OpenCorporates URL". |

Other ownership or registry children seen in the list: `ext_ua_edr`, `ext_kz_companies`, `ext_lv_business_register`, `ext_cz_business_register`, `ext_ee_ariregister`, `ext_ge_company_registry`, `ext_cy_companies`, `ext_md_companies`, `ext_ba_companies`, `brightquery`, `permid`, `wikidata`, `ext_us_ofac_press_releases`. I did NOT CHECK their sizes or contents.

### 1.3 `ann_graph_topics` breakdown **[inspected]** (2026-10-05)

- Topic counts: `sanction.linked` 63,031; `sanction.control` 28,561; `role.rca` 25,887; `export.control.linked` 10,837.
- Combinations: `{sanction.control, sanction.linked}` 19,782; `{export.control.linked, sanction.control, sanction.linked}` 8,779. Every control entity is also tagged linked, which matches the article: "control is a subset of linkage".
- Schemas across all patches: LegalEntity 79,730; Security 9,878; Vessel 703; Airplane 273.
- Example patch: `{"id":"NK-22LPeJXieAfM3GCfmZyFq2","schema":"LegalEntity","referents":["ru-inn-2318024818"],"datasets":["ann_graph_topics"],"origin":["inferred"],"first_seen":"2026-05-15T18:40:22","properties":{"topics":["sanction.control","sanction.linked"]}}`.
- Each patch carries only `topics`. Names and edges must be joined from `default/entities.ftm.json`. The `first_seen` value on each patch is useful as a **label timestamp** for time-split evaluation.

### 1.4 Topic definitions (https://www.opensanctions.org/docs/topics/)

- `sanction`: "designated by a government in order to prohibit specific interactions".
- `sanction.linked`: "a direct relationship with a `sanction` or a `sanction.control` entity".
- `sanction.control`: "direct or indirect subsidiaries of sanctioned entities".
- `sanction.counter`: designations issued by non-democratic countries.
- Other topics: `role.pep`, `role.rca`, `poi`, `debarment`, `reg.action`, `reg.warn`.

Per the article, `sanction.linked` is now one-hop adjacency across "ownership, directorship, membership, employment, association, family and succession", plus security/issuer links.

### 1.5 FtM schemata

- `Ownership` (https://followthemoney.tech/explorer/schemata/Ownership/). It is an edge from `owner` to `asset`. Properties: `percentage` (string), `startDate`, `endDate`, `sharesCount`, `sharesValue`, `sharesCurrency`, `sharesType`, `legalBasis`, `ownershipType`, `role`, `status`, `recordId`, `sourceUrl`, `publisher`, `retrievedAt`. Note that `percentage` is a free string, so it needs parsing.
- `Vessel` (https://followthemoney.tech/explorer/schemata/Vessel/). Properties: `imoNumber`, `mmsi`, `callSign`, `flag`, `pastFlags`, `registrationPort`, tonnage fields. Inherited from Vehicle: `owner`, `operator`, `buildDate`, `registrationDate`.
- `Directorship`, `UnknownLink`, `Occupancy`, `Family`, `Associate`, `Company`/`Organization`/`LegalEntity`: NOT CHECKED today. From prior knowledge (UNVERIFIED), they are Interval-based edges such as `Directorship(director, organization, role)`, `UnknownLink(subject, object, role)` and `Family(person, relative, relationship)`.
- Suggested mapping: `Ownership`→`OWNS{pct,valid_from,valid_to}`; `Directorship`→`OFFICER_OF{role}`; `UnknownLink`→`CONTROLS` only if the role says control, otherwise `LINKED`.

### 1.6 Licence

- The site footer says the data is under "Creative Commons 4.0 Attribution NonCommercial". Allowed free uses are "student projects, hobby analysis, and personal research". "Any use inside a for-profit business requires a data license", and "Compliance screening is a commercial use even though it generates no revenue." Free API keys are available to journalists, NGOs and academics (https://www.opensanctions.org/docs/commercial/exemption/, https://www.opensanctions.org/faq/32/exemptions/).
- Hackathon use is UNVERIFIED. Recommendation: confirm by email, attribute OpenSanctions, and do not commit derived data. Commit the loader plus the pinned version string instead.

---

## 2. GLEIF (CC0)

- **Licence:** "The data available through the Access Service are provided under the CC0 licence". No attribution is required, but you must not imply GLEIF endorsement (https://www.gleif.org/en/meta/lei-data-terms-of-use).
- **Golden copy (publish 2026-10-05 08:00)**, from metadata at https://goldencopy.gleif.org/api/v2/golden-copies/publishes/latest:

| File | Records | CSV zip | JSON zip | XML zip | Format version |
|---|---|---|---|---|---|
| Level 1 (lei2) | 3,451,660 | 483.6 MB | 891.8 MB | 859.3 MB | LEI_3.1 |
| Level 2 RR | 489,942 | 23.3 MB | 33.5 MB | 31.7 MB | RR_2.1 |
| Reporting exceptions | 6,397,033 | 59.1 MB | 61.2 MB | 66.2 MB | REPEX_2.1 |

  - RR CSV URL: `https://goldencopy.gleif.org/storage/golden-copy-files/2026/10/05/1284770/20261005-0800-gleif-goldencopy-rr-golden-copy.csv.zip`.
  - Delta files are also published (IntraDay, LastDay, LastWeek, LastMonth; LastMonth RR-equivalent lei2 delta is 47 MB).
- **RR CSV schema [inspected].** There are 54 columns, including:
  - `Relationship.StartNode.NodeID` (the child) and `Relationship.EndNode.NodeID` (the parent), plus their `NodeIDType`
  - `RelationshipType`, `RelationshipStatus`
  - `Period.{1..5}.startDate/endDate/periodType`
  - `Qualifiers.{1..5}.QualifierDimension/Category`
  - `Quantifiers.{1..5}.MeasurementMethod/QuantifierAmount/QuantifierUnits`
  - `Registration.*`, including `RegistrationStatus` and `ValidationSources`
- **RR profile [inspected].**
  - Types: IS_FUND-MANAGED_BY 151,929; IS_ULTIMATELY_CONSOLIDATED_BY 133,261; IS_DIRECTLY_CONSOLIDATED_BY 127,044; IS_SUBFUND_OF 74,348; IS_INTERNATIONAL_BRANCH_OF 1,969; IS_FEEDER_TO 1,391.
  - Status: ACTIVE 489,497; INACTIVE 60; NULL 385.
  - Registration: PUBLISHED 387,640; LAPSED 102,293.
  - The direct-parent subgraph has 169,343 LEIs and 127,044 edges.
  - Qualifiers are ACCOUNTING_STANDARD only (IFRS 71,424; other 55,148; US_GAAP 15,497).
  - Example record: child `0292001381F1R1IB5B85` → parent `2549003PEZXUT7MDBU41`, IS_DIRECTLY_CONSOLIDATED_BY, RELATIONSHIP_PERIOD start 2006-01-25, IFRS, ACCOUNTING_CONSOLIDATION 99.99 PERCENTAGE, FULLY_CORROBORATED.
- **Semantics.** Accounting consolidation applies when "the assets, liabilities, equity, income, expenses and cash flows of the parent and its subsidiaries are presented as those of a single economic entity". This wording is from the IFRS 10 definition quoted in the GLEIF L2 ontology (https://www.gleif.org/ontology/pylodev2/GLEIF_L2.html); I saw it via a search snippet and did not fetch the page in full. Reporting-exception reasons include NATURAL_PERSONS, NON_CONSOLIDATING and NO_KNOWN_PERSON (same source). Others such as NON_PUBLIC are UNVERIFIED.
- **Small-subset API (verified working).** Use `https://api.gleif.org/api/v1/lei-records?filter[fulltext]=...` together with `/lei-records/{LEI}/direct-parent`, `/ultimate-parent`, `/direct-children` and `/ultimate-children`.
- **Many sanctioned-group LEIs are LAPSED.** Examples: Sovcomflot and most of its subsidiaries. Do not filter out LAPSED registrations.

---

## 3. ICIJ Offshore Leaks (NOT CHECKED today)

From prior knowledge, all UNVERIFIED:
- Download at https://offshoreleaks.icij.org/pages/database, licensed ODbL with contents under CC BY-SA.
- CSV files for nodes (entities, officers, intermediaries, addresses, others) and a relationships file. Edge types include `officer_of`, `intermediary_of`, `registered_address`, `similar`, `same_as`, `underlying`, with `start_date`/`end_date` columns.
- Officers are largely natural persons, so it carries a personal-data risk.

OpenSanctions links only 1,782 ICIJ entities, and ICIJ coverage ends in 2023 (`ext_icij_offshoreleaks` index). Verdict: optional, companies-only, and do not use it for the core demo.

## 4. Other sources (NOT CHECKED today; UNVERIFIED)

- **Open Ownership / BODS.** Status of the register in 2026 is unknown.
- **UK Companies House PSC snapshot.** Open, but every PSC is a natural person, so excluding people is mandatory.
- **OpenCorporates.** Bulk data is paywalled. OpenSanctions itself says OpenCorporates bulk/API is for "OpenCorporates customers". Do not use.
- **Wikidata P127/P749.** CC0, but the percentage qualifier (P1107) is sparse. Plausible for parent-org edges.
- **OFAC SDN.** Public domain, with "Linked To:" remarks. Its value is as an independent label source (section 6).
- **GEM ownership.** CC BY 4.0, has real percentages, and is already in OpenSanctions (section 1.2). This is the best legal source of percentage-bearing company-to-company edges found so far.

---

## 5. Recommended real-data slice

1. **Seeds.** Sanctioned non-person targets from `sanctions/entities.ftm.json` (367 MB): schemas Company, Organization, LegalEntity and Vessel, plus the `maritime.csv` vessels (5.1 MB). Seed count by schema is NOT CHECKED. The total across all schemas is 72,805 targets.
2. **Company-to-company edges.**
   - GLEIF RR IS_DIRECTLY_CONSOLIDATED_BY edges (23 MB zip; CC0), restricted to the connected components of LEIs that are attached to seeds.
   - OpenSanctions `Ownership` edges where **both ends are non-Person**. Keep `percentage`, `startDate` and `endDate`.
   - GEM ownership edges (CC BY 4.0).
3. **People.** Drop every `Person` node and any edge touching a Person. Replace them with synthetic officers or nominees so the person-centric typologies still work.
4. **Size estimate (UNVERIFIED, back-of-envelope).** Roughly 5k-30k company/vessel nodes and 10k-60k edges. That is within FalkorDB comfort. Measure it with a filter script over the pinned snapshot before committing to the number.
5. **Provenance.** Store `source`, `source_version`, `licence` and `retrieved_at` on every node and edge.

### Real example chains (verified today via the GLEIF API; designation status of the parent is UNVERIFIED today)

1. **Sovcomflot.** PAO Sovcomflot (LEI `253400DYLWR5A6YAWJ69`, LAPSED) has 1 direct child and 11 ultimate children. The direct child is SERAFINA ENTERPRISES INCORPORATED (LR, `549300T8W114GXW7VJ40`). The ultimate children include MAJORIA SHIPPING COMPANY LIMITED (CY), HEADLINER MARITIME S.A. (LR), ALBUS SHIPPING LIMITED, PURPOSEFUL CORPORATION, DAFNE LINE SHIPPING COMPANY LIMITED (CY), GLOBAL CHALLENGE SHIPPING COMPANY LIMITED (CY), and PABBAY / ENSAY / BORERAY / SCALPAY SHIPPING LIMITED (LR). Ten of the ultimate children are not direct children, so multi-hop chains exist. The intermediate hops are NOT CHECKED. The names give no hint of Sovcomflot, which makes this a good "missed by name screening" demo. Sovcomflot's designations by OFAC, UK and EU are UNVERIFIED today.
2. **Sberbank.** PJSC Sberbank (`549300WE6TAF5EEWQS81`) has 4 direct and 9 ultimate children. Children that are ultimate but not direct, i.e. multi-hop: Sber Trading Swiss AG (CH, `506700AUNEQF0C694855`), SBGB CYPRUS LIMITED (`549300L1G21ZCED8UN98`), V-Dat Informatikai Kft. (HU, `529900YLHSF7E5PF9A73`), SBERBANK CIB (UK) LIMITED (`549300BKWHXYEXPV0328`) and SIB (CYPRUS) LIMITED (`F68F5WN6OGTEHIP5ZT82`).
3. **Rosneft.** PJSC NK Rosneft (`253400JT3MQWNDKMJE44`) has two direct children: Rosneft Deutschland GmbH (DE, `391200PKEUF3Y2NUMW25`) and LLC RN-Capital (`25340076BE9D5XUK4H54`). This is a one-hop chain.
4. **Giner network (OpenSanctions article, ends at a person).** Yakhonty Kursk (registered November 2023, not listed) has as a major shareholder a hotel management company outside Moscow, which is 50% owned by Eugeny Giner (Ukraine NSDC, October 2022). Separately, Agroinnovatsiya is 50% owned by Giner and owns a trading house and companies in Astrakhan and the Moscow region (https://www.opensanctions.org/articles/2026-08-13-sanction-control/). Replace Giner with a synthetic sanctioned person, or keep the public-figure node with an explicit justification.

---

## 6. Evaluation design (avoiding leakage)

**The leakage problem.** `sanction.control` is defined as the downward ownership closure from `sanction` seeds over un-ended OpenSanctions edges (`ann_graph_topics`). Predicting it from the same edges is an identity function. Even a "GLEIF-only" graph is partly contaminated, because `ext_gleif` sits inside OpenSanctions' resolved graph.

Proposed tiers:

- **E0 - Reproduction check (correctness, not accuracy).** Load OpenSanctions edges, run our control traversal, then diff against `ann_graph_topics`. The target is about 100% agreement. The diffs reveal entity-resolution or end-date handling bugs. Report it as a sanity check only.
- **E1 - Cross-source test (main metric).**
  - Graph: GLEIF RR plus GEM plus synthetic edges only.
  - Seeds: `sanction` entities.
  - Labels: `sanction.control` entities whose OpenSanctions control path does not use GLEIF statements. Filter by the `dataset` column in `statements.csv` (9.5 GB, stream it).
  - Report recall, precision, and the share of labels that are reachable at all.
- **E2 - Time split (most convincing).**
  - Freeze the graph at T0. Use pinned artifact versions; old-version availability is UNVERIFIED.
  - Positives: entities that gain a **direct** `sanction` designation between T0 and T1 (for example, subsidiaries named in OFAC press releases via `ext_us_ofac_press_releases`, or entities whose `first_seen` in `ann_graph_topics` falls after T0), where at T0 they were already reachable by ownership from a sanctioned entity.
  - Metric: precision@k on a ranking of not-yet-listed entities by control score.
- **E3 - Ablation.** For listed subsidiaries whose listed parent is in the graph, remove the subsidiary's `sanction` topic and test whether traversal recovers it.
- **Negatives.**
  - Companies with no ownership path to any seed at T0 that remain unlisted at T1, sampled from the same jurisdiction mix.
  - Hard negatives:
    - (a) paths that exist only through edges with `endDate < T0` (temporal expiry)
    - (b) `sanction.linked`-only entities, linked through directorship or association but not ownership
    - (c) aggregated known stakes below 50% (relevant to the OFAC 50% framing)
    - (d) GLEIF IS_FUND-MANAGED_BY links, which do not constitute ownership
- **Name-screening baseline.**
  - Exact match plus fuzzy match (for example, normalised token-set ratio ≥ 0.9, or the OpenSanctions matcher via self-hosted `yente`) against `sanctions/names.txt` (11 MB).
  - "Missed by name screening" = positives with no name hit above threshold that the graph finds.
  - Subsidiaries carrying the parent's brand (for example "Sberbank CIB (UK)") will be caught by the baseline. Single-ship companies (Pabbay, Serafina) and Yakhonty Kursk will not. Report the two strata separately.

## 7. Synthetic generator (NOT CHECKED today: IBM AMLworld, AMLSim)

The design is from first principles. Generate 10k-50k nodes using:
- a scale-free corporate forest (preferential attachment by country and sector)
- planted typologies with ground-truth labels:
  - nominee layering: 3-7 hops through BVI, CY and AE shells with synthetic nominee directors
  - circular ownership loops
  - "49% restructuring", where a sanctioned parent drops below 50% via two 49%/2% holders that share a director
  - alias and transliteration variants: Cyrillic to Latin, plus suffixes LLC/OOO/Ltd
  - temporal expiry: `valid_to` set before the query date
  - vessel flag-hopping with IMO kept stable

Use a seeded RNG, emit FalkorDB-ready CSV, and store `typology_id` on every planted edge so detections can be scored exactly.
