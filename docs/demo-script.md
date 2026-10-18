# ShellTrace: 3-minute recording script

Record at 1920×1080, browser zoom 80–90%, microphone on, notifications off.
The target timeline is 180 seconds. Speak naturally at about 125 words/minute.
Keep the cursor visible. Use the freshly started local build for these fixes.
The public deployment hasn't been updated by this work and still serves the
synthetic demo. Say that the real-data segment runs locally.

## Start a clean take

Docker must be running. The dedicated recording database on this machine is
`shelltrace-recording-20261018` on port 6386. From the repository root:

```powershell
docker start shelltrace-recording-20261018
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-demo.ps1 -Agent
```

On another machine, create the database first:

```powershell
docker run -d --name shelltrace-recording -p 127.0.0.1:6386:6379 falkordb/falkordb:6.0.2
python -m pip install -e './backend[dev]'
npm --prefix frontend ci
```

`start-demo.ps1` prints the recording URL with a fresh `?ws=take_...`, a new
synthetic template, and log paths. Use that exact URL for every synthetic tab.
The defaults are API port 8014 and UI port 5183. If those ports are occupied,
provide different `-ApiPort` and `-UiPort` values. The script doesn't stop
existing processes. Keep the original terminal output for the process IDs.

Groq credentials belong only in ignored `backend/.env`. The launcher prints the
configured model, never the keys. Without working keys, omit `-Agent`, use
Playbook, and use the alternative narration below.

Before each retake, stop only the API/UI processes for the previous take and
start a new take. A designation updates that take's template, so reusing it can
make the watch case exposed before you start. A new workspace under the same
old template is insufficient.

## Prepare these tabs before recording

Use Playbook for all prepared cases. Keep OFAC, EU and UK selected.

| Tab | Prepare | Expected visible state |
| --- | --- | --- |
| A: hook + agent | Search `Nord Harbor`, select Nord Harbor Logistics Ltd, date `2024-01-01`, Run, then Run name screen | Name screen: no hit; validated EXPOSED; ownership proof |
| B: regime comparison | Search `Birch`, select Birch Marine Services Ltd, date `2024-01-01`, Run | OFAC/EU BLOCKED, UK NOT_BLOCKED |
| C: date change | Search `Larch`, select Larch Metals AG, date `2022-06-01`, Run | EXPOSED; time slider includes `2023-01-01` |
| D: watch | Search `Aegean Fresh Produce`, date `2024-03-01`, Run | CLEAR_WITHIN_BOUNDS; watch unchecked; no injected Nikos designation |
| E: authentic data | Open `http://127.0.0.1:8012/?ws=real_demo_1018`, search LEI `635400I6H6CSZ39WIN49`, select GTLK Europe Capital, date `2026-10-15`, Run, Draft report, click its designation citation | Local real snapshot; source record; date basis is first_seen approximation |
| F: evaluation | Open the fresh take's URL followed by `#/eval` | Golden suite and schema-v2 E3 results |
| G: uncertainty | Search `Dune`, select Dune Logistics FZE, date `2024-01-01`, Run | ESCALATE, uncertain ownership interval |
| H: repository | Open the public repository, then `backend/shelltrace/graph/ownership.py` | `ROUND_CYPHER`, `SCOPE_STEP`, `SEEDS` available to show |

Tab E requires the corrected real API to be running locally. On this machine
it uses graph `st_facts_real_os_20261015_corrected`, port 6384, and API port 8012.
See [the real-data runbook](real-data-evaluation.md) to start it elsewhere.
Don't start a second API on an occupied port.

Rehearse Tab A once in a different take. The verified Groq run returned a
proposal and validated EXPOSED in 9.03 seconds with no fallback. Network times
vary; allow 15 seconds in the script. If it exceeds the slot, let the actual
run finish and record a new take, or use the honest Playbook alternative.
Don't edit out a fallback and present the result as an uninterrupted agent run.
The timeline appears when the request completes; it isn't a live token stream.

## Exact timeline and narration

| Time | Show / click | Say |
| --- | --- | --- |
| 0:00–0:08 | Tab A. Point to “Name screen: no hit”, then EXPOSED. | “This company passes a name screen, but its owners still expose it. This is a disclosed synthetic case.” |
| 0:08–0:17 | Keep the company and proof visible. | “I built ShellTrace for analysts who need to explain sanctions exposure through ownership, across dates and jurisdictions.” |
| 0:17–0:32 | Select Agent, click Run investigation. Let it finish on camera. | “I'll rerun this with the Groq agent. It investigates through read-only MCP tools. The timeline records those calls, and deterministic checks validate the result.” |
| 0:32–0:43 | Point to tool calls, actor/model, proposal and validated badge. | “Here are the actual tool calls, their inputs, and evidence keys. The model's proposal stays separate from the authorized outcome.” |
| 0:43–0:55 | Click a proof edge, show the evidence locker. Keep this proof sequence uninterrupted. | “This proof crosses companies and an accepted alias. Clicking a record gives me its source, dates and licence.” |
| 0:55–1:09 | Tab B. Show all 3 rule-pack verdicts. | “Now the same fifty-percent chain. Under the modeled OFAC rule it propagates blocking. The UK threshold gives a different result. Both are shown together.” |
| 1:09–1:20 | Tab C. Move Investigation date slider to `2023-01-01`. Wait for CLEAR_WITHIN_BOUNDS. | “Dates change the answer too. Move past this synthetic delisting date, and the case reruns within the same explicit bounds.” |
| 1:20–1:32 | Tab D. Check Watch this case. Expand Demo: inject designation. Search/select `Nikos`. Keep defaults OFAC, SDN (demo), `2024-03-15`, Demo injection. Click Inject designation. | “A clearance can go stale. I'll watch this case, then inject a disclosed synthetic designation for Nikos.” |
| 1:32–1:44 | Show the toast: 2 entities newly blocked, 1 watched case changed. Open Notifications. | “The graph finds two newly blocked companies and rechecks the watched case. This notification shows the clearance changing to exposure.” |
| 1:44–1:54 | Click View diff. Show EXPOSED and the new proof. | “I can open the updated case and inspect the new proof, rather than reconstructing the change by hand.” |
| 1:54–2:10 | Tab E. Show real snapshot, source attribution and first_seen date explanation. | “This second workspace uses authentic OpenSanctions and GLEIF data, loaded locally. Here are the source records. GLEIF consolidation stays separate from legal ownership, and observation dates are labelled.” |
| 2:10–2:25 | Tab F. Show 24/24 golden result, then E3. | “The synthetic suite checks twenty-four planted cases. The real-data evaluation hides each subject's own listing and measures graph tools against name screening.” |
| 2:25–2:38 | Point to E3 date-basis column and small-n counts. | “Our current slice gives seven eligible positives: five using observation-date approximations, two using source dates. That's a small sample, so I show counts.” |
| 2:38–2:49 | Tab G. Point to ESCALATE and the interval. | “When percentages are missing, ShellTrace shows uncertainty and escalates the case. The analyst can see what evidence is still needed.” |
| 2:49–3:00 | Tab H. Show the Cypher file, then repository home. | “FalkorDB powers the investigation, case memory and change traversal. The repository includes the Cypher, tests and recordings. ShellTrace supports investigation; it doesn't provide legal advice.” |

For a Playbook-only recording, replace the 0:17–0:32 narration with:
“I'll rerun the reproducible playbook. It uses the same read-only MCP tools and
policy checks as agent mode. The timeline records the investigation.”
At 0:32 say “The timeline records the investigation and its validated outcome.”
Don't claim that a model selected tools during that take.

## Final recording checks

- Record the browser and your voice, not terminals containing `.env` values.
- Keep real and synthetic segments visibly labelled. A real company's own
  designation is not evidence that an unlisted subsidiary was discovered.
- Use the measured counts above; don't say “100% accurate” or “production-ready”.
- The real slice has 32,169 company/vessel nodes but only 51 loaded GLEIF links.
  The 4,307 parsed relationship rows aren't the number loaded into this graph.
- Optional end card: “Track 01 · Built with AI coding assistance · Sources and limitations in repository”.
- Upload the finished video to YouTube as public or unlisted. Open the link in
  an incognito window before pasting it into the submission. Repository WebM
  recordings alone don't satisfy the form's YouTube-link requirement.
