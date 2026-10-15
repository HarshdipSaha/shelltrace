# R1: Hackathon intelligence and TypeSafe check

Researched 2026-10-05. Sources are the live WeMakeDevs pages (raw HTML pulled and converted to text the same day), TypeSafe's docs (`llms.txt` and per-page `.md`), and web search. Anything I could not confirm from a primary page is marked **UNVERIFIED**.

---

## Key findings that change the spec

- **The hackathon has been reframed, and "Investigation and Risk" is gone.** The live event is called **"Graph Hacks: Context for AI Agents"**, not "Building Next-Gen RAG" ([overview](https://www.wemakedevs.org/hackathons/falkordb)). The three tracks are now **Track 01 "Agents That Act on Connected Data"**, **Track 02 "Agent Memory and Coordination"** and **Track 03 "Company Brain"** ([rules #5](https://www.wemakedevs.org/hackathons/falkordb/rules)). The GraphRAG-SDK track was removed. ShellTrace belongs in **Track 01**, whose example list starts with "investigate fraud". The spec, README and submission form must use the new track name.
- **Dates: 15 Oct 2026, 12:01 AM IST to 18 Oct 2026, 11:59 PM IST.** In UTC that is 14 Oct 18:31 to 18 Oct 18:29, about 96 hours ([schedule](https://www.wemakedevs.org/hackathons/falkordb/schedule)). The saved copy's "September 2026" and "$10,000" are stale. The prize pool is now **$20,000**.
- **You can enter more than one track, and each track has its own prize.** "You may enter any or all of them, and you must name every track you are entering" ([rules #5](https://www.wemakedevs.org/hackathons/falkordb/rules)). The old saved rule ("Enter one track per submission") is superseded. If ShellTrace's persistent case memory is real (cross-session, per-tenant), it could also claim Track 02.
- **CRITICAL rule 8 risk: the repo already holds a working FalkorDB implementation dated before the event.** Commit `chore: establish ShellTrace baseline` (2026-10-01 19:56 +0530) adds `backend/shelltrace/{agent,queries,resolver,graph,exposure,api}.py`, tests and a full React frontend, about 7,650 lines. The FAQ says: *"The submission and its main FalkorDB implementation must be new work completed during the event."* Submitting this history as-is risks rejection. Recommendation: from 15 Oct 12:01 AM IST, start a fresh public repo and rewrite the FalkorDB layer (schema, Cypher, resolver, agent loop) during the event. Carry over only notes, the graph-model sketch, diagrams, and generic infrastructure (docker-compose, Makefile). Disclose this in the README.
- **TypeSafe is real, but the spec describes it wrongly.** "Jev" is the **model** (`jev-1.13.0`, alias `jev-latest`), not a judgment type. There are **three** primitives, not four: **Choice, Score, Noul**. Choice and Score return a value, per-option or per-level `probabilities`, and `confidence`. Noul returns a single 0-1 probability of "yes" and no separate confidence ([intro](https://docs.typesafe.ai/introduction)). It is not a hackathon partner. It is a closed, hosted, early-access paid API. TypeSafe's own docs say it is weak at **date comparison** and **multi-hop indirection**, which are exactly ShellTrace's core logic. Keep it optional, behind an interface, with a deterministic fallback. It must never decide temporal validity or paths.
- **No judging criteria, weights or judges are published for Graph Hacks.** Past WeMakeDevs events used about six equally weighted criteria: impact, creativity, technical excellence, best use of the sponsor, UX/safety, and presentation. One page said "The demo is scored as hard as the code" ([TrueForge](https://www.wemakedevs.org/hackathons/trueforge)). Plan for that rubric (UNVERIFIED for this event).
- **Rules may still change.** "These rules, the schedule, and the prize breakdown may be updated before the hackathon begins" ([rules note](https://www.wemakedevs.org/hackathons/falkordb/rules)). Re-check on 14-15 Oct.

---

## 1. Current hackathon facts

### 1.1 Identity, format, dates
- Name: **Graph Hacks: Context for AI Agents**, "Powered by FalkorDB". Tagline: "Agents are only as good as the context they work with... Build an agent that makes decisions you can trace." ([overview](https://www.wemakedevs.org/hackathons/falkordb))
- Online, worldwide, free to enter. Solo or up to 4 people. "Each participant may only be part of one team." ([rules #1](https://www.wemakedevs.org/hackathons/falkordb/rules))
- Schedule ([schedule](https://www.wemakedevs.org/hackathons/falkordb/schedule)):
  - **Registration: open now.** "Register yourself and add your teammates any time before submissions close."
  - **Hacking begins: 15 Oct, 12:01 AM IST.** "The event opens and submissions open with it."
  - **Submissions close: 18 Oct, 11:59 PM IST.** "Submit your repository, README, demo video, deployment, and project information before the deadline."
  - **Judging dates and results date are not published** (UNVERIFIED / not announced).
- The FAQ mentions a **"kickoff session"** ("The getting started guide and the kickoff session cover the basics"). No date or link is published yet (UNVERIFIED).
- Brief: "Build a working agent, or a group of agents, with FalkorDB as its context layer. The graph has to shape what the agent does, not sit on the side." "Work the graph has to do" lists: follow connections across data, remember across sessions, share state between agents, connect people/projects/decisions, **show the path behind an answer**.

### 1.2 Tracks (verbatim focus lists)
- **Track 01: Agents That Act on Connected Data.** "Build an agent that uses the graph to decide and act. It could investigate fraud, triage security findings, or work through a codebase." Key focus: **Multi-hop reasoning; Graph queries and algorithms as agent tools; Tool selection through MCP; Actions based on what the graph shows; Explainable results.**
- **Track 02: Agent Memory and Coordination.** Key focus: episodic, semantic and procedural memory; persistent conversation history; shared state and handoffs between agents; high-concurrency reads and writes; separate memory per user or tenant.
- **Track 03: Company Brain.** Key focus: knowledge from docs, tickets and chats in one graph; who owns and knows what; tracing decisions to their source; keeping knowledge current; answers with clear sources.

Every Track 01 bullet maps onto ShellTrace:
- shortest temporally-valid path → multi-hop reasoning
- WCC and shortest path exposed as tools → algorithms as agent tools
- MCP read-only tools → tool selection through MCP
- the CLEAR/EXPOSED verdict, watches and analyst-review routing → actions
- cited hops → explainable results

The README should mirror this list one-to-one.

### 1.3 Prizes and team policy ([overview](https://www.wemakedevs.org/hackathons/falkordb), [rules #14](https://www.wemakedevs.org/hackathons/falkordb/rules))
- Total pool **$20,000**, "One prize for each track, plus two side prizes. Every member of a winning team gets the prize."
- Track 01: **iPhone 18 Pro**. Track 02: **PS5 with GTA VI**. Track 03: **M6 Mac Mini**.
- Side prize: **AirPods 5** for the best blog post ("Write a blog post about your project"). Side prize: **T-shirt** for every member of the top 50 teams.
- Only the best project per track wins. There is no 2nd or 3rd place per track. A blog post is a cheap extra shot.
- IP: "Any intellectual property developed during the hackathon belongs to the participant or team that created it" (rule 15).

### 1.4 FAQ answers (verbatim, [overview#faq](https://www.wemakedevs.org/hackathons/falkordb))
- **Is FalkorDB mandatory?** "Yes. FalkorDB must be the primary graph database, and it must support a central part of the product."
- **Can I enter more than one track?** "Yes. You can enter one, two or all three, and each track has its own prize. As a guide: an agent that acts on data fits Track 01, one that remembers or coordinates fits Track 02, and one that works with company knowledge fits Track 03."
- **Can I continue an existing project?** "You may reuse general libraries, templates, and infrastructure. The submission and its main FalkorDB implementation must be new work completed during the event."
- **Can I use coding assistants?** "Yes. You remain responsible for the code, architecture, security, and correctness of the project, and you must be able to explain what was built and why."
- **Does the project need to be deployed?** "A live deployment is preferred. Projects that cannot be deployed must include complete local setup instructions and a working demo video."
- **Do I need graph database experience?** "No."
- **Can I use any programming language?** "Yes. You may use any language, framework, frontend, or deployment platform that works with your project."

### 1.5 Rules (full list, verbatim where load-bearing, [rules](https://www.wemakedevs.org/hackathons/falkordb/rules))
2. "FalkorDB must be the primary graph database in your project, and it must support a central part of what the product does."
3. "The graph has to do real work. A visualisation drawn on top of ordinary storage does not qualify: if the product still works once FalkorDB is taken out, the graph is decoration rather than the thing the product runs on."
4. Docker, self-hosted, and FalkorDB Cloud are all accepted.
5. Tracks as above. You must name every track you enter.
6. "Your project must use data you are allowed to use: public, synthetic, or your own. Do not load private, login-protected, paywalled, personal, or otherwise restricted information into your graph." (Note: OpenSanctions data includes named natural persons. Another lane should check whether "personal" excludes PEP/person records. Entity-only or synthetic persons is the safe choice.)
7. Dates as above.
8. **"The main coding and design work must begin after the hackathon starts. You may discuss ideas, create notes, sketch the graph model, or prepare diagrams beforehand."**
9. "You may use frameworks, open-source libraries, public APIs, templates, third-party tools, and publicly available datasets and assets. The original work completed during the hackathon will be judged."
10. Submission must include: "A public source-code repository; A README with setup instructions and your graph data model; The Cypher queries or graph algorithms the product depends on; A demo video showing the working project; A live deployment, or complete local setup instructions if it cannot be deployed; The track you are entering."
11. "AI coding assistants are allowed, but their use must be disclosed."
12. "Participants must understand the submitted code and be able to explain the graph model, the queries, the project architecture, and the technical decisions behind them."
13. "Projects that are entirely generated using AI without meaningful participant contribution, verification, or technical understanding may be rejected."
17. "Harassment, discrimination, plagiarism, or attempts to manipulate the judging process will result in disqualification."

### 1.6 What pre-event work is allowed
Allowed before 15 Oct 12:01 AM IST (rule 8 and FAQ):
- discussing ideas
- notes
- graph-model sketches
- diagrams
- general libraries, templates and infrastructure

Not allowed:
- "main coding and design work"
- the "main FalkorDB implementation"

The current repo history has a full ShellTrace backend and frontend committed on 1 Oct, plus a 544-line spec. The spec can probably pass as "notes" (it is a design artefact, so this is grey). The code clearly fails the FAQ's test.

Safe path:
1. Create a new public repo after the start time.
2. Copy in `docs/` as clearly labelled pre-event notes.
3. Rewrite `queries.py`, `resolver.py`, `agent.py`, the schema and the UI components during the window, with granular commits.
4. State in the README which files existed before the event.

Judges can see commit timestamps. Rule 12 means you will be asked to explain the code, so granular commits during the event help.

### 1.7 Resources listed ([resources](https://www.wemakedevs.org/hackathons/falkordb/resources))
- Start: [Getting started](https://docs.falkordb.com/getting-started/), [Docs](https://docs.falkordb.com), [FalkorDB GitHub](https://github.com/FalkorDB/FalkorDB), [GraphRAG SDK](https://github.com/FalkorDB/GraphRAG-SDK)
- Setup: [Docker / Compose](https://docs.falkordb.com/operations/docker), [FalkorDB Cloud](https://app.falkordb.cloud), [FalkorDB Browser](https://docs.falkordb.com/browser/)
- Querying: [Cypher](https://docs.falkordb.com/cypher/), [Clients](https://docs.falkordb.com/getting-started/clients), [Algorithms](https://docs.falkordb.com/algorithms/), [Integrations](https://docs.falkordb.com/integration/)
- Examples: [Community projects](https://www.falkordb.com/community-projects/)
- Videos: [Write effective Cypher queries](https://www.youtube.com/watch?v=emUQmEitSGY), [Advanced graph algorithms in FalkorDB](https://www.youtube.com/watch?v=aFkgUT0ubYY), [Graph and RAG talks playlist](https://www.youtube.com/playlist?list=PL_SzmSBoVe82kQKf5l_hDxu2yj7FEJDHB), [FalkorDB Cloud setup playlist](https://www.youtube.com/playlist?list=PL_SzmSBoVe82pWDPjSDH8QZP6kGxfVjut)
- Support: [FalkorDB Discord](https://discord.com/invite/Y2mMT9VdMy) ("open for the whole event"; team finding)
- The overview page also lists an "agent stack": **GraphRAG-SDK, QueryWeaver, MCP, Graphiti, Cognee, LangChain, LlamaIndex**. Algorithms named as agent tools: **Shortest path, PageRank, Centrality, Connected components, Community detection**. It also features **FalkorDB Browser** and **multigraph**: "one instance can hold thousands of isolated graphs, so each user, agent, or tenant gets its own."
- The `llms.txt` named in the footer ([wemakedevs.org/llms.txt](https://www.wemakedevs.org/llms.txt)) is a generic WeMakeDevs company file with nothing about this event.

### 1.8 Sponsors and partners
- FalkorDB is the only sponsor: "Graph Hacks is an independent developer hackathon organised by WeMakeDevs in collaboration with FalkorDB" ([rules](https://www.wemakedevs.org/hackathons/falkordb/rules)).
- **TypeSafe does not appear anywhere** in the overview, rules, resources or schedule HTML. I grepped the raw HTML for "typesafe" and found zero hits. WeMakeDevs' general partner list (Accomplish, Archestra, Cerebras, Cline, CodeRabbit, III, Kestra, Lingo, Meta, Portia, Tambo, Together AI) does not include it either ([llms.txt](https://www.wemakedevs.org/llms.txt)).

### 1.9 Changes from the saved copy (`rules.txt` / `about.txt` in repo)
| Item | Saved copy | Live (2026-10-05) |
|---|---|---|
| Name | Building Next-Gen RAG | Context for AI Agents |
| When | September 2026 | 15-18 Oct 2026 (IST) |
| Pool | $10,000 | $20,000 |
| Tracks | Investigation and Risk / Best Agentic AI Use Case / Best Use Case of the GraphRAG SDK | Agents That Act on Connected Data / Agent Memory and Coordination / Company Brain |
| Multi-track | "Enter one track per submission" | "any or all", name every track |
| Rule 8 | same text | same text |

---

## 2. TypeSafe check

**Verdict: real product, misdescribed in the spec, not connected to the hackathon.**

- **What it is.** TypeSafe AI, San Francisco, sells "System One" decision models. "Jev is TypeSafe's flagship model and the first System One model... Jev evaluates typed *questions* against a *state* and returns structured results directly. No text generation, no parsing." ([intro](https://docs.typesafe.ai/introduction), [typesafe.ai](https://typesafe.ai/))
  - Founder: Diogo Almeida (ex-OpenAI). Funding: $40M. Both per [The Register, 16 Sep 2026](https://www.theregister.com/ai-and-ml/2026/09/16/typesafe-ai-debuts-model-for-machines-that-plays-doom/5296711); the funding figure is not confirmed on TypeSafe's own site.
  - Launch: "available today in early access" ([launch post](https://typesafe.ai/blog/introducing-system-one-models-and-jev)). The page shows 28 Sep 2026; the press covered it on 15-16 Sep.
- **Primitives (exact):**
  - [Choice](https://docs.typesafe.ai/primitives/choice) returns `choice`, `probabilities` (one per option) and `confidence`.
  - [Score](https://docs.typesafe.ai/primitives/score) returns `score`, `probabilities` (one per level) and `confidence`.
  - [Noul](https://docs.typesafe.ai/primitives/noul) returns `noul`, a probability in 0-1 that the answer is yes. It has "no separate `confidence`... The probability already carries the uncertainty" ([confidence](https://docs.typesafe.ai/confidence)).
  - All three can be mixed in one call and are evaluated "in parallel and in isolation against the same state."
  - **"Jev" is the model name, not a primitive.** The spec's "Jev / Choice / Score / Noul" must become "model Jev; primitives Choice / Score / Noul".
- **Calibration claims.** Trained with "RLCD" (reinforcement learning for calibrated decisions). Docs caveat: "Calibration is measured across groups of predictions; it does not guarantee that an individual answer is correct" ([llms-full](https://docs.typesafe.ai/llms-full.txt), [AI primer](https://docs.typesafe.ai/introduction/machine-learning-primer)). I found no independent calibration benchmark. The Register calls the "hallucination-free" framing "not very useful as a comparison."
- **Model, price, limits** ([models](https://docs.typesafe.ai/models)):
  - `jev-1.13.0`, priced at $0.042 per million input tokens; output tokens are free.
  - Rate limits: 100K tokens/s and 80 requests/s. Docs say "Rate limits are adjusting dynamically... can change without notice."
  - Context: 64k tokens per request, of which 32k covers the state plus the longest question.
  - Text input only. "English is the primary training language"; CJK and other scripts are "handled but not equally well."
- **Latency:** "70ms-500ms" end to end ([launch post](https://typesafe.ai/blog/introducing-system-one-models-and-jev)).
- **SDKs:**
  - Python: `pip install typesafe-sdk`, with `TypeSafeClient` and `AsyncTypeSafeClient`.
  - JS/TS: `npm install @typesafe-ai/sdk`.
  - HTTP: `POST https://api.typesafe.ai/v1/systemone` with a Bearer key from [console.typesafe.ai](https://console.typesafe.ai/keys) ([quickstart](https://docs.typesafe.ai/introduction/quickstart), [SDKs](https://docs.typesafe.ai/sdk)).
  - There is also a LiteLLM pass-through ([LiteLLM](https://docs.litellm.ai/docs/pass_through/typesafe)) and a Spring AI integration ([Spring blog](https://spring.io/blog/2026/09/21/spring-ai-typesafe-structured-judgment/)).
- **License and openness.** Proprietary hosted model with no open weights. Governed by a Master Customer Agreement ([legal](https://docs.typesafe.ai/legal)). SDK licenses not checked (UNVERIFIED).
- **Free tier: UNVERIFIED.** No pricing page exists (`typesafe.ai/pricing` returns 404). Early-access and waitlist wording suggests an API key may not be instant.
- **Known weaknesses that hit ShellTrace directly** ([Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13), reviewed 2026-10-02):
  - "**Date and time comparison**... unreliable. Extract components; compare in code." Temporal validity of ownership edges must stay in Cypher.
  - "**Indirection**... multiple hops of reasoning costs accuracy." Path-finding must stay in FalkorDB.
  - "Math and Numbers": ownership-percentage thresholds belong in code.
  - "**Choice option order**... leans toward the option that comes first." Shuffle and re-ask if Choice is used for tool selection.
  - "Adversarial content... can move the answer."
  - Non-English weaker: sanctions aliases in transliterated scripts are exactly this case.
- **Where it legitimately fits.** TypeSafe has a [knowledge-graph entity alignment cookbook](https://docs.typesafe.ai/cookbooks/entity_alignment): "one Score question plus three companion Nouls that surface which fields disagree". Use it for **SAME_AS alias adjudication on candidate pairs that Cypher/WCC already proposed**. [Function calling](https://docs.typesafe.ai/cookbooks/function_calling) and [Skill suggestion](https://docs.typesafe.ai/cookbooks/skill_suggestion) patterns fit **MCP tool routing**. [Confidence-gated routing](https://docs.typesafe.ai/patterns/confidence-routing) fits sending low-confidence cases to analyst review.
- **Recommendation for the spec.**
  - Keep TypeSafe as an **optional adjudicator behind a `Judge` interface**, with a deterministic fallback (string or phonetic similarity plus identifier match) as the default for local setup. Judges reproducing locally will not have a key.
  - Never let it decide paths, dates or thresholds.
  - Name it correctly and disclose it as a third-party tool, which rule 9 allows.
  - It adds nothing to the "FalkorDB does real work" test (rule 3), so it must not become the headline.

---

## 3. Judge-craft intelligence

### 3.1 Judging criteria (not published for Graph Hacks)
Nothing about criteria, weights or judges appears on the four Graph Hacks pages (grepped raw HTML). The nearest WeMakeDevs precedents:
- **Cognee hackathon** (context/memory theme, also graph-adjacent) ([archive](https://archive.wemakedevs.org/hackathons/cognee)). Six criteria:
  1. Potential Impact
  2. Creativity & Innovation
  3. Technical Excellence
  4. Best Use of Cognee
  5. User Experience
  6. Presentation Quality ("clarity of demo, README, and submission")
- **TrueForge "Agent Harness Hackathon"**, Aug 2026 ([page](https://www.wemakedevs.org/hackathons/trueforge)). "Six criteria, weighted equally. The demo is scored as hard as the code." The criteria were impact, creativity, technical excellence, use of sponsor tools, **control and safety (human approval gates)**, and presentation. On prior work: "the build has to happen during the week."
- Older WeMakeDevs events (e.g. [HackFrost](https://archive.wemakedevs.org/hackathons/hackfrost24)) used impact, creativity, learning, implementation and aesthetics, plus "Best Documentation" style category prizes.

Expected rubric (UNVERIFIED): impact, originality, technical depth, **centrality of FalkorDB**, UX/safety, and demo/README quality, roughly equally weighted.

### 3.2 Judges
None announced (UNVERIFIED). Expect FalkorDB staff and DevRel, plus WeMakeDevs (Kunal Kushwaha's team).

### 3.3 What FalkorDB emphasises publicly
- **Speed inside the agent loop.** "Traversals are fast enough to run on every step of an agent loop" ([overview](https://www.wemakedevs.org/hackathons/falkordb)). Their blog claims sub-millisecond traversals and "496x faster... P99" benchmarks ([blog: Graph Database AI Agents](https://www.falkordb.com/blog/graph-database-ai-agents/); search snippet, figures UNVERIFIED).
- **Multi-tenancy and multigraph.** "one graph per user or tenant... without running separate deployments."
- **Agent-memory ecosystem.** Graphiti and its MCP server ([docs](https://docs.falkordb.com/agentic-memory/graphiti-mcp-server.html), [blog](https://www.falkordb.com/blog/mcp-knowledge-graph-graphiti-falkordb/)), Cognee, GraphRAG-SDK, QueryWeaver, and an MCP integration ([blog](https://www.falkordb.com/blog/mcp-integration-falkordb-graphrag/)). Also temporal knowledge graphs ([blog](https://www.falkordb.com/blog/building-temporal-knowledge-graphs-graphiti/)).
- **Graph algorithms as agent tools** and **FalkorDB Browser** for inspecting the model.
- Score-winning moves for ShellTrace:
  - show measured per-hop query latency in the UI
  - keep one graph per case or tenant via multigraph
  - expose the algorithms as MCP tools
  - include a Browser screenshot of the data model in the README

### 3.4 Promotion and early competitors
- WeMakeDevs is pushing the tracks on X: Company Brain ([post](https://x.com/WeMakeDevs/status/2106258783072891069)) and Memory ([post](https://x.com/WeMakeDevs/status/2106688880842096755)). It is also listed in roundups ([dev.to radar #19](https://dev.to/devengers/dev-opportunity-radar-19-hacktoberfest-20k-ai-agent-hackathon-and-pear-prime-2027-291n), [brabble](https://brabble.ai/blog/wemakedevs-hackathon)).
- A public pre-event repo was indexed: **`Hydra-Of-Malice/FalkorDB`**, "Minutes: shared, time-aware memory for agent teams on FalkorDB. Graph Hacks 2026 (Tracks 2 and 3)". It returns 404 as of 2026-10-05, so it was deleted or made private. Others are prototyping early, and some seem aware of rule 8.
- I found no public Track 01 beneficial-ownership or sanctions entries (search coverage was limited).

### 3.5 Likely Track 01 competitors and how to stand out
The page's own prompts say "investigate fraud, triage security findings, or work through a codebase", and its first "why graphs" question is "Which accounts are linked to this flagged transaction?". Expect many projects in four groups:
- **Fraud rings / money mules** on synthetic transactions (PaySim-style), using WCC or community detection.
- **AML transaction tracing.**
- **Security triage**: CVE/SBOM dependency graphs and attack paths.
- **Codebase agents**: FalkorDB already ships code-graph tooling (UNVERIFIED that judges will discount it).

How ShellTrace stands out:
1. **Real public data, not synthetic**: GLEIF Level 2 plus OpenSanctions. Plus an **evaluation against ground truth** (`sanction.control`). Almost no hackathon project reports precision/recall.
2. **Temporal validity** on edges (Cypher-enforced) and **honest abstention** ("CLEAR within N hops"). This is rare and fits "explainable results".
3. **Live CLEAR→EXPOSED flip** when a designation is injected. This is the demo moment; open the video with it.
4. **MCP tool selection** shown explicitly. This is a named Track 01 focus that most fraud demos will skip.
5. **Human-in-the-loop action** (analyst review, watches). This maps to "Actions based on what the graph shows" and to the control/safety criterion seen in TrueForge.
6. **Packaging**: live deployment (FalkorDB Cloud plus a host), a README with the data model diagram, a Cypher appendix, an AI-disclosure section (AIDLC logs), and a blog post for the AirPods side prize.
7. Optionally enter **Track 02** too, only if case memory truly persists across sessions with per-tenant graphs. Otherwise stay focused on Track 01.
