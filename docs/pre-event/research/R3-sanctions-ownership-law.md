# R3: Sanctions ownership and control law, written as graph algorithms

Research date: 2026-10-05. Scope: OFAC (US), EU, UK OFSI, related US export-control rules, red flags, enforcement narratives, and analyst and regulator expectations.
Status legend: **VERIFIED** means the primary source was fetched and read. **SECONDARY** means it was confirmed through a reputable law-firm or press summary only. **UNVERIFIED / NOT CHECKED** means it comes from background knowledge and was not fetched in this session (research was stopped early by the coordinator). Re-check those items before quoting them in the demo.

This is investigative evidence tooling, not legal advice. Every output must say so.

---

## Key findings that change the spec

1. **"Connected" is not "owned".** Under all three regimes an unlisted entity is caught only by ownership, or by control in the EU and UK. A shortest path through an officer, an address or a SAME_AS edge is never by itself a legal basis for "EXPOSED". ShellTrace needs three separate verdicts per jurisdiction: `BLOCKED_BY_OWNERSHIP`, `PRESUMED_CONTROLLED` (EU/UK only), and `PROXIMITY_ONLY` (escalation context). A fourth verdict, `NO_FINDING`, replaces the word "CLEAR". VERIFIED (sources in sections 1-3).
2. **OFAC does not multiply down the chain.** An entity that is 50% or more owned by blocked persons is itself blocked, and its *full* stake in the next entity counts. OFAC FAQ 401 Example 1: X owns 50% of A, A owns 50% of B, so B is blocked. A multiplicative model would give 25% and miss it. The correct computation is a **fixpoint over the blocked set**, not path products. Integrated (multiplicative) ownership is still useful, but only as a separate economic-exposure metric. VERIFIED.
3. **The thresholds differ.** OFAC uses ≥50%. The EU now also uses ≥50%: the Council Best Practices of July 2024, and then binding definitions written into Article 1 of Reg. 269/2014 by Reg. 2025/2037 on 23 Oct 2025. The UK uses **>50%** of shares or voting rights. So an entity at exactly 50% is blocked in the US and EU but not caught by UK ownership. VERIFIED.
4. **Aggregation differs.** OFAC aggregates across different blocked persons, even across different programs. So does the EU (Best Practices para 63; Commission FAQ 8). The UK does **not** aggregate holdings of different designated persons unless there is a joint arrangement, or one party controls the other's rights (OFSI General Guidance 4.1, updated 12 May 2026; OFAC-OFSI joint comparison, 23 Jun 2026). Through its Feb 2026 call for evidence, HMG says it is "actively explor[ing]" an aggregation model and a "50% or more" threshold. That is not adopted yet. VERIFIED.
5. **Control counts in the EU and UK, but not under OFAC's 50% rule.** OFAC FAQ 398 says "speaks only to ownership and not to control". However, OFAC's **31 Mar 2026 "Guidance on Sham Transactions and Sanctions Evasion"** says sham transfers "do not terminate a blocked interest in property". It lists red flags such as transfers to family, transfers near designation, complex structures and continued involvement. So below-50% "divestments" need a red-flag layer even for US analysis. VERIFIED.
6. **EU control is now a rebuttable legal presumption.** The CJEU's EM System judgment (C-84/24, 12 Mar 2026) held that a 50% stake held by a listed person creates a rebuttable presumption of control. The Commission's asset-freeze FAQ (as of 25 Sep 2026) frames owned-or-controlled status as a presumption that the entity can rebut. The tool should therefore present EU/UK control findings as "presumption triggered, with the rebuttal evidence needed", not as certainty. VERIFIED (FAQ) / SECONDARY (judgment).
7. **Temporal logic is legally meaningful.** Divesting below 50% unblocks the entity for future dealings only. Property already blocked stays blocked (OFAC FAQ 402). Transfers near the designation date are an explicit red flag in OFAC's 2026 guidance and in EU Best Practices para 67(c). ShellTrace already stores validity intervals. It should evaluate status "as of D" and also "as of designation date", and flag differences between the two. VERIFIED.
8. **US export controls are coming into scope.** The BIS "Affiliates Rule" (IFR, 90 FR 47201, 30 Sep 2025) applies the Entity List to affiliates that are ≥50% owned, directly or indirectly, individually or in the aggregate. It is stayed until **9 Nov 2026** and is scheduled to return on **10 Nov 2026**. The same fixpoint engine can compute it with a different seed list. VERIFIED (FR 2025-19846). Whether the stay has been extended is NOT CHECKED.

---

## 1. OFAC (United States): the 50 Percent Rule

### 1.1 Text (VERIFIED)
From the Revised Guidance of 13 Aug 2014, Federal Register 79 FR 47726 (https://www.govinfo.gov/content/pkg/FR-2014-08-14/pdf/2014-19252.pdf):

> "any entity owned in the aggregate, directly or indirectly, 50 percent or more by one or more blocked persons is itself considered to be a blocked person. The property and interests in property of such an entity are blocked regardless of whether the entity itself is listed..."

On caution:
> "U.S. persons are advised to act with caution when considering a transaction with a non-blocked entity in which one or more blocked persons has a significant ownership interest that is less than 50 percent or which one or more blocked persons may control by means other than a majority ownership interest. Such entities may be the subject of future designation or enforcement action by OFAC."

### 1.2 FAQs (VERIFIED, https://ofac.treasury.gov/faqs/topic/1521)
- **FAQ 398**: control alone does not trigger blocking. "OFAC's 50 Percent Rule speaks only to ownership and not to control." OFAC may still designate such entities separately. https://ofac.treasury.gov/faqs/398
- **FAQ 399**: aggregation. X at 25% plus Y at 25% means A is blocked. Ownership "of persons blocked under different OFAC sanctions programs are aggregated."
- **FAQ 400**: a US person may not sign contracts with a blocked individual even when that individual is acting for a non-blocked entity. This matters for OFFICER_OF edges: a blocked *officer* does not block the company, but a transaction that person signs is prohibited.
- **FAQ 401**: indirect ownership. "Indirectly" means ownership through entities that are themselves 50% or more owned by blocked persons. Worked examples (https://ofac.treasury.gov/faqs/401):

| # | Facts | Result | Why (fixpoint view) |
|---|---|---|---|
| 1 | X→A 50%; A→B 50% | **B blocked** | A is blocked (50% ≥ 50), so A's full 50% counts toward B |
| 2 | X→A 50%, X→B 50%; A→C 25%, B→C 25% | **C blocked** | A and B are blocked, so 25 + 25 = 50 |
| 3 | X→A 50%, X→B 10%; A→B 40% | **B blocked** | 10 (X) + 40 (A blocked) = 50 |
| 4 | X→A 50%, X→B 25%; A→C 25%, B→C 25% | **C not blocked** | B is not blocked (25%), so only A's 25 counts |
| 5 | X→A 25%, X→B 25%; A→C 50%, B→C 50% | **C not blocked** | Neither A nor B is blocked, so nothing counts |

Example 1 shows the rule is not multiplicative: 0.5 × 0.5 = 25% would wrongly clear B. Example 5 shows the rule is not "any path". Under a multiplicative model X's look-through stake in C would be 12.5 + 12.5 = 25%, and under a path model C is "connected". Neither gives the right answer.

- **FAQ 402**: divestment. Once the blocked stake falls below 50%, the entity is not blocked for future dealings. Property blocked while the stake was 50% or more stays blocked unless OFAC authorizes otherwise. Divestment must happen with no US-person involvement, and due diligence should confirm it actually happened. A sanctions-specialist commentary notes the FAQ has not yet been updated for the 2026 sham guidance (SECONDARY: https://sanctions.org/turbofac/research/OFAC-FAQ-402).

### 1.3 Sham Transactions guidance, 31 Mar 2026 (VERIFIED, https://ofac.treasury.gov/media/935441/download?inline)
Core statement: OFAC "implements functional definitions of 'interest' and 'property interest' that look beyond legal formalities to underlying practical and economic realities, [so] sham transactions do not terminate a blocked interest in property." Footnote 3 says the advisory "supplements the 50 Percent Rule". The red flags it lists are not exhaustive, and none is determinative on its own:
1. Commercially unreasonable transactions (inadequate consideration, not at arm's length).
2. Transfer to family members or close associates, including nominal owners who are not independent.
3. Unclear purpose of the transfer, or a transferee with no relevant expertise.
4. Unduly complex structures involving higher-risk jurisdictions (multi-layer LLCs, partnerships, trusts).
5. Continued involvement of the blocked person in use, management or disposition.
6. Transfer near the time of designation, immediately before or after. It cross-references FinCEN Alert FIN-2023-Alert002 (transfers "to a family member, business associate, or associated trust in close temporal proximity to... an OFAC designation").
7. Evasive responses about the blocked person's involvement.

Case vignettes in the guidance: Kerimov / Heritage Trust (blocking notice June 2022); Potanin / Sentimare, transferred to four Liechtenstein foundations for his minor children, with those foundations designated in June 2024 as controlled by Potanin.

### 1.4 BIS Affiliates Rule (VERIFIED, https://public-inspection.federalregister.gov/2025-19846.pdf)
"any entity that is at least 50 percent owned directly or indirectly, individually or in the aggregate, by one or more entities on the Entity List ... is itself automatically subject to Entity List restrictions." Stayed from 10 Nov 2025 to 9 Nov 2026, and reimposed from 10 Nov 2026 under the same rule. Whether the stay was extended after Oct 2026 is NOT CHECKED.

---

## 2. European Union

### 2.1 Council Best Practices, doc 11623/24 of 3 July 2024 (VERIFIED, https://data.consilium.europa.eu/doc/document/ST-11623-2024-INIT/en/pdf)
- **Para 63, ownership**: "the possession of 50% or more of the proprietary rights of an entity or having majority interest in it." **Aggregation:** "if one designated person owns 30% of the entity and another designated persons owns 25% of the entity, the entity should, in principle, be considered as owned by designated persons."
- **Para 64, control criteria** ("alone or pursuant to an agreement with another shareholder or other third party", inter alia):
  - (a) the right or power to appoint or remove a majority of the board;
  - (b) having appointed a majority of the board solely through one's voting rights, in the current or previous financial year;
  - (c) controlling a majority of voting rights under an agreement with other shareholders;
  - (d) a right to exercise dominant influence under an agreement or the articles;
  - (e) de facto power to exercise dominant influence, "including, for example, by means of a front company";
  - (f) a right to use all or part of the assets;
  - (g) managing on a unified basis while publishing consolidated accounts;
  - (h) sharing jointly and severally, or guaranteeing, the entity's financial liabilities.
- **Paras 65-66**: if any criterion is met, the entity is considered controlled "unless the contrary can be established on a case by case basis". Ownership and control findings can be rebutted.
- **Para 67, indications of control**:
  - (a) the designated person is the largest shareholder, e.g. 40% against several holders at 10%, which "may warrant further analysis";
  - (b) a buyback option held by the designated former owner;
  - (c) **a transfer of shares close to designation**, including "smaller numbers which enable the listed seller ... to fall below the ownership threshold";
  - (d) front persons, such as family members or former employees, a too-low price, an advisor holding ultimate decision power, or written agreements giving a minor holder sole authority;
  - (e) needlessly complex structures, such as shell companies, LLCs or trusts set up or changed around the time of designation, or trusts used to receive assets.
- **Para 68**: making funds available to an owned or controlled entity is presumed to be making them available indirectly to the listed person, rebuttable on a risk-based assessment.

### 2.2 Binding definitions and Commission FAQ (VERIFIED, FAQ as of 25 Sep 2026, https://finance.ec.europa.eu/document/download/c7265161-3d9c-42e2-a928-e5b38c02bb92_en?filename=faqs-sanctions-russia-assets-freezes_en.pdf)
- Reg. (EU) 2025/2037 of 23 Oct 2025 (19th package) put the definitions of "owning" (≥50% / majority interest) and "controlling" (the non-exhaustive Best Practices criteria) into Article 1 of Reg. 269/2014. It also removed the "associated" wording in Article 2. Sources: FAQ Q1-Q2, Q43; Skadden summary https://www.skadden.com/insights/publications/2025/11/eu-adopts-19th-sanctions-package; regulation https://eur-lex.europa.eu/eli/reg/2025/2037/oj. The verbatim Article 1 text was NOT fetched because EUR-Lex was blocked.
- FAQ 1: control by a listed person over an unlisted entity creates a **presumption** that it extends to the entity's assets. The presumption is rebuttable.
- FAQ 5: assets transferred to a family member before listing must still be frozen if there are "reasonable grounds" to believe they belong to or are controlled by the listed person. The factors include closeness of ties, the third person's professional independence, previous gifts and formal agreements.
- **FAQ 8 (5 Sep 2024): aggregation applies.** The 30% + 25% example.
- **FAQ 9: groups.** If a listed person controls a group as a whole, the finding extends to all subsidiaries. If the listed person controls only one entity, the finding extends to that entity's own subsidiaries but "not other subsidiaries in the wider group". This is a direct graph rule: propagate downward only.
- FAQ 15 (May 2026): voting rights of listed shareholders are fully frozen (CJEU C-465/24 SBK Art, 12 Mar 2026).
- FAQ 44-46: an NCA-authorized "firewall" can rebut control.
- **CJEU C-84/24 EM System (12 Mar 2026)**: a listed Belarusian held exactly 50%, which created a rebuttable presumption of control. Rebuttal looks at governance, the articles and how the entity works in practice (SECONDARY: https://www.hlc.com/en/publications/em-system-cjeu-elaborates-on-presumption-of-control-of-non-designated-entities-for-asset-freezing-purposes).
- **Indirect chains (EU).** The EU texts read in this session do not give an explicit chain-arithmetic rule like OFAC FAQ 401. The Group FAQ 9 and the control criteria support "controlled entity, then its subsidiaries" propagation. Treat the EU's indirect-ownership arithmetic as **UNVERIFIED**. ShellTrace should apply the OFAC-style fixpoint at ≥50% plus control propagation, and label this an interpretation.

### 2.3 Other packages
- **Article 8a of Reg. 833/2014 (14th package, June 2024)**: "best efforts" to ensure that non-EU entities an EU operator owns or controls do not undermine the sanctions. The Commission FAQs of 22 Nov 2024 cover it (SECONDARY: https://www.mayerbrown.com/en/insights/publications/2024/11/eu-commission-adopts-guidance-clarifying-best-efforts-obligations-under-eu-sanctions-targeting-belarus-and-russia). For graph purposes this means walking *downward* from an EU client to its owned or controlled non-EU subsidiaries.
- **20th package (23 Apr 2026; Reg. 2026/506 and 2026/511)**: an LNG terminal services ban for EU entities that are "50% or more owned, or controlled by" Russian nationals or entities; first use of the Art. 12f anti-circumvention tool (Kyrgyzstan); a ban on mirror and successor entities of listed crypto and payment providers (SECONDARY: https://www.skadden.com/insights/publications/2026/05/eu-20th-sanctions-package). The "successor entity" rule maps onto SAME_AS / re-incorporation detection.

---

## 3. United Kingdom (OFSI / FCDO)

### 3.1 Statutory test (VERIFIED as quoted in the HMG call for evidence, Feb 2026, https://assets.publishing.service.gov.uk/media/6992f255ceeaa48d377f6ba7/Call_for_Evidence.pdf)
Regulation 7 of the Russia (Sanctions) (EU Exit) Regulations 2019 says C is owned or controlled by P if either:
- **Condition 1**: P holds, directly or indirectly, **more than 50%** of the shares, **or more than 50%** of the voting rights, **or** the right to appoint or remove a majority of the board.
- **Condition 2**: "it is reasonable, having regard to all the circumstances, to expect that P would (if P chose to) be able, in most cases or in significant respects, by whatever means and whether directly or indirectly, to achieve the result that affairs of C are conducted in accordance with P's wishes."

### 3.2 Schedule 1 interpretation rules (SECONDARY, from the search snippet of https://www.legislation.gov.uk/uksi/2021/488/schedule/1; legislation.gov.uk could not be fetched)
- **Indirect holding through a chain of majority stakes.** A share is held indirectly if P has a majority stake in an entity that holds it, or in a chain where each link has a majority stake in the next. The whole share is attributed, not a multiplied fraction. "Majority stake" means a majority of voting rights, or being a member with the right to appoint or remove a majority of the board, or being a member who controls a majority of votes by agreement (UNVERIFIED in detail).
- **Joint arrangement.** Holders who agree to exercise their rights jointly in a predetermined way are each treated as holding the combined shares.
- **Nominees.** A share held as nominee is treated as held by the principal.
- Rights are treated as held by whoever controls their exercise (UNVERIFIED).

### 3.3 OFSI positions (VERIFIED)
- **General Guidance 4.1 (updated 12 May 2026)**, https://www.gov.uk/government/publications/financial-sanctions-general-guidance/uk-financial-sanctions-general-guidance: "OFSI would not simply aggregate different designated persons' holdings in a company, unless, for example, the shares or rights are subject to a joint arrangement between the designated parties." Jointly held funds count as owned by each holder.
- **OFAC-OFSI comparative overview (23 Jun 2026)**, https://assets.publishing.service.gov.uk/media/6a3a4c4f00ff27f06e3efc8b/OFAC-OFSI_Comparison_Guide.pdf. On UK thresholds: "more than 50 percent ... applies both to shares and voting rights". On aggregation: "OFSI's 50 percent requirement does not apply when different designated persons' shareholdings in an entity amount to 50 percent or more ... unless there is evidence to suggest the ownership structure is intended to obfuscate control".
- **Call for evidence, 16 Feb to 20 Apr 2026**, https://www.gov.uk/government/calls-for-evidence/ownership-and-control-test-in-uk-financial-sanctions-regulations. It focuses on "hypothetical control". On ownership, HMG is "actively explor[ing] ... adopting an aggregation model and amending the 50% ownership rule to '50% or more'". No government response had been published when checked. It cites the typology from *Hellard v OJSC Rossiysky Kredit Bank* (June 2024): de jure control; actual present de facto control ("calling the shots", from *Mints*); potential future de facto control; potential future de jure control.
- **Public officials (FCDO/OFSI, Nov 2023, after *Mints v PJSC National Bank Trust* [2023] EWCA Civ 1132).** Designated officials are not generally treated as controlling the public bodies they lead (SECONDARY: https://sanctionsnews.bakermckenzie.com/ofsi-and-fcdo-issue-joint-guidance-relating-to-ownership-and-control-by-public-officials/). Consequence for ShellTrace: an OFFICER_OF edge from a designated *official* is not control.
- The UK is **strict liability** for civil penalties (call for evidence para 1.15). That makes documented due diligence the main mitigating factor.

---

## 4. Per-jurisdiction rule table

| Rule | OFAC (US) | EU | UK |
|---|---|---|---|
| Ownership threshold | ≥50% | ≥50% (since 2024 BP / 2025 Art. 1) | >50% shares **or** >50% votes |
| Aggregate across different listed persons | Yes, across programs too | Yes | **No**, unless a joint arrangement or control of the other's rights |
| Indirect chain | Full stake of any ≥50%-blocked intermediary counts | Interpreted the same way plus group propagation (UNVERIFIED arithmetic) | Full attribution via a chain of majority (>50%) stakes |
| Control limb | **No** (ownership only), but sham/proxy analysis applies (2026) | Yes, 8 criteria, rebuttable presumption | Yes: board-appointment right **plus** the "reasonable to expect" test, including hypothetical control |
| Divestment | Prospective only; blocked property stays blocked (FAQ 402) | Transfers near listing trigger investigation (BP 67(c)); FAQ 5 | Not checked |

---

## 5. Algorithm specification

### 5.1 Graph preconditions
- `OWNS{pct, valid_from, valid_to, kind: legal|beneficial|nominee|trust_beneficiary, voting_pct?, source, confidence}`
- `CONTROLS{basis: board_appointment|voting_agreement|dominant_influence|asset_use|unified_mgmt|liability_guarantee|de_facto, ...}`
- `SANCTIONED{regime: OFAC|EU|UK|BIS, listed_from, delisted_on}`. A sanctioned-ness property has to be per regime, because seeds differ by list.
- Snapshot at date D: keep only edges where `valid_from <= D < coalesce(valid_to, +inf)`. Nominee edges are rewritten so the stake sits with the principal (the UK Schedule rule, and EU/OFAC substance over form).

### 5.2 (a) OFAC fixpoint, also used for BIS, EU ownership (threshold ≥50) and UK ownership (threshold >50, aggregate=false)
```
function blocked_fixpoint(G_D, seeds, thr=50.0, op=">=", aggregate=True):
    B = set(seeds)                     # listed persons at D
    reason = {s: ("LISTED", []) for s in seeds}
    changed = True
    while changed:                     # monotone: B only grows, so it terminates
        changed = False
        for e in entities(G_D) - B:
            in_edges = [(o, pct) for (o -> e, pct) in OWNS(G_D) if o in B]
            if aggregate:
                total = sum(pct for _, pct in in_edges)
            else:   # UK: per-person, and joint-arrangement groups count as one
                total = max(group_sum(in_edges, joint_groups))
            if compare(total, op, thr):
                B.add(e); reason[e] = ("OWNED", in_edges)   # evidence edges
                changed = True
    return B, reason
```
- Complexity: naive O(|V|·|E|) worst case. A worklist version (re-check only the out-neighbours of newly blocked nodes) runs in **O(|V|+|E|)**, because each OWNS edge is added to a running sum at most once.
- **Cycles** are safe. The set only grows, so cross-holdings converge to the least fixpoint, and nothing becomes blocked through self-ownership unless seeded.
- **Example check.** Ex.1: B ← A(50) gives B. Ex.4: C receives only A's 25, so not blocked. Ex.5: A and B are never blocked, so C is not blocked. This matches the FAQs.
- **Evidence.** `reason[e]` keeps the exact edges whose sum crossed the threshold. That is the explainable proof chain. Walk it back to the seeds to show the analyst a tree, not a single shortest path.

### 5.3 (b) EU/UK control overlay
```
C = B_ownership (from 5.2 with regime params)
repeat until no change:
  for e not in C:
     if any CONTROLS(c -> e) with c in C and basis in hard_criteria:   # EU 64(a)-(h); UK board right
         C.add(e, "PRESUMED_CONTROLLED", rebuttable=True)
     if any OFFICER_OF(c -> e, role in {director, board}) for c in C
        and count(board seats held by C-members) > half(board):         # EU 64(a)/(b)
         C.add(e, "PRESUMED_CONTROLLED")
# groups: propagate only downward from the controlled node (EU FAQ 9)
```
- The UK's "reasonable to expect" (hypothetical) control cannot be computed. ShellTrace should **surface indicators**, such as the largest shareholder at ≥ 2× the next holder, buyback options, family-member owners, or an advisor with veto. These lead to `ESCALATE`, never to an automatic block.

### 5.4 (c) Integrated, or effective, ownership: an economic look-through metric, not a legal test
Integrated ownership with cross-holdings works like a Leontief inverse. With W[i][j] the fraction of j held by i:
`Ω = W + W² + … = W (I − W)⁻¹`. This converges when every entity has outside holders, i.e. column sums < 1. Compute it with Jacobi iteration or a sparse solve restricted to the target's ancestor subgraph. The idea follows the "integrated ownership" literature (Glattfelder / Vitali et al. 2011, network of global corporate control; NOT CHECKED this session).

Cypher, acyclic, bounded depth, for display only:
```cypher
MATCH p = (s:Entity {sanctioned:true})-[:OWNS*1..6]->(t:Entity {id:$target})
WHERE all(r IN relationships(p) WHERE r.valid_from <= $D AND (r.valid_to IS NULL OR r.valid_to > $D))
WITH p, reduce(x = 1.0, r IN relationships(p) | x * r.pct/100.0) AS path_share
RETURN [n IN nodes(p) | n.name] AS chain, path_share ORDER BY path_share DESC
```
Summing `path_share` over paths double-counts nothing in DAGs but breaks on cycles. Use Python for cycles. **Never use this number to decide OFAC/EU/UK status.** Example 1 shows why: 25% integrated, but legally blocked.

### 5.5 (d) Proximity signals, for escalation only
Shared officers, shared REGISTERED_AT addresses, and SAME_AS fuzzy matches go into a separate score with their own label: "proximity, not ownership". These are the current shortest-path outputs.

### 5.6 Edge cases
- **Missing pct.** Treat it as unknown. Compute both bounds: the lower bound uses 0 and the upper bound uses the residual (100 − known stakes). If the upper bound crosses the threshold and the lower bound does not, the verdict is `INDETERMINATE: data gap`.
- **pct sum above 100.** This is a data error. Flag it, normalize only for the integrated metric, and keep the raw values for legal tests together with a data-quality warning.
- **Expired edges.** Excluded at D, but kept for the temporal red-flag pass.
- **Trusts and foundations.** Model them as Entity nodes with `TRUST_BENEFICIARY` / `SETTLOR` / `PROTECTOR` edges. Do not auto-attribute pct. Raise a red flag instead, since both the OFAC 2026 guidance and EU BP 67(e) single out trusts.
- **Nominees.** Rewrite the stake to the principal when the nominee relationship is known. Otherwise flag nominee-pattern officers (see 6).
- **Votes vs equity.** The UK tests >50% of shares *or* votes separately. Carry `voting_pct` when it is known.
- **Delisted seeds.** They are removed from seeds at D. Property blocked earlier stays blocked under OFAC FAQ 402, which requires a separate "historically blocked" flag.

---

## 6. Red flags mapped to graph patterns

| Red flag (source) | Graph pattern / query idea |
|---|---|
| Stake cut to just below the threshold near designation (EU BP 67(c); OFAC 2026 "transfer near designation") | An OWNS edge from a listed person whose `valid_to` (or a pct change from ≥50 to <50) falls within ±N days (e.g. 90) of `listed_from` |
| Transfer to a family member or associate (OFAC 2026; EU BP 67(d); EU FAQ 5) | New OWNS from P2 to E starting within the window when old OWNS from S to E ends, where P2 is linked to S by a FAMILY/ASSOCIATE edge or SAME_AS, or shares an address or officer with S |
| Trust or foundation receiving assets (OFAC 2026; EU BP 67(e); Potanin/Sentimare, Kerimov/Heritage) | An entity of kind trust/foundation whose beneficiary or settlor is S or S's family and that owns ≥50% of the target |
| Largest-shareholder control (EU BP 67(a)) | Listed holder with pct ≥ 2× the next-largest holder and pct ≥ 25 → escalate |
| Aggregation just below thresholds (UK gap) | Multiple listed holders, each <50 but together ≥50. Status: blocked under OFAC and EU, not under UK unless a joint arrangement exists. Show it as a cross-regime divergence |
| Needlessly complex structures in higher-risk jurisdictions (OFAC 2026) | Chain depth ≥ 3 through entities in secrecy jurisdictions, or entities with no officers and no activity |
| Circular ownership | Strongly connected components in OWNS (Tarjan, O(V+E)) |
| Mass-registration address | REGISTERED_AT in-degree above a percentile threshold (formation-agent address) |
| Nominee director | Person with OFFICER_OF out-degree in the top 0.1%, or appointments across many unrelated companies |
| Re-incorporation or successor entity (OFAC 2026 narcotics example; EU 20th package successor ban) | A new entity created shortly after a listed entity, sharing officers, address or name similarity → SAME_AS candidate |
| Continued involvement after divestment (OFAC 2026) | Listed person still OFFICER_OF or CONTROLS the target after their OWNS edge expired |

FinCEN alerts FIN-2022-Alert001 and the March 2023 REPO Task Force advisory, the DOJ/Commerce/Treasury tri-seal notes, FATF R.24/R.25 (revised 2022/2023, with guidance in 2023/2024), and Wolfsberg sanctions-screening guidance were **NOT CHECKED** in this session. They are known to list similar shell, nominee and family-proxy red flags. Fetch them before citing.

---

## 7. Enforcement narratives (narrative only, no personal data in the graph)

1. **IPI Partners, OFAC settlement of $11,485,352, 2 Dec 2025.** VERIFIED, https://ofac.treasury.gov/media/934786/download?inline. Kerimov's money reached the fund through Definition Services Inc. (BVI), which was owned by Heritage Trust (Delaware). Outside counsel concluded no blocking was needed "because Kerimov did not formally own 50% or more of Definition". IPI knew Kerimov was the source of funds and dealt with his nephew-representative. The result was 51 apparent violations. **This is the demo story: a 50%-only check returns "clear", and the evidence layer shows why that was wrong.**
2. **GVA Capital, OFAC penalty notice of $215,988,868 (the statutory maximum), 12 Jun 2025.** VERIFIED, https://ofac.treasury.gov/media/934366/download?inline=. GVA managed Kerimov's investment through his nephew-proxy and Heritage Trust. OFAC warned against "relying on formalistic ownership arrangements that obscure the true parties in interest ... without sufficiently considering factors such as control or influence."
3. **Gracetown Inc., OFAC penalty of $7,139,305, 4 Dec 2025.** VERIFIED via press release, https://home.treasury.gov/news/press-releases/sb0328. A property manager whose ultimate beneficial owner was Deripaska processed payments for a Deripaska-owned entity after his designation, and did not report blocked property.
4. **Heritage Trust blocking (June 2022)** and **Potanin/Sentimare foundations (designated June 2024).** VERIFIED as described in the OFAC 2026 guidance.
5. **EM System, CJEU C-84/24 (12 Mar 2026).** SECONDARY. Assets of an unlisted Lithuanian company with an exactly-50% listed shareholder were frozen. The court confirmed the presumption is rebuttable.
6. **UK OFSI cases** (e.g. Wise Payments 2023, a withdrawal from a company account owned or controlled by a designated person; Herbert Smith Freehills Moscow 2025) are **NOT CHECKED**. Verify on the gov.uk OFSI enforcement page before citing them.

---

## 8. What analysts and regulators need from the tool

**VERIFIED anchors**
- OFAC, *A Framework for OFAC Compliance Commitments* (2 May 2019), cited in the GVA release. Testing, auditing and documented controls are expected.
- The UK strict-liability regime makes due diligence records the main mitigation (call for evidence 1.10, 1.15). HMG "does not prescribe the level or type of due diligence", but expects research, information requests and legal advice where obligations are unclear.
- The EU presumption model requires recording the **rebuttal evidence considered** (FAQ 1; BP 65-66, 68).

**Required product features** (derived from the above; the regulatory citations here are NOT CHECKED)
- An immutable audit trail per case: graph snapshot hash, as-of date D, list versions per regime, the rule parameters (threshold, operator, aggregate), and the evidence edges with their sources.
- Disposition codes: `TRUE_MATCH_BLOCKED`, `PRESUMED_CONTROLLED_REBUTTABLE`, `ESCALATE_RED_FLAG`, `FALSE_POSITIVE`, `NO_FINDING_AS_OF_D`, `INDETERMINATE_DATA_GAP`.
- Four-eyes review: the maker proposes, the checker approves, and both are logged. The LLM agent may only *propose*.
- Model governance: SR 11-7 (Fed/OCC 2011), and the April 2021 interagency statement on model risk management for BSA/AML systems, which treats such tools proportionately. These are NOT CHECKED this session, and any 2025-2026 revision of SR 11-7 is NOT CHECKED. Under the EU AI Act, Annex III treats creditworthiness scoring as high-risk but excludes fraud detection; whether AML or sanctions tooling counts as high-risk is UNVERIFIED. Treat the tool as a decision-support aid with a human in the loop.
- **A defensible "NO_FINDING" must state**: the target and its identifiers; the as-of date; each regime evaluated, with its threshold and aggregation rule; the list versions and dates; the data sources and their coverage gaps (missing pct, unknown beneficiaries); the maximum aggregated blocked stake found per regime, compared with the threshold; the red flags checked and their results; that integrated ownership is informational only; the reviewer identities; and the disclaimer "investigative evidence, not legal advice; no finding ≠ cleared".

---

## Open items (not checked because research was stopped early)
FinCEN/REPO/tri-seal advisories; FATF R.24/25 guidance; Wolfsberg; OFSI penalty notices; SR 11-7 and its 2021 BSA/AML statement; EU AI Act and AMLR provisions on automated decisions; verbatim Article 1 of Reg. 269/2014; UK Schedule 1 verbatim; whether the BIS stay was extended; Glattfelder/Vitali citation.
