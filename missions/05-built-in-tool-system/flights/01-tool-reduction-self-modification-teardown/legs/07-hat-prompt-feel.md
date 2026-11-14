# Leg: 07-hat-prompt-feel

**Status**: completed
**Flight**: [Tool Reduction & Self-Modification Teardown](../flight.md)

## Objective

Guided HAT session: operator chats with the agent against the new base prompt and walks through the six verification probes (a-f) listed in the flight spec's L7. Inline-fix any voice or copy issues that surface; divert any structural ones to a follow-up. Mandatory — F1 cannot land without it.

## Context

L7 is the only leg in this flight that exercises the post-rip runtime against a real LLM. The default unit suite, browser suite, and Reviewer pass all confirmed source-level coherence. L7 confirms behavioral coherence — does the agent actually behave like the post-rip codebase intends?

L1-L6 are committed (`dc57080`). The PR is open as a draft (#19). After L7 lands, the flight transitions to `landed` and the PR moves from draft → ready-for-review.

## Inputs

- Branch `flight/01-tool-reduction-self-modification-teardown` checked out, committed at `dc57080`.
- A running instance of the-one against an Ollama-backed (or other LLM-backed) provider. The operator runs `make rebuild` to build the post-L1-L6 image and start the container.
- Operator has access to the chat UI (browser at `http://localhost:8484`), the admin System page, and the Studio agent editor.

## Outputs

After this leg:
- Operator has confirmed the new agent voice matches the post-rip identity (no ghost-tool hallucination, no self-modification framing).
- Operator has confirmed the three core capabilities work: file read, shell execution, web search.
- Operator has confirmed the admin Base Prompt section renders correctly and Studio Tools tab shows 3 categories × 7 tools.
- Any voice/copy issues surfaced have been inline-fixed (small follow-up commits on the same branch).
- Any structural issues have been diverted to follow-up work (recorded in the flight log Anomalies section).
- L7 leg status `landed` (then `completed` after final commit).
- Flight status `landed`.
- L7 checkbox in flight.md checked.
- Flight checkbox in mission.md checked.
- PR moved from draft → ready-for-review.

## Acceptance Criteria (Verification Probes)

- [ ] **(a) No ghost-tool hallucination**: ask the agent "list your tools". None of the seven removed names (`self_deploy`, `rollback`, `restart`, `run_tests`, `git`, `memory`, `mission_control`) appears in the response.
- [ ] **(b) Voice and identity feel right**: open a chat, send a few generic messages ("hi", "what can you do?", "what's your name?"). Tone is direct, concise, no filler openings, no self-modification framing. Identity is "the-one", general-purpose. Operator's subjective check.
- [ ] **(c) Filesystem tool works**: ask the agent to read a file (e.g., `pyproject.toml` from inside `/app/`). Agent uses `read_file`, returns the file's contents.
- [ ] **(d) Shell tool works**: ask the agent to run a shell command (e.g., `echo hello` or `ls /app`). Agent uses `shell`, returns stdout.
- [ ] **(e) Web tool works**: ask the agent to search the web (e.g., "search the web for 'fastapi documentation'"). Agent uses `web_search`, returns results.
- [ ] **(f) Admin Base Prompt section renders**: open the chat UI, navigate to Admin → System. Verify a "Base Prompt" section appears (read-only `<pre>` block), its content matches the `BASE_PROMPT` constant. The Concourse CI section is NOT present.
- [ ] **(g) Studio Tools tab structure**: open Studio, select the default agent, click the Tools tab. Verify 3 categories visible (Filesystem, Execution, Web) with 7 tools total. No "System" banner.
- [ ] **(h) AIAT live tests pass** (optional but recommended): operator runs `pytest -m live tests/test_aiat.py` against the running instance. All 6 surviving tests should pass.

## Verification Steps (Step-by-Step Guidance)

The Flight Director walks the operator through each probe one at a time, waits for the operator's report, fixes issues inline if needed, then proceeds.

### Step 0: Build and start

Operator runs:
```bash
cd ~/projects/the-one
make rebuild
```

Wait for the container to come up (`make logs` to verify; `/api/info` should return 200).

### Step 1: Probe (b) — open chat, generic interaction

- Operator opens `http://localhost:8484/`, switches to the Chat area.
- Operator sends: "Hi, what can you do?"
- Operator reports: response text, any oddness (filler, self-modification framing, mention of removed tools).
- Flight Director assessment: voice/identity feel right? If not, propose a redline to BASE_PROMPT and inline-commit.

### Step 2: Probe (a) — tool list

- Operator sends: "List your tools."
- Operator reports: full response.
- Flight Director assessment: any of the seven removed names appear? If yes — investigate (could be hallucination, could be a stale tool description leak). Inline-fix if it's BASE_PROMPT or tool-description content; divert if it's a runtime issue.

### Step 3: Probe (c) — file read

- Operator sends: "Read the file /app/pyproject.toml."
- Operator reports: did the agent call `read_file`? Did it return file contents?
- Flight Director assessment: read_file works against the post-L4 path. If it fails — could be path-scope issue (F2 will add path scoping but L1-L6 didn't change read_file behavior). Investigate.

### Step 4: Probe (d) — shell

- Operator sends: "Run `ls /app` using the shell tool."
- Operator reports: did the agent call `shell`? Did it return file listing?

### Step 5: Probe (e) — web search

- Operator sends: "Search the web for 'fastapi documentation'."
- Operator reports: did the agent call `web_search`? Did it return results?

### Step 6: Probe (f) — admin Base Prompt section

- Operator navigates: `http://localhost:8484/#admin/system`.
- Operator reports: is the Base Prompt section visible? Does it show the prompt content? Is the Concourse CI section gone?

### Step 7: Probe (g) — Studio Tools tab

- Operator navigates: Studio → select default agent → Tools tab.
- Operator reports: how many categories visible? How many tools total? Is "System" banner gone? Is `run_tests` absent from Execution?

### Step 8: Probe (h) — AIAT live tests (optional)

- Operator runs: `pytest -m live tests/test_aiat.py --tb=short`.
- Operator reports: pass count, failures.
- Flight Director assessment: all 6 surviving tests should pass. Failures might surface real issues that the unit/browser suites missed.

### Step 9: Final commit

- If any inline fixes were applied during steps 1-8, commit them with a descriptive message.
- Update L7 leg status `landed`. Check off L7 in flight.md. Update flight `**Status**: in-flight` → `landed`. Check off flight in mission.md.
- Mark PR ready for review (`gh pr ready 19`).
- Signal `[COMPLETE:flight]`.

## Edge Cases

- **Operator runs into a setup issue (Ollama not running, etc.)**: pause HAT, fix the setup, resume.
- **Voice issue surfaces (e.g., agent says "I'm a self-modifying personal assistant")**: redline BASE_PROMPT inline, rebuild, re-test.
- **Tool fails (e.g., read_file returns "no such file")**: investigate. Could be a path issue (post-L4 the working dir / scope changed) or an LLM-side issue. Most likely a prompt issue if the tool itself works in unit tests.
- **Browser-test regression surfaces during HAT**: inline-fix or divert. The browser suite already passed cleanly at L6 — any regression here would be from a step-2-onward inline-fix.
- **AIAT failure**: investigate. The 6 surviving tests should pass against the post-L4 runtime. A failure indicates the L4 path-fix didn't take or a tool's behavior changed unexpectedly.
- **No issues at all**: ideal outcome — proceed to step 9.

## Files Affected

- Possibly `the_one/agent/config.py` (BASE_PROMPT redlines)
- Possibly other source files if HAT surfaces a regression
- `missions/05-built-in-tool-system/flights/01-tool-reduction-self-modification-teardown/flight-log.md` — L7 progress entry, any anomalies
- `missions/05-built-in-tool-system/flights/01-tool-reduction-self-modification-teardown/legs/07-hat-prompt-feel.md` — status updates
- `missions/05-built-in-tool-system/flights/01-tool-reduction-self-modification-teardown/flight.md` — status `in-flight` → `landed`, L7 checkbox, last-checkpoint checkbox
- `missions/05-built-in-tool-system/mission.md` — flight checkbox

---

## Post-Completion Checklist

- [ ] All 8 verification probes pass (or have a documented divert)
- [ ] Any inline fixes applied are committed
- [ ] Update flight-log.md with L7 progress entry
- [ ] Set L7 leg status to `completed` (in this file's header)
- [ ] Check off L7 in flight.md
- [ ] Update flight `**Status**` from `in-flight` to `landed`
- [ ] Check off the seventh checkpoint (HAT pass) in flight.md
- [ ] Check off the flight in mission.md
- [ ] `gh pr ready 19` to move the PR from draft to ready-for-review
- [ ] Signal `[COMPLETE:flight]`
