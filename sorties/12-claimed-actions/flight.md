# Sortie: Claimed actions

**Status**: planning

## Charter

### Outcome
A small local model with its tools up front calls the tool instead of claiming it did, and the prompt evals catch the claims it still makes.

### Why Now
Sortie 11 put every tool schema in front of small models from the first call (tool exposure). That fixed tool use for `qwen3:4b-instruct`: `kb-find` and `kb-answer` went from 1/20 to 20/20 and `tool-discovery` from 6/20 to 20/20. But `notes-as-told` fell from 19/20 to 14/20.
- In the six failures the model made no tool call and replied as if it had saved the note, for example `Saved note: "…"`. Four of the six used the phrasing "Please remember this: …".
- The `notes-as-told-claims` cell flagged only 1 of the 6 false claims, because its first-person patterns miss result-style wording.
- The operator accepted the regression as a recorded exception at landing (`sorties/11-tool-exposure-for-small-models/flight-log.md`, Decisions). This sortie is the follow-up the sortie 11 debrief named as recommendation 1.
- The 2026-11-05 benchmark had already seen the same shape: `qwen3:4b-instruct` claimed a planted save it never made in 10 to 14 of 20 runs where it read the page.

### Success Criteria
- [ ] `qwen3-4b` `notes-as-told` is at least 19/20, with sortie 11's gains held: `kb-find`, `kb-answer` and `tool-discovery` each at 0.9 or more.
- [ ] The claims cells flag result-style false claims (`Saved note: "…"`). Proof: the six failing sortie 11 transcripts (`evals/runs/s11-cand-main`, `notes-as-told/qwen3-4b/f0p0`, `f1p0`, `f1p3`, `f3p0`, `f4p0`, `f4p3`).
- [ ] Decided and recorded: the claimed-action guard is either a runtime check or a gated eval cell.
- [ ] New same-prompt baselines for the changed scenario set are committed.

### Constraints
- No change to the frozen `the_one/agent/core.py` without the owner's approval.
- A platform prompt change lands with an eval comparison against the current baseline, including its token cost (`CLAUDE.md` "Prompt evals").
- Prompt wording is screened at fact 0 only, then compared once at full width (Mission 30's screening rule).
- A changed claim pattern moves the scenarios fingerprint, so it needs a same-prompt re-baseline before the product comparison.
- Out of scope: secrets stored in notes (a separate design call) and the Ollama wire (sortie 13).

---

## Pre-Flight

*(Flight design not started. Run `/mission-control:sortie` design for sortie 12 to continue.)*

### Inputs carried from the sortie 11 debrief
- Run an n=5 sentinel on the tool-calling hold cells (`notes-as-told`, `notes-proactive`) for the smallest model before any n=20 set.
- Review and commit product code before each quota-heavy set of runs (sortie 11 DD14, now the operator's standard for eval-driven flights).
- At temperature 0, n=20 measures about 20 distinct prompts, not 20 independent trials. Group failures by phrasing and fact.
- At baseline time, decide the reading for any cell that already fails its own bar.
