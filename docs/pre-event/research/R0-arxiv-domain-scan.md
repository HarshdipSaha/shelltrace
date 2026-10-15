# R0: arXiv domain scan (ownership control, AML agents, temporal graphs, attribution)

_Run on 2026-10-05 with the `/arxiv` skill (arXiv export API; every ID below was returned by the API with the abstract quoted). The broader GraphRAG and agent literature is in [R5](R5-academic-sota.md). This scan covers the domain-specific papers a sanctions-ownership investigator should build on._

## Key findings that change the spec

1. **Ownership control has a validated, linear-time algorithm.** α-ICON ([2109.07181](https://arxiv.org/abs/2109.07181)) identifies ultimate controlling entities, unifies direct and indirect control with a damping factor, handles circular ownership by design, and found more than 96% of beneficiaries in an independent UK evaluation (4.2M companies). ShellTrace should compute control with an iterative algorithm of this kind instead of treating "connected within 6 hops" as exposure.
2. **Don't claim that hidden beneficial owners can be recovered.** Bingham ([2609.26171](https://arxiv.org/abs/2609.26171)) proves an identifiability bound on the full ICIJ graph (814K entities, 84K labelled owner edges). Isolated owners (20.6%) cannot be recovered above chance by any isomorphism-respecting link predictor, including GNNs. The paper also lists five evaluation traps. ShellTrace should only trace observed, cited edges, and the pitch should say that. That claim is honest and defensible; a "we infer hidden owners" claim would not be.
3. **Counterfactual checks make AML explanations measurable.** Torres et al. ([2604.19755](https://arxiv.org/abs/2604.19755)) combine evidence bundling, a structured output contract that separates supporting, contradicting and missing evidence, and counterfactual perturbation checks. They report citation validity 0.98, evidence support 0.88 and counterfactual faithfulness 0.76. ShellTrace can run exact counterfactuals natively: remove the hop, rerun the trace, and show whether the status flips. A graph can do this deterministically, which an LLM cannot.
4. **Keep probability out of the traversal.** The SAT-Graph API ([2510.06002](https://arxiv.org/abs/2510.06002)) specifies typed, atomic primitives between an LLM and a deterministic temporal graph. Uncertainty is allowed only in intent translation, anchoring and narrative, and every answer is grounded in an auditable log of graph operations. This matches "LLM proposes, graph disposes", and the spec should cite it as prior art.
5. **Entity-attribution failure is a separate failure mode from hallucination.** "Deceptive grounding" ([2607.09349](https://arxiv.org/abs/2607.09349)) is a real citation about the *wrong entity*. It slips past faithfulness and citation checks and occurs in 8–87% of adversarial cases. Checking entity attribution catches it at 97% precision. For ShellTrace this is the alias problem, so the report verifier must check that each cited record belongs to the node on that hop, not only that the citation exists.
6. **Extracting graph facts from text with an LLM creates an attack surface.** GraphRAG poisoning works through relation injection: GragPoison reaches up to 98% success at IEEE S&P 2026 ([2501.14050](https://arxiv.org/abs/2501.14050)). A few edited words in source text can move QA accuracy from 95% to 50% ([2508.04276](https://arxiv.org/abs/2508.04276)). See also KEPo ([2603.11501](https://arxiv.org/abs/2603.11501)) and LogicPoison ([2604.02954](https://arxiv.org/abs/2604.02954)). Any edge the LLM extracts (for example from a press release) must stay a *candidate* with a quoted span until a deterministic check or an analyst accepts it. Candidates never traverse.
7. **Tool results can inject prompts.** AgentDojo ([2406.13352](https://arxiv.org/abs/2406.13352)) shows tool-returned data hijacking agents. ToolHijacker ([2504.19793](https://arxiv.org/abs/2504.19793)) attacks tool selection itself. Entity names and source text in the graph are untrusted input, so the agent should get structured tool output, render names as data, and run with no write tools.
8. **Persistent case memory is case-based reasoning.** The CBR-for-LLM-agents review ([2504.06943](https://arxiv.org/abs/2504.06943)) defines retrieve, reuse, revise and retain. ShellTrace's "earlier cases touching this entity or address" fits that model: retrieve prior cases by graph overlap rather than by text similarity.
9. **Domain prior art to position against:**
   - Co-Investigator AI ([2509.08380](https://arxiv.org/abs/2509.08380)): agentic SAR drafting with agent-as-judge.
   - Adverse-media agent ([2602.23373](https://arxiv.org/abs/2602.23373)): evaluated on OpenSanctions PEP and sanctioned names.
   - LLM in-context learning over k-hop AML subgraphs ([2507.14785](https://arxiv.org/abs/2507.14785)).
   - CF3 evidence subgraphs for company financial risk ([2503.06441](https://arxiv.org/abs/2503.06441)).

   None of these runs a temporal, aggregated-ownership legal test inside a graph database with case memory and watches. That gap is ShellTrace's novelty.

## Paper table

| Paper | Year | ID | Key result | What ShellTrace borrows |
|---|---|---|---|---|
| Vitali, Glattfelder, Battiston: The network of global corporate control | 2011 | [1107.5728](https://arxiv.org/abs/1107.5728) | Bow-tie structure of transnational ownership; control computed per player over the integrated network | Defines integrated (indirect) ownership as a network flow; motivates computing it rather than eyeballing paths |
| Takes & Heemskerk: Centrality in the global network of corporate control | 2016 | [1605.08197](https://arxiv.org/abs/1605.08197) | 400K firms, 1.7M board-interlock edges; centrality of interlocks | Shared-director (OFFICER_OF) proximity is a separate signal from ownership; display it as context, not exposure |
| Polovnikov et al.: α-Indirect Control in Onion-like Networks (α-ICON) | 2021 | [2109.07181](https://arxiv.org/abs/2109.07181) | Linear-time ultimate-controller identification, handles cycles, more than 96% of beneficiaries found on UK data | Algorithm template for the control computation: iterative propagation, damping, cycle-safe |
| van Lidth de Jeude et al.: The multilayer structure of corporate networks | 2019 | [1901.07411](https://arxiv.org/abs/1901.07411) | Ownership and board layers carry different information | Model ownership/control and officer/address as separate layers with separate semantics |
| Abeltino et al.: Financial intermediaries and capital centralization in global FDI | 2026 | [2604.02875](https://arxiv.org/abs/2604.02875) | Tracing transnational control through intermediary chains | Intermediaries are the hops that hide control; supports "enabler" highlighting |
| Bingham: When concealed links cannot be recovered (offshore leaks) | 2026 | [2609.26171](https://arxiv.org/abs/2609.26171) | Identifiability bound; isolated owners (20.6%) are at a 0.5 floor; five evaluation traps | Never claim hidden-owner inference; evaluate only on observable structure; avoid the listed traps |
| Torres et al.: Explainable AML triage with LLMs, evidence retrieval and counterfactual checks | 2026 | [2604.19755](https://arxiv.org/abs/2604.19755) | Citation validity 0.98, counterfactual faithfulness 0.76, Escalate F1 0.62 | Structured output contract (support / contradict / missing) plus counterfactual checks on each hop |
| de Martim: Deterministic legal agents (SAT-Graph API) | 2025 | [2510.06002](https://arxiv.org/abs/2510.06002) | Typed primitive API over a temporal KG with probability isolation | Agent tools are typed primitives; every answer carries an auditable operation log |
| Caruzzo et al.: Deceptive grounding | 2026 | [2607.09349](https://arxiv.org/abs/2607.09349) | Wrong-entity attribution in 8–87% of adversarial cases; attribution verification has 97% precision | Report verifier checks citation belongs to the hop's node (alias-safe) |
| Liang et al.: GraphRAG under fire (GragPoison) | 2025 (S&P 2026) | [2501.14050](https://arxiv.org/abs/2501.14050) | Up to 98% attack success via relation injection | LLM-extracted edges stay candidates; provenance required; no traversal until accepted |
| Wen et al.: A few words can distort graphs | 2025 | [2508.04276](https://arxiv.org/abs/2508.04276) | Under 0.05% text edits move QA accuracy from 95% to 50% | Same: extraction is untrusted; deterministic acceptance gate |
| Debenedetti et al.: AgentDojo | 2024 | [2406.13352](https://arxiv.org/abs/2406.13352) | 97 tasks, 629 injection cases; agents hijacked by tool data | Treat graph strings as untrusted; read-only tools; adversarial golden case in tests |
| Shi et al.: Prompt injection attack to tool selection (ToolHijacker) | 2025 | [2504.19793](https://arxiv.org/abs/2504.19793) | Tool selection can be hijacked | Fixed tool allowlist with static descriptions; tool choice validated by a policy |
| Hatalis et al.: Review of case-based reasoning for LLM agents | 2025 | [2504.06943](https://arxiv.org/abs/2504.06943) | CBR retrieve, reuse, revise, retain for accountable agents | Case memory = CBR; retrieve prior cases by graph overlap |
| Naik et al.: Co-Investigator AI | 2025 | [2509.08380](https://arxiv.org/abs/2509.08380) | Agentic SAR drafting with a validation agent, human in the loop | Draft report with a verifier; human approval stays mandatory |
| Chernakov et al.: Agentic adverse media screening | 2025 | [2602.23373](https://arxiv.org/abs/2602.23373) | Agent computes an adverse media index; evaluated on OpenSanctions names | Prior art for agentic screening; ShellTrace differs by doing structure, not media |
| Pirmorad: LLM in-context learning for AML on financial graphs | 2025 (ICDM workshop) | [2507.14785](https://arxiv.org/abs/2507.14785) | LLM over serialized k-hop subgraphs emulates analyst logic | The baseline ShellTrace improves on: the LLM narrates, but the graph decides |
| Du et al.: CF3 evidence subgraphs via counterfactual and factual reasoning | 2025 | [2503.06441](https://arxiv.org/abs/2503.06441) | Evidence subgraphs explain company risk | Evidence subgraph equals the minimal set of hops whose removal flips status |
| Si et al.: Conformal constrained policy optimization for LLM agents | 2025 | [2511.11828](https://arxiv.org/abs/2511.11828) | Conformal guarantees for cost-aware agent routing | Optional: conformal threshold for escalation once the eval set exists |
| Hu et al.: Chronofy, temporal-logical decay for time-aware RAG | 2026 | [2607.20560](https://arxiv.org/abs/2607.20560) | Obsolete facts cause temporal hallucination | Use hard validity intervals on edges, not soft recency decay |

## Queries run

The `/arxiv` skill ran these queries:
- `ti:"corporate control" AND abs:network`
- `abs:"ultimate controller" AND abs:ownership`
- `abs:"beneficial ownership" AND abs:network`
- `abs:"integrated ownership"`
- `abs:sanctions AND abs:ownership AND abs:network`
- `abs:"shell companies" AND abs:graph`
- `abs:"sanctions evasion"`
- `all:"ownership network" AND all:companies`
- `all:"beneficial owner"`
- AML + KG/LLM
- temporal KG + RAG
- GraphRAG + poisoning
- entity resolution + LLM
- Text2Cypher
- conformal + tool agents
- selective prediction + abstain
- sanctions name matching
- watchlist screening
- counterfactual path explanations
- citation faithfulness
- CBR + LLM agents
- temporal agent memory
- prompt-injection defenses for tools
- correlation clustering for ER

Some arXiv queries returned nothing, notably `sanctions AND ownership AND network` and `shell companies AND graph`. That gap in the academic literature supports the novelty claim.
