# R5 - Academic State of the Art for ShellTrace (verified subset)

Status: PARTIAL. Research was stopped early by the coordinator. Every paper in the tables below was checked against a fetched arXiv API record (title, first author, date, comments/venue, abstract) or, for TimeR4, the ACL Anthology page. Numbers come only from those abstracts or from the arXiv HTML full text where noted. Clusters E (financial-crime graphs) and G (evaluation methodology) and part of F (calibration, abstention, conformal prediction, citation attribution) are **NOT CHECKED**. Candidate titles for those gaps are listed at the end and marked unverified. Do not cite them until someone checks them.

Date of review: 2026-10-05.

---

## Key findings that change the spec

1. **Graphs help on multi-hop and temporal questions. They hurt or tie on single-fact lookups.** RAG vs. GraphRAG (2502.11371) found RAG ahead on single-hop NQ (64.78 vs 63.01 F1) and on detail-oriented NovelQA (55.28 vs 46.88). GraphRAG was ahead on HotpotQA multi-hop (61.66 vs 60.04) and well ahead on MultiHop-RAG *temporal* queries (50.60 vs 30.70). ShellTrace's questions ("is X exposed, through what chain, as of date D?") are multi-hop and temporal, so a graph is the right choice. The pitch should say that and should not claim graphs win everywhere.
2. **LLM-extracted KGs lose answers.** In the same study, only about 65.8% (HotpotQA) and 65.5% (NQ) of answer entities appeared in the LLM-built KG. ShellTrace should build its graph from structured registries and sanctions lists, not LLM triple extraction. Any LLM-extracted edge should be marked as lower-trust provenance.
3. **Published GraphRAG gains are inflated by evaluation bias.** LLM-as-judge position bias can flip pairwise preferences (2502.11371). An unbiased framework found GraphRAG gains "much more moderate than reported previously" (2506.06331). ShellTrace should evaluate with deterministic, ground-truth metrics (path found or not, correct verdict, correct as-of date) on a labeled cohort, not with LLM preference judgments.
4. **Token cost varies by about 300x across GraphRAG designs.** GraphRAG-Bench (2506.05690) measured MS-GraphRAG global at about 331k tokens per query, LightRAG about 100k, HippoRAG2 about 1k, and vanilla RAG about 954. Community-summary GraphRAG is the wrong design for a per-entity investigation. Use targeted path retrieval in the HippoRAG/PathRAG style.
5. **The answer should be the path itself.** PathRAG (2502.14902) argues the weakness of graph RAG is redundancy, not missing information. It retrieves pruned relational paths and prompts with them as text. RoG (2310.01061) grounds its plans in KG relation paths for faithfulness. ShellTrace should return ranked, pruned, temporally valid paths as the primary artefact, with the LLM only narrating them.
6. **PPR is a proven graph-retrieval primitive.** HippoRAG (2405.14831) uses Personalized PageRank and gains up to 20% on multi-hop QA. Single-step retrieval was 10-30x cheaper and 6-13x faster than iterative IRCoT. HippoRAG 2 (2502.14802) keeps PPR and fixes the factual-recall regression. This supports ShellTrace's PPR exposure score as a recognised technique, but PPR should rank candidates, not issue verdicts.
7. **Free-form text-to-Cypher is not reliable enough for compliance verdicts.** CypherTurn (2609.36987, EMNLP 2026 oral) found the best model reaches only 64.7% execution accuracy, with session-level correctness below 5%. Strong models self-limit to about two actions per turn whatever the budget. LAST-CQ (2609.12746) found that failure detection plus retry recovers 91.7% of failed queries, and that its LLM judge was 9 points optimistic against human labels. This justifies **parameterized, read-only graph tools** instead of LLM-written Cypher. If free-form Cypher is ever offered, it should be an analyst-only "explore" mode with execution validation and retry.
8. **LLM-to-database query generation is an injection surface.** P2SQL (2308.01990, ICSE 2025) showed that LangChain-style prompt-to-SQL apps are "highly susceptible" to SQL injection via prompts across 7 LLMs. The same risk applies to Cypher, which is another reason for the parameterized-tool design.
9. **Tool results are untrusted input.** Indirect prompt injection is well documented: Greshake 2302.12173. InjecAgent (2403.02691) found ReAct GPT-4 vulnerable 24% of the time, and nearly double that with a hacking prompt. CaMeL (2503.18813) gets provable security by separating control flow, which is planned from the trusted query, from data flow. It solves 77% of AgentDojo tasks vs 84% undefended. Entity names, addresses and notes read from the graph are attacker-controllable, for example a shell company named "IGNORE PREVIOUS INSTRUCTIONS...". The tool plan should be fixed before data is read, and the verdict should be computed by code, not by the LLM.
10. **GraphRAG can be poisoned through shared relations.** GraphRAG under Fire (2501.14050, IEEE S&P 2026) reports a GragPoison attack with up to 98% success. Further attacks followed in 2025-26: 2508.04276, KEPo 2603.11501 (WWW 2026) and LogicPoison 2604.02954. Ingest provenance (source list, retrieval time, hash) should be stored on every edge, and verdicts should be explainable by source.
11. **Persistent agent memory is an attack surface.** AgentPoison (2407.12784) and MINJA (2503.03704) poison memory, and MINJA does it with queries alone. The EMNLP 2026 memory-security survey (2604.16548) concludes that memory security "must be anchored in storage-time provenance, versioning, and policy-aware retention" and cannot be added at retrieval time. Case memory, meaning decisions, analyst reviews and watches, should be append-only, versioned and author-attributed. Agent-written memory should never be reused as evidence without analyst sign-off.
12. **Bi-temporal edges are the established pattern for agent memory.** Zep/Graphiti (2501.13956) keeps historical relationships in a temporally aware KG. It scores 94.8% vs MemGPT's 93.4% on DMR and gains up to 18.5% accuracy with 90% lower latency on LongMemEval. T-GRAG (2508.01680) found that GraphRAG which ignores time suffers from "temporal ambiguity, time-insensitive retrieval". It is evaluated on corporate annual reports. ShellTrace should model valid time (designation and ownership intervals) separately from transaction time (when we learned it). That separation makes "CLEAR as of D" reproducible and supports the live-flip demo.
13. **Transitive closure over noisy SAME_AS creates over-merged clusters.** Lauren et al. (2610.00566) found that the risk of merging distinct individuals under transitive closure grows with population size. Leiden, Louvain and label propagation cut linkage error by up to 66% relative to transitive closure. ShellTrace's WCC alias resolution should be replaced or guarded: run Leiden or label propagation on weighted SAME_AS edges, cap cluster size or diameter, and send bridge edges to human review.
14. **Corporate-family links are mostly invisible to name matching.** CorpFam (2609.04269) found the strongest matcher recovers 100% of identical-name pairs but only 4.2% of pairs with no shared name token. Blocking misses 93.2% of those "invisible" links. Ownership and control edges therefore find exposure that name screening cannot. This is the quantitative core of the "vs name-screening baseline" story.
15. **LLMs are strong entity matchers if the prompt sees several candidates.** Peeters et al. (2310.11244, EDBT 2025) found the best LLMs, with no or few examples, match PLMs fine-tuned on thousands of examples, and are more robust to unseen entities. "Match, Compare, or Select?" (2405.16884, COLING 2025) found that a *selecting* strategy, choosing among candidates, beats pairwise matching. Ditto (2004.00584) reached 96.5% F1 on 789K x 412K company records. An LLM should adjudicate only ambiguous SAME_AS candidates, using a select-among-candidates prompt and a structured explanation.

---

## A. GraphRAG SOTA and critiques

| Paper | Year / venue | ID | Key result | Borrow for ShellTrace |
|---|---|---|---|---|
| From Local to Global: A Graph RAG Approach to Query-Focused Summarization (Edge et al.) | 2024, arXiv (Microsoft) | 2404.16130 | Entity KG plus pre-generated community summaries. Big gains in comprehensiveness and diversity on "global sensemaking" questions over about 1M-token corpora. | Contrast case only. Our queries are local and path-shaped, not global summarization. Do not build community summaries. |
| LightRAG (Guo et al.) | 2024, arXiv | 2410.05779 | Dual-level (entity/theme) graph+vector retrieval with **incremental update**. | Incremental ingest pattern for new designations without a full rebuild. |
| HippoRAG (Gutierrez et al.) | 2024, NeurIPS | 2405.14831 | KG + Personalized PageRank. Up to 20% better on multi-hop QA. 10-30x cheaper and 6-13x faster than IRCoT. | PPR seeded at the target entity as a *ranking* signal (exposure score). |
| From RAG to Memory / HippoRAG 2 (Gutierrez et al.) | 2025, ICML | 2502.14802 | Structured RAG methods had regressed on basic factual recall. HippoRAG 2 fixes this and gains 7% on associative memory. | Keep exact-lookup tools (entity by ID, sanctions list lookup) next to graph search. Do not route everything through the graph. |
| PathRAG (Chen et al.) | 2025, arXiv | 2502.14902 | Flow-based pruning of relational paths plus path-as-text prompting. Beats baselines on 6 datasets and 5 dimensions. | Rank and prune paths, then serialize each path as an ordered evidence chain for the narrator. |
| G-Retriever (He et al.) | 2024, arXiv | 2402.07630 | Retrieves a subgraph for textual-graph QA. | Return a bounded subgraph (k paths, max hops) as the evidence object. |
| RAG vs. GraphRAG: A Systematic Evaluation (Han et al.) | 2025, arXiv (v3 2026) | 2502.11371 | RAG wins single-hop and detail questions. GraphRAG wins multi-hop and temporal (50.60 vs 30.70 on MultiHop-RAG temporal). Only about 65% of answer entities are in LLM-built KGs. LLM judges show position bias. | Justify graph use by query type. Build from structured sources. Avoid pairwise LLM judging. |
| When to use Graphs in RAG / GraphRAG-Bench (Xiang et al.) | 2025, arXiv | 2506.05690 | Vanilla RAG wins fact retrieval (60.92 vs 49.29). GraphRAG wins complex reasoning (HippoRAG2 53.38 vs 42.93). Token cost ranges from about 1k to 331k per query. | The cost and latency argument for targeted path tools. Report tokens per investigation. |
| GraphRAG-Bench: Domain-Specific Reasoning (Xiao et al.) | 2025, arXiv | 2506.02404 | Evaluates construction, retrieval and generation, plus reasoning coherence, not only the final answer. | Evaluate each stage separately: alias resolution, path retrieval, verdict, narrative. |
| How Significant Are the Real Performance Gains? Unbiased Evaluation for GraphRAG (Zeng et al.) | 2025, arXiv | 2506.06331 | Once unrelated questions and judge bias are removed, GraphRAG gains are "much more moderate than reported." | Use ground-truth labelled cohort metrics. If an LLM judge is used, swap answer order and report agreement. |
| In-depth Analysis of Graph-based RAG in a Unified Framework (Zhou et al.) | 2025, arXiv | 2503.04338 | Unified framework compares graph RAG methods on specific vs abstract QA. New combinations of existing pieces beat SOTA. | Treat graph RAG as composable operators. Our tools are such operators. |
| Graph RAG: A Survey (Peng et al.) | 2024, arXiv | 2408.08921 | Survey of graph-based indexing, retrieval and generation. | Taxonomy terms for the spec. |
| Retrieval-Augmented Generation with Graphs (Han et al.) | 2024, arXiv | 2501.00309 | Survey of GraphRAG. | Taxonomy and related work. |
| Unifying LLMs and KGs: A Roadmap (Pan et al.) | 2023, arXiv | 2306.08302 | KG-enhanced LLM, LLM-augmented KG and synergized paradigms. | Frame ShellTrace as "KG reasons, LLM explains". |

**What justifies path-as-answer over vector RAG:** the multi-hop and temporal advantages (2502.11371, 2506.05690), PathRAG's redundancy argument (2502.14902), RoG's faithful path plans (2310.01061), and HippoRAG's cost efficiency (2405.14831). The counter-evidence is also needed for credibility: graph indexing hurts simple lookups and LLM-extracted KGs miss about 35% of answers.

## B. Agentic graph reasoning and text-to-Cypher

| Paper | Year / venue | ID | Key result | Borrow |
|---|---|---|---|---|
| Think-on-Graph (Sun et al.) | 2024, ICLR | 2307.07697 | LLM agent beam-searches the KG. SOTA on 6 of 9 datasets without training. Offers "knowledge traceability and correctability". | Beam-bounded exploration with explicit width and depth. Analyst feedback corrects an edge, not the model. |
| Think-on-Graph 2.0 (Ma et al.) | 2024, arXiv | 2407.10805 | Alternates graph retrieval and document context retrieval. SOTA on 6 of 7 datasets with GPT-3.5. | Pair graph paths with source-document snippets such as the designation notice text. |
| Reasoning on Graphs (RoG) (Luo et al.) | 2024, ICLR | 2310.01061 | Plans as KG-grounded relation paths, then retrieves valid paths for faithful, interpretable reasoning. | Relation-path templates (OWNS+ -> SANCTIONED, OFFICER_OF -> CONTROLS -> ...) as the agent's plan vocabulary. |
| KG-Agent (Jiang et al.) | 2024, arXiv | 2402.11163 | Small LLM plus toolbox plus KG executor plus memory. A 7B model with 10K tuning samples beats larger LLMs. | Toolbox-plus-executor architecture. A small model can be enough when tools do the work. |
| StructGPT (Jiang et al.) | 2023, EMNLP | 2305.09645 | Iterative reading-then-reasoning through specialised interfaces for KGs, tables and DBs. | Interface functions that linearize results compactly for the LLM. |
| GraphReader (Li et al.) | 2024, EMNLP | 2406.14550 | An agent with predefined read-node and read-neighbour functions and a notebook beats GPT-4-128k with a 4k window. | Predefined functions plus a running "case notebook". The bounded agent loop works. |
| Graph Chain-of-Thought (Jin et al.) | 2024, ACL | 2404.07103 | Iterates LLM reasoning, LLM-graph interaction and graph execution. GRBench has 1,740 questions. | Step-structured trace (reason -> tool -> result) stored as an audit log. |
| ChatKBQA (Luo et al.) | 2024, ACL Findings | 2310.08975 | Generate the logical form first, then retrieve and bind entities. SOTA on WebQSP and CWQ. | Bind entity mentions to graph IDs as a separate step before any query runs. |
| Graph-R1 (Luo et al.) | 2025 arXiv, ICML 2026 | 2507.21892 | Agentic GraphRAG trained with end-to-end RL. Multi-turn agent-environment retrieval. | Future work only. Not needed for the hackathon. |
| Search-on-Graph-R1 (Sun et al.) | 2026, arXiv | 2607.18481 | An 8B model trained by SFT+RL to call a live Search tool beats frozen frontier-LLM systems on WebQSP, CWQ and GrailQA. | Evidence that tool-mediated KG navigation is the dominant paradigm. |
| ReAct (Yao et al.) | 2023, ICLR | 2210.03629 | Interleaved reasoning and acting reduces hallucination on HotpotQA and FEVER. | Baseline agent loop pattern. |
| CypherBench (Feng et al.) | 2024, arXiv | 2412.18702 | Huge RDF schemas are inefficient for LLMs, so it proposes property-graph views. 11 graphs, 7.8M entities, over 10k questions. | Expose a **small, normalized schema view** to the agent. Headline accuracy numbers NOT CHECKED (fetch failed). |
| Text2Cypher (Ozsoy et al., Neo4j) | 2024, arXiv | 2412.10064 | 44,387-instance dataset. Fine-tuning gives large EM and BLEU gains. Zero-shot LLMs "often struggle". | Supports avoiding zero-shot Cypher generation for verdict paths. |
| CypherTurn (Zhang et al.) | 2026, EMNLP oral | 2609.36987 | Best model 64.7% execution accuracy. Session-level correctness below 5%. "Autonomy Divergence". Models self-limit to about 2 actions per turn. | **Key evidence for parameterized tools.** Also: give a step budget, but don't expect the model to use all of it. |
| LAST-CQ (Prokopiou et al.) | 2026, EMNLP REALM workshop | 2609.12746 | Detect-and-retry recovers 91.7% of failures. Raw DB errors are as good as LLM feedback. LLM judge 9 points optimistic. | If free-form Cypher is allowed, add execution validation plus a retry on error. Calibrate any judge against humans. |
| P2SQL: From Prompt Injections to SQL Injection Attacks (Pedro et al.) | 2025, ICSE | 2308.01990 | LangChain prompt-to-SQL apps are highly susceptible to SQL injection across 7 LLMs. | Read-only DB role plus parameterized queries. No string-built queries. |

Other recent text-to-Cypher work, verified by title only: Schema Filtering 2505.05118, Multi-Agent GraphRAG text-to-Cypher 2511.08274, PIPE-Cypher 2606.08481 (enterprise benchmark generation on FinBench/SNB; "zero-shot transfer is weak").

## C. Temporal KGs, temporal RAG and agent memory

| Paper | Year / venue | ID | Key result | Borrow |
|---|---|---|---|---|
| Zep: A Temporal Knowledge Graph Architecture for Agent Memory (Rasmussen et al.) | 2025, arXiv | 2501.13956 | The Graphiti temporal KG keeps historical relations. DMR 94.8% vs MemGPT 93.4%. LongMemEval up to +18.5% accuracy with 90% lower latency. | Bi-temporal edge model (valid interval plus ingest/expiry time). Invalidate edges, never delete them. |
| T-GRAG (Li et al.) | 2025, arXiv | 2508.01680 | GraphRAG that ignores time shows temporal ambiguity. Temporal KG generator, query decomposition and a layered retriever. Time-LongQA benchmark built on corporate annual reports. | Filter subgraphs by time *before* path search. Sanctions questions always carry an implicit date. |
| TimeR4 (Qian et al.) | 2024, EMNLP | ACL 2024.emnlp-main.394 | Retrieve-rewrite-retrieve-rerank makes time constraints explicit. 47.8% and 22.5% relative gains. | Rewrite "is X exposed?" into an explicit "as_of=D" parameter before calling tools. |
| Question Answering over Temporal KGs / CronQuestions (Saxena et al.) | 2021, ACL | 2106.01515 | Temporal KG edges carry start and end times. The dataset is 340x larger than prior ones, and existing KGQA methods fall short on it. | Validity-interval edge semantics. Stratify the test set by temporal complexity. |
| Temporal KGQA: A Survey (Su et al.) | 2024, arXiv | 2406.14191 | Taxonomy of temporal question types. | Categorize our temporal test questions ("as of", "before/after designation", "during interval"). |
| Test of Time (Fatemi et al.) | 2024, arXiv | 2406.09170 | LLMs make errors on complex temporal logic. | Do interval arithmetic in code or Cypher, never in the LLM. |
| MemGPT (Packer et al.) | 2023, arXiv | 2310.08560 | OS-style tiered memory with paging. | Working context (current case) vs archival (graph). |
| A-MEM (Xu et al.) | 2025, NeurIPS | 2502.12110 | Zettelkasten-style linked, evolving memory notes. | Link case notes to entities. Note that memory evolution conflicts with audit, so version the notes. |
| Mem0 (Chhikara et al.) | 2025, arXiv | 2504.19413 | 26% relative gain over OpenAI memory on LOCOMO. Graph variant about 2% better. 91% lower p95 latency. | Extract, consolidate and retrieve decisions as structured facts. |
| LongMemEval (Wu et al.) | 2025, ICLR | 2410.10813 | Five abilities including temporal reasoning, knowledge updates and **abstention**. 30% accuracy drop across sustained interactions. | Test the case-memory recall of "what did we decide about entity X last time, and is it still valid?" |
| Survey on Memory Mechanism of LLM Agents (Zhang et al.) | 2024, arXiv | 2404.13501 | Survey. | Terminology. |
| Survey of Agent Memory in the Second Half (Huang et al.) | 2026, TMLR | 2602.06052 | Survey (title and venue verified). | Related work. |
| Survey on Long-Term Memory Security in LLM Agents (Lin et al.) | 2026, EMNLP | 2604.16548 | Memory lifecycle threat model. Calls for storage-time provenance, versioning and policy-aware retention. | **Case memory = append-only, versioned, provenance-stamped.** |

## D. Entity resolution with LLMs and graphs

| Paper | Year / venue | ID | Key result | Borrow |
|---|---|---|---|---|
| Entity Matching using LLMs (Peeters et al.) | 2025, EDBT | 2310.11244 | Best LLMs with no or few examples match PLMs fine-tuned on thousands. More robust to unseen entities. GPT-4 produces structured explanations. Prompt must be tuned per model and dataset. | LLM adjudicates gray-zone SAME_AS only, with a structured explanation stored on the edge. |
| Match, Compare, or Select? (Wang et al.) | 2025, COLING | 2405.16884 | The *selecting* strategy beats binary matching across 8 datasets and 10 LLMs. ComEM is cheaper. | Prompt: "which of these k candidates, if any, is the same entity?" Include a "none" option. |
| Can Foundation Models Wrangle Your Data? (Narayan et al.) | 2022, arXiv (VLDB 2023) | 2205.09911 | FMs reach SOTA on data cleaning and integration tasks via prompting. | Prior evidence for LLM-assisted matching. |
| Ditto (Li et al.) | 2021, VLDB | 2004.00584 | PLM matcher. 96.5% F1 on 789K x 412K company records. | A cheap, strong first-pass matcher for company names. LLM only on residuals. |
| In-context Clustering-based ER with LLMs (Fu et al.) | 2026, SIGMOD | 2506.02509 | Design space for LLM in-context *clustering* rather than pairwise matching (title and venue verified). | Cluster-level adjudication of alias groups. |
| On Leveraging LLMs for Enhancing ER: Cost-efficient (Li et al.) | 2024, arXiv | 2401.03426 | Title verified. | Budgeted LLM queries for ER. |
| Adaptive Graph Refinement and Label Propagation with LLMs for ER (Wang et al.) | 2026, arXiv | 2605.25814 | Title verified. Graph refinement plus label propagation. | LLM refines the edges, then label propagation forms clusters. |
| Probabilistic linkage with graphs (Lauren et al.) | 2026, arXiv | 2610.00566 | The risk of merging distinct individuals under transitive closure grows with population. Leiden, Louvain and label propagation cut error by up to 66% and run up to 40x faster than Markov clustering. | **Replace raw WCC with Leiden or label propagation on weighted SAME_AS. Keep WCC as a diagnostic.** |
| CorpFam: Corporate-Family Resolution Is Not a String-Matching Problem (Gupta) | 2026, arXiv | 2609.04269 | 54,864 pairs. Matchers recover 100% of identical-name pairs and at most 4.7% of no-shared-token pairs. 93.2% of invisible links never reach the candidate set. | **Headline for "name screening misses structural exposure."** Report recall per name-visibility stratum, not F1. |
| Graph-based hierarchical record clustering for unsupervised ER (Ebeid et al.) | 2022, ITNG | 2112.06331 | Title verified. | Related work. |
| Clustering with Noisy Queries (Mazumdar and Saha) | 2017, arXiv (NeurIPS 2017) | 1706.07510 | Theory of clustering with a faulty oracle, motivated by crowdsourced ER. | Theory for human-in-the-loop alias confirmation budgets. |

NOT CHECKED in D: classic correlation clustering (Bansal-Blum-Chawla) and Hassanzadeh et al. VLDB 2009 (the Semantic Scholar API returned 429), and sanctions-specific name-matching papers. The arXiv search for sanctions and watchlist name matching found nothing relevant.

## E. Financial crime graphs - NOT CHECKED

No paper in this cluster was verified before the stop. These are candidates to verify. The IDs are from memory and are unverified, so do not cite them yet:
- Weber et al., "Anti-Money Laundering in Bitcoin: Experimenting with Graph Convolutional Networks" (Elliptic), 2019, believed 1908.02591
- Altman et al., "Realistic Synthetic Financial Transactions for Anti-Money Laundering Models" (AMLworld), NeurIPS 2023 D&B, believed 2306.16424
- Egressy et al., "Provably Powerful Graph Neural Networks for Directed Multigraphs", believed 2306.11586
- Bellei et al., Elliptic2 subgraph classification, believed 2404.19109
- Vitali, Glattfelder, Battiston, "The network of global corporate control", PLoS ONE 2011, believed 1107.5728
- Glattfelder and Battiston, "Backbone of complex networks of corporations: the flow of control", believed 0902.0878
- Garcia-Bernardo et al., "Uncovering Offshore Financial Centers: Conduits and Sinks", believed 1703.03016
- Bellomarini, Gottlob et al., Vadalog company-control reasoning at Bank of Italy (venue and ID unverified)

## F. Trustworthy LLM decisions

Verified:

| Paper | Year / venue | ID | Key result | Borrow |
|---|---|---|---|---|
| Not what you've signed up for: Indirect Prompt Injection (Greshake et al.) | 2023, arXiv | 2302.12173 | Retrieved data can act like "arbitrary code execution" and control which APIs are called. | Treat graph string fields as untrusted. |
| InjecAgent (Zhan et al.) | 2024, ACL Findings | 2403.02691 | 1,054 cases. ReAct GPT-4 vulnerable 24% of the time, nearly double with a hacking prompt. | Red-team test: a shell company whose name or notes contain injected instructions. |
| AgentDojo (Debenedetti et al.) | 2024, arXiv (NeurIPS D&B) | 2406.13352 | 97 tasks and 629 security cases. Tool results hijack agents. | Use it as the evaluation pattern for our injection tests. |
| CaMeL: Defeating Prompt Injections by Design (Debenedetti et al.) | 2025, arXiv | 2503.18813 | Control and data flow separation plus capabilities. 77% of tasks solved with provable security vs 84% undefended. | Plan the tools from the analyst query, read data into variables, and let code compute the verdict. |
| Design Patterns for Securing LLM Agents against Prompt Injections (Beurer-Kellner et al.) | 2025, arXiv | 2506.08837 | Principled patterns with provable resistance. | Cite the plan-then-execute and action-selector patterns for our bounded tool agent. |
| GraphRAG under Fire (Liang et al.) | 2026, IEEE S&P | 2501.14050 | GragPoison exploits shared relations. Up to 98% success. | Edge provenance and source trust tiers. Flag paths that rely on a single source. |
| A Few Words Can Distort Graphs (Wen et al.) | 2025, arXiv | 2508.04276 | Knowledge poisoning of GraphRAG (title verified). | Same as above. |
| KEPo (Chen et al.) | 2026, WWW | 2603.11501 | Knowledge-evolution poisoning of GraphRAG (title and venue verified). | Temporal poisoning risk for injected designations. Require a source on every injection. |
| LogicPoison (Xiao et al.) | 2026, arXiv | 2604.02954 | Logical attacks on GraphRAG (title verified). | Same as above. |
| Query-Efficient Agentic Graph Extraction Attacks on GraphRAG (Yang et al.) | 2026, ACL | 2601.14662 | GraphRAG responses can leak the hidden graph. | Rate-limit tool calls and scope results to a case. |
| AgentPoison (Chen et al.) | 2024, arXiv (NeurIPS 2024) | 2407.12784 | Backdoor via a poisoned memory or knowledge base. | Case memory is not evidence. |
| MINJA (Dong et al.) | 2025, arXiv | 2503.03704 | Memory injection through queries alone. | Only analysts can write durable decisions. Agent notes are quarantined. |

NOT CHECKED in F: Kadavath et al. "Language Models (Mostly) Know What They Know"; Xiong et al. on verbalized confidence; Tian et al. "Just Ask for Calibration"; Kamath et al. selective QA; the abstention survey "Know Your Limits"; conformal LLM papers (Quach et al., Mohri and Hashimoto, KnowNo); ALCE (Gao et al.); attribution evaluation (Yue et al.); MT-Bench judge bias (Zheng et al.); "LLMs are not fair evaluators" (Wang et al.). The judge-bias point is still supported by the verified 2502.11371, 2506.06331 and 2609.12746.

## G. Evaluation methodology - NOT CHECKED

Not verified: HotpotQA, 2WikiMultiHopQA, MuSiQue, Trivedi et al. "Is Multihop QA in DiRe Condition?", Press et al. compositionality gap, ERASER, Jacovi and Goldberg on faithfulness, MultiHop-RAG, STaRK, FRAMES. Verified evaluation-relevant evidence from the other clusters: per-stage evaluation (2506.02404), unbiased evaluation (2506.06331), session-level vs turn-level correctness (2609.36987), per-stratum recall instead of F1 (2609.04269), the abstention ability in LongMemEval (2410.10813), and judges calibrated against human labels (2609.12746).

---

## Design principles distilled

1. **The graph decides and the LLM narrates.** Verdicts (EXPOSED / CLEAR-within-N-as-of-D / ESCALATE) come from deterministic path search plus ownership arithmetic. The LLM picks tools and explains returned paths. (2310.01061, 2502.14902, 2503.18813, 2406.09170)
2. **Use parameterized read-only tools, not free-form Cypher, for verdicts.** Free-form NL-to-Cypher tops out around 65% execution accuracy and is an injection surface. (2609.36987, 2412.10064, 2308.01990)
3. **Plan before reading.** Fix the tool plan from the trusted analyst query. Data returned by tools never adds new tool calls outside a bounded budget. (2503.18813, 2506.08837, 2403.02691)
4. **The path is the answer.** Return pruned, ranked, temporally valid paths with per-edge provenance. Use PPR only to rank. (2502.14902, 2405.14831)
5. **Make time explicit.** Every query carries `as_of`, and edges are bi-temporal (valid time vs knowledge time). Filter by time before traversal. (2501.13956, 2508.01680, ACL 2024.emnlp-main.394, 2106.01515)
6. **Alias clusters must resist chaining.** Use Leiden or label propagation on weighted SAME_AS, cap cluster size, and send bridges to analysts. The LLM adjudicates gray-zone pairs with a select-among-candidates prompt. (2610.00566, 2405.16884, 2310.11244)
7. **Structure beats names.** Show recall on name-invisible links against a name-screening baseline, reported per stratum. (2609.04269)
8. **Provenance on every edge.** Store source, ingest time and hash, and flag single-source paths. This defends against poisoning and makes audits possible. (2501.14050, 2603.11501)
9. **Memory is append-only and attributed.** Analyst decisions are durable. Agent notes are not evidence. (2604.16548, 2503.03704, 2407.12784)
10. **Evaluate deterministically, per stage, per stratum.** Avoid pairwise LLM-judge preferences. If a judge is used, swap answer order and calibrate it against humans. (2502.11371, 2506.06331, 2609.12746)
11. **Report cost.** Give tokens and latency per investigation. Targeted retrieval is about 1k tokens vs about 331k for global GraphRAG. (2506.05690)

## Claims we can safely make in the pitch (with citation)

- "Graph retrieval beats vanilla RAG on multi-hop and temporal questions, and loses on single-fact lookups. ShellTrace's questions are multi-hop and temporal." (Han et al., 2502.11371. Xiang et al., 2506.05690)
- "LLM-extracted knowledge graphs miss about a third of answer entities. We build from authoritative structured sources instead." (2502.11371)
- "Even frontier models reach only about 65% execution accuracy on conversational text-to-Cypher, and below 5% session correctness. We use parameterized graph tools instead." (CypherTurn, 2609.36987)
- "Name matching recovers under 5% of corporate-family links where names share no token. Ownership edges find what name screening cannot." (CorpFam, 2609.04269)
- "Transitive closure over noisy matches over-merges as data grows. Community-detection clustering cuts linkage error by up to 66%." (2610.00566)
- "Personalized PageRank retrieval is 10-30x cheaper than iterative LLM retrieval for multi-hop QA." (HippoRAG, 2405.14831)
- "Temporal knowledge graphs with preserved history are the state-of-the-art agent memory architecture." (Zep, 2501.13956)
- "GraphRAG systems can be poisoned with up to 98% success. We keep provenance on every edge." (GraphRAG under Fire, IEEE S&P 2026, 2501.14050)
- "Separating control flow from untrusted data gives provable prompt-injection resistance at small utility cost." (CaMeL, 2503.18813)
- Do NOT claim anything about AML GNN benchmarks, corporate-control network statistics, or LLM calibration or conformal guarantees until clusters E, F (calibration) and G are verified.
