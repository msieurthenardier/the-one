# Leg: 02-prompt-layering-and-base-rewrite

**Status**: completed
**Flight**: [Tool Reduction & Self-Modification Teardown](../flight.md)

## Objective

Establish the layered-prompt model in `AgentConfig.get_system_prompt()` (additive composition: base prompt always applies; per-agent `system_prompt`, when non-empty, is appended via a `\n\n---\n\n` separator), rename the constant `DEFAULT_SYSTEM_PROMPT` → `BASE_PROMPT`, drop the `system_prompt` default value from `Agent.__init__`'s signature so callers must pass an explicit prompt, replace the constant's content with a general-purpose personal-assistant base prompt that contains no self-modification / deployment / methodology / `/workspace` / mission-control language, and update every test call site that relied on the removed default.

## Context

L2 establishes the prompt-layer architecture the rest of the mission builds on. After L2:
- `BASE_PROMPT` is the foundational layer — identity, tone, turn semantics (including the `continue` signal), tool-use disposition, light generic tool guidance.
- `AgentConfig.system_prompt` (when non-empty) **adds to** the base prompt rather than replacing it. No escape hatch / replace-mode flag (per Decision 4).
- `Agent.__init__` no longer has a `system_prompt` default, so the only production resolution path is `AgentConfig.get_system_prompt()`. This closes the bypass that previously let direct `Agent(...)` construction silently inherit `DEFAULT_SYSTEM_PROMPT`.

L1 is landed (uncommitted). L2 commits with L1 in the post-L6 batch — per the flight Technical Approach inter-leg coherence note, L1+L2 are treated as a single observable release because L1 deletes tools the prompt mentions, and L2 rewrites the prompt to no longer mention them.

**Codebase audit findings (2026-04-28, post-L1):**

- `the_one/agent/config.py` line 7: `DEFAULT_SYSTEM_PROMPT` constant — full self-modification narrative, mentions `restart`, `run_tests`, `git`, `self_deploy`, `rollback`, references `/workspace`, `/app`, `/mission-control/docs/`, the methodology framework. All of this goes.
- `the_one/agent/config.py` line 101-103: `get_system_prompt()` returns `self.system_prompt if self.system_prompt else DEFAULT_SYSTEM_PROMPT`. New behavior: always include the base; append `system_prompt` if set.
- `the_one/agent/core.py` line 5: `from the_one.agent.config import DEFAULT_SYSTEM_PROMPT`. After rename, this import goes (no callers — `Agent.__init__` no longer uses it as a default).
- `the_one/agent/core.py` line 33-44: `Agent.__init__(self, llm, tools, system_prompt: str = DEFAULT_SYSTEM_PROMPT, max_iterations: int = 20)`. The default disappears; `system_prompt` becomes a required positional/keyword argument.
- `the_one/agent/core.py` line 133-134: `reset(self)` re-uses `self.system_prompt`. No change needed — instance attribute is set in `__init__`.

**Critical design correction** (refines flight spec Decision 4):

The flight spec says: *"Two test files do this: `tests/test_auto_load.py:99` and `tests/test_streaming.py:268`. L2 strategy: drop the default value from `Agent.__init__`'s signature... and update those two test sites."*

A fresh `grep -n "Agent(" tests/` audit shows the spec inverted the reading. Those two cited sites **already pass explicit prompts** (`system_prompt="test"` and `system_prompt="sys"` respectively); they don't rely on the default. The sites that **actually** rely on the default are six in `tests/test_agent.py`:

| File:line | Current call shape |
|-----------|--------------------|
| `tests/test_agent.py:59` | `Agent(llm=llm, tools=_make_registry())` |
| `tests/test_agent.py:78` | `Agent(llm=llm, tools=_make_registry(tool_a))` |
| `tests/test_agent.py:105` | `Agent(llm=llm, tools=_make_registry(tool_a))` |
| `tests/test_agent.py:135` | `Agent(llm=llm, tools=_make_registry(tool_a), max_iterations=2)` |
| `tests/test_agent.py:159` | `Agent(llm=llm, tools=_make_registry(bad))` |
| `tests/test_agent.py:173` | `Agent(llm=llm, tools=_make_registry())` |

Sites that already pass an explicit prompt (verified — no edits needed in L2):
- `tests/test_auto_load.py:99` (`system_prompt="test"`)
- `tests/test_streaming.py:268, 282, 300, 468` (`system_prompt="sys"`)
- `tests/test_session_lifecycle.py:39` (`system_prompt="You are helpful"`)
- `the_one/agent/factory.py:112` (production — passes resolved `system_prompt`)

**Refined L2 strategy**: drop the default; update the six `test_agent.py` sites with `system_prompt="test"` (matching the convention in `test_auto_load.py:99`). Record this design correction in the flight log Deviations.

**Other audit notes:**
- `the_one/agent/__init__.py` does not re-export `DEFAULT_SYSTEM_PROMPT`. No re-export update needed.
- `tests/test_config.py` lines 5, 105, 117-122 import and assert on `DEFAULT_SYSTEM_PROMPT`. After L2's rename, these all become `BASE_PROMPT`. The `TestGetSystemPrompt::test_empty_returns_default` assertion `cfg.get_system_prompt() == DEFAULT_SYSTEM_PROMPT` is correct under the new composition rule (when `system_prompt == ""`, `get_system_prompt()` returns `BASE_PROMPT` alone). The `test_custom_prompt_returned` assertion (`cfg.get_system_prompt() == "Custom prompt."`) is **wrong** under the new rule — must update to assert the additive composition.
- `the_one/agents.md:57` references `DEFAULT_SYSTEM_PROMPT`. This is a `*.md` narrative file; L5's UI/docs cleanup leg will rewrite it. Out of L2 scope. L2's verification greps must use `--glob '!*.md'` (consistent with L1's pattern).
- `CLAUDE.md` does not reference `DEFAULT_SYSTEM_PROMPT` directly (verified). The Self-Deployment / Configuration / What-This-Is sections that L5 will edit do not name the constant.
- The base-prompt visibility surface in admin (Decision 7) is L5's job, not L2's. L2 only delivers the constant; L5 surfaces it via `/api/info` (or new endpoint) and renders it in `admin/system-page.js`.

## Inputs

- L1 landed (uncommitted): `behaviors.py` gone, 7 tools removed, `direct_actions` field gone, `CONTINUE_SCHEMA` inlined into `core.py`.
- `DEFAULT_SYSTEM_PROMPT` constant present in `the_one/agent/config.py` with self-modification content.
- `the_one/agent/core.py` imports `DEFAULT_SYSTEM_PROMPT` for the `Agent.__init__` default.
- Default unit test suite has 394 passing + 1 pre-existing red (`test_token_definitions.py::test_every_var_reference_is_defined`, unrelated to F1).

## Outputs

After this leg:
- `BASE_PROMPT` constant exists in `the_one/agent/config.py` with new content (no self-modification / deployment / methodology / `/workspace` language).
- `DEFAULT_SYSTEM_PROMPT` no longer exists anywhere in the codebase (renamed everywhere).
- `AgentConfig.get_system_prompt()` returns `BASE_PROMPT` when `system_prompt == ""`, else `f"{BASE_PROMPT}\n\n---\n\n{self.system_prompt}"`.
- `Agent.__init__` no longer has `system_prompt: str = DEFAULT_SYSTEM_PROMPT`; the parameter has no default.
- `the_one/agent/core.py` no longer imports `DEFAULT_SYSTEM_PROMPT` (or `BASE_PROMPT` — `core.py` doesn't need it post-L2).
- Six `tests/test_agent.py` `Agent(...)` constructions updated with `system_prompt="test"`.
- `tests/test_config.py` updated: import renamed, `test_empty_returns_default` updated to reference `BASE_PROMPT`, `test_custom_prompt_returned` updated to assert additive composition, `TestDefaultSystemPrompt` class renamed to `TestBasePrompt` with assertion variable rename.
- Default unit test suite (`pytest tests/ --ignore=tests/browser`) green (modulo the pre-existing CSS anomaly).
- No commit yet — agentic-workflow defers commit to post-L6.

## Acceptance Criteria

- [ ] `the_one/agent/config.py` defines `BASE_PROMPT` (not `DEFAULT_SYSTEM_PROMPT`); content draft approved by user.
- [ ] `BASE_PROMPT` content does NOT mention `restart`, `run_tests`, `git` (the tool, word-boundary check), `self_deploy`, `rollback`, `memory` (the tool, word-boundary check), `mission_control`, `autopilot`, `/workspace`, `/mission-control`, paths starting with `/app/`, "Mission Control methodology", "Mission:", "Flight:", "Leg:" (in the methodology sense), "self-modification", "self-deploy", "deploy yourself", or "rebuild image".
- [ ] `BASE_PROMPT` content DOES mention the `continue` tool / signal explicitly (turn semantics) and uses the word "tool" in the generic sense (positive coverage check).
- [ ] `BASE_PROMPT` length is in the band 180-450 words (flight-spec target: ~200-400; slack on both ends covers the gate).
- [ ] `AgentConfig.get_system_prompt()` returns `BASE_PROMPT` when `self.system_prompt == ""`, and returns `f"{BASE_PROMPT}\n\n---\n\n{self.system_prompt}"` when non-empty.
- [ ] `Agent.__init__` signature does not include a default value for `system_prompt`. Calling `Agent(llm=..., tools=...)` without passing `system_prompt` raises a `TypeError`.
- [ ] `the_one/agent/core.py` does not import `DEFAULT_SYSTEM_PROMPT` or `BASE_PROMPT`.
- [ ] `rg -n "DEFAULT_SYSTEM_PROMPT" the_one/ tests/ --glob '!*.md'` returns no matches. (`agents.md:57` mention is L5's to edit.)
- [ ] All six `tests/test_agent.py` `Agent(...)` construction sites pass `system_prompt="test"`.
- [ ] `tests/test_config.py` no longer references `DEFAULT_SYSTEM_PROMPT`. `TestDefaultSystemPrompt` is renamed to `TestBasePrompt` and asserts on `BASE_PROMPT`. `test_custom_prompt_returned` is renamed to `test_custom_prompt_appended` (semantic shift — git-blame readability) and asserts the additive composition (not bare `"Custom prompt."`). The comment header at line ~113 (`# DEFAULT_SYSTEM_PROMPT validation`) is updated to `# BASE_PROMPT validation`.
- [ ] `python -c "from the_one.agent.config import BASE_PROMPT, AgentConfig; cfg = AgentConfig(name='t'); assert cfg.get_system_prompt() == BASE_PROMPT; cfg2 = AgentConfig(name='t2', system_prompt='Persona X'); assert cfg2.get_system_prompt() == BASE_PROMPT + '\n\n---\n\nPersona X'; print('OK')"` prints `OK`.
- [ ] `python -m pytest tests/ --tb=short -q --ignore=tests/browser` exits 0 (modulo the pre-existing CSS anomaly that L1 also tolerated).
- [ ] Working tree on branch `flight/01-tool-reduction-self-modification-teardown`; **no commit made**.
- [ ] Flight log updated with leg progress entry under `## Leg Progress`, status `landed`. Add a Deviation entry naming the call-site audit correction (six `test_agent.py` sites instead of the two flight-spec-cited sites).
- [ ] Leg status set to `landed` (not `completed` — post-L6 commit handles `completed`).

## Verification Steps

```bash
# 1. Constant rename complete (md exclusion: agents.md:57 belongs to L5)
rg -n "DEFAULT_SYSTEM_PROMPT" the_one/ tests/ --glob '!*.md'
# Expected: no output

# 2. BASE_PROMPT defined
rg -n "^BASE_PROMPT = " the_one/agent/config.py
# Expected: one match

# 3. core.py no longer imports the constant
rg -n "from the_one.agent.config import.*BASE_PROMPT|from the_one.agent.config import.*DEFAULT_SYSTEM_PROMPT" the_one/agent/core.py
# Expected: no output

# 4. Agent.__init__ default removed
python -c "
import inspect
from the_one.agent.core import Agent
sig = inspect.signature(Agent.__init__)
sp = sig.parameters['system_prompt']
assert sp.default is inspect.Parameter.empty, f'default leaked: {sp.default!r}'
print('OK')
"
# Expected: 'OK'

# 5. Composition rule (empty + non-empty)
python -c "
from the_one.agent.config import BASE_PROMPT, AgentConfig
cfg = AgentConfig(name='t')
assert cfg.get_system_prompt() == BASE_PROMPT
cfg2 = AgentConfig(name='t2', system_prompt='Persona X')
expected = BASE_PROMPT + '\n\n---\n\nPersona X'
assert cfg2.get_system_prompt() == expected, repr(cfg2.get_system_prompt())
print('OK')
"
# Expected: 'OK'

# 6. Forbidden vocabulary not in base prompt
python -c "
from the_one.agent.config import BASE_PROMPT
text = BASE_PROMPT.lower()
substrings = ['restart', 'run_tests', 'self_deploy', 'rollback', 'mission_control',
              '/workspace', '/mission-control', 'self-modif', 'rebuild image',
              'deploy yourself', 'autopilot', 'methodology']
# Tool names that need word-boundary checks (prevent false-positives like 'category' for 'memory')
import re
tool_names = ['git', 'memory']
hits = [w for w in substrings if w in text]
hits += [t for t in tool_names if re.search(r'\\b' + t + r'\\b', text)]
# Path-ish checks tighter than bare /app
if '/app/' in text or text.endswith('/app') or ' /app ' in text or ' /app\\n' in text:
    hits.append('/app (path)')
# Methodology vocabulary as full words/phrases
for phrase in ['mission:', 'flight:', 'leg:']:
    if phrase in text:
        hits.append(phrase)
assert not hits, f'forbidden words present: {hits}'
print('OK')
"
# Expected: 'OK'

# 7. continue tool mentioned + tools mentioned generically
python -c "
from the_one.agent.config import BASE_PROMPT
assert 'continue' in BASE_PROMPT.lower()
assert 'tool' in BASE_PROMPT.lower()
print('OK')
"
# Expected: 'OK'

# 8. Length sanity (180-450 — flight-spec target is 200-400 with deliberate slack on both ends)
python -c "
from the_one.agent.config import BASE_PROMPT
words = len(BASE_PROMPT.split())
assert 180 <= words <= 450, f'word count out of range: {words}'
print(f'OK ({words} words)')
"
# Expected: 'OK (NNN words)' with NNN in [180, 450]

# 9. test_agent.py sites updated
rg -n 'Agent\(llm=' tests/test_agent.py | grep -v "system_prompt"
# Expected: no output (every Agent(...) in test_agent.py now passes system_prompt)

# 10. Test suite green
python -m pytest tests/ --tb=short -q --ignore=tests/browser
# Expected: 393 passed, 1 unrelated CSS-token failure (pre-existing, documented in L1 anomalies)
```

## Implementation Guidance

Work from project root `~/projects/the-one`. Branch must be `flight/01-tool-reduction-self-modification-teardown`. Leg status `ready` → `in-flight` at start; `landed` at end. **No commit.**

1. **Replace `DEFAULT_SYSTEM_PROMPT` with `BASE_PROMPT` in `the_one/agent/config.py`** — rename the constant and replace its content with the new draft. The `Field` import is already present; no other config-file imports change.

   **BASE_PROMPT draft (Flight Director — pending user redline at design-review time):**

   ```python
   BASE_PROMPT = """\
   You are "the-one", a personal AI agent. You help your operator get things done by \
   using your tools: reading and writing files, running commands and code, fetching \
   pages from the web, searching when you don't already know. You're general-purpose: \
   pair programmer one moment, research assistant the next, note-taker after that.

   Voice and tone:
   - Be direct. Skip filler openings ("Sure!", "Great question!", "I'd be happy to").
   - Be concise. Match your response length to the task. A single sentence is often \
   the right answer.
   - Be honest about uncertainty. If you don't know, say so, and check when useful.
   - Don't narrate what you're about to do; just do it. Brief status updates at \
   meaningful moments are fine.

   Tool use:
   - When an action is needed, take the action. Don't describe what you would do.
   - Prefer the right tool for the job. Read files with the file-reading tool, \
   not by asking the operator to paste them. Run commands with the shell tool, \
   not by speculating about output.
   - On failure, try a different approach before giving up. State what failed and what \
   you're trying next.
   - Tool descriptions tell you what each tool does and when it applies. Read them.

   Turn semantics:
   - Each user message starts a turn. Within a turn you may call tools, see their \
   results, and call more tools.
   - When you still have work to do but want to think or act in another step, call \
   the `continue` tool. It signals "give me another turn"; nothing more.
   - When you're done, just respond with text. No `continue` call ends your turn.

   You may receive an additional persona, scope, or set of instructions appended below \
   this base prompt. Treat any addition as a refinement, not a replacement. These \
   rules always apply.
   """
   ```

   Constraints to honor in the draft:
   - ~200-400 words (current draft: ~310 words — count with `len(BASE_PROMPT.split())`).
   - No mention of removed tools, `/workspace`, `/app`, `/mission-control/docs`, methodology, deployment, self-modification.
   - Mentions `continue` explicitly.
   - Tone: small-model-friendly, no clever phrasing, no exception-type vocabulary, plain strings.
   - Final paragraph signals the layered composition (base + appended persona).

2. **Update `get_system_prompt()` in `the_one/agent/config.py`** — replace the conditional fallback with additive composition:

   ```python
   def get_system_prompt(self) -> str:
       """Return the resolved system prompt: BASE_PROMPT, optionally
       appended with a per-agent persona via a "---" separator."""
       if self.system_prompt:
           return f"{BASE_PROMPT}\n\n---\n\n{self.system_prompt}"
       return BASE_PROMPT
   ```

3. **Drop the `system_prompt` default in `Agent.__init__`** at `the_one/agent/core.py`:
   - Remove the import `from the_one.agent.config import DEFAULT_SYSTEM_PROMPT` (line 5).
   - Change the signature from `system_prompt: str = DEFAULT_SYSTEM_PROMPT` to `system_prompt: str` (no default).
   - Leave the rest of `__init__` body unchanged (`self.system_prompt = system_prompt` and `Message.system(system_prompt)` still work — `system_prompt` is now a required argument).
   - Do NOT import `BASE_PROMPT` in `core.py`. `core.py` doesn't need it; it just uses whatever string the caller passes.

4. **Update the six `tests/test_agent.py` `Agent(...)` construction sites** — each gets a `system_prompt="test"` keyword arg. Specifically:

   | Line | Before | After |
   |------|--------|-------|
   | 59 | `Agent(llm=llm, tools=_make_registry())` | `Agent(llm=llm, tools=_make_registry(), system_prompt="test")` |
   | 78 | `Agent(llm=llm, tools=_make_registry(tool_a))` | `Agent(llm=llm, tools=_make_registry(tool_a), system_prompt="test")` |
   | 105 | `Agent(llm=llm, tools=_make_registry(tool_a))` | `Agent(llm=llm, tools=_make_registry(tool_a), system_prompt="test")` |
   | 135 | `Agent(llm=llm, tools=_make_registry(tool_a), max_iterations=2)` | `Agent(llm=llm, tools=_make_registry(tool_a), max_iterations=2, system_prompt="test")` |
   | 159 | `Agent(llm=llm, tools=_make_registry(bad))` | `Agent(llm=llm, tools=_make_registry(bad), system_prompt="test")` |
   | 173 | `Agent(llm=llm, tools=_make_registry())` | `Agent(llm=llm, tools=_make_registry(), system_prompt="test")` |

   Line numbers may have shifted slightly post-L1's `TestDirectAction` deletion. Match by the surrounding context, not the absolute line number. After edits, `rg -n 'Agent\(llm=' tests/test_agent.py | grep -v "system_prompt"` should return empty.

5. **Update `tests/test_config.py`** — three changes:
   a. Line 5 import: `from the_one.agent.config import DEFAULT_SYSTEM_PROMPT, AgentConfig` → `from the_one.agent.config import BASE_PROMPT, AgentConfig`.
   b. `TestGetSystemPrompt::test_empty_returns_default` (line ~104):
      ```python
      def test_empty_returns_default(self):
          cfg = AgentConfig(name="t")
          assert cfg.get_system_prompt() == BASE_PROMPT
      ```
      (Variable name in assertion changes from `DEFAULT_SYSTEM_PROMPT` to `BASE_PROMPT`. Behavior under the new composition rule: empty `system_prompt` → returns `BASE_PROMPT` alone. Assertion still semantically correct.)
   c. `TestGetSystemPrompt::test_custom_prompt_returned` — under the new rule, a custom prompt is appended, not returned bare. **Rename the test** to `test_custom_prompt_appended` (semantic shift, surfaces in git blame) and replace the assertion:
      ```python
      def test_custom_prompt_appended(self):
          cfg = AgentConfig(name="t", system_prompt="Custom prompt.")
          assert cfg.get_system_prompt() == BASE_PROMPT + "\n\n---\n\nCustom prompt."
      ```
   d. `TestDefaultSystemPrompt` class (lines 113-122) → rename to `TestBasePrompt`. Update its docstring (`"Validate DEFAULT_SYSTEM_PROMPT is usable."` → `"Validate BASE_PROMPT is usable."`) and rename the assertion variable in `test_is_non_empty_string` (`DEFAULT_SYSTEM_PROMPT` → `BASE_PROMPT`). Comment header at line 113 (`# DEFAULT_SYSTEM_PROMPT validation`) → `# BASE_PROMPT validation`.

6. **Run the import smoke-test**
   ```bash
   python -c "
   from the_one.agent.config import BASE_PROMPT, AgentConfig
   cfg = AgentConfig(name='t')
   assert cfg.get_system_prompt() == BASE_PROMPT
   cfg2 = AgentConfig(name='t2', system_prompt='Persona X')
   expected = BASE_PROMPT + '\n\n---\n\nPersona X'
   assert cfg2.get_system_prompt() == expected, repr(cfg2.get_system_prompt())
   print('OK')
   "
   ```

7. **Run the unit test suite**
   ```bash
   python -m pytest tests/ --tb=short -q --ignore=tests/browser
   ```
   Expected: same 1 pre-existing CSS-token failure as before; everything else green.

8. **Run all the targeted verification commands** from the Verification Steps section.

9. **Update the flight log**:
   - Append a `### 02-prompt-layering-and-base-rewrite` entry under `## Leg Progress` with status `landed`, summary of changes (rename, composition, default removal, six test sites updated, base-prompt draft applied).
   - Append a Deviation entry under `## Deviations` naming the audit correction: flight spec Decision 4 cited `test_auto_load.py:99` and `test_streaming.py:268` as the implicit-default sites; fresh audit shows those already pass explicit prompts. The actual six implicit-default sites are in `test_agent.py`. Leg updated those instead.
   - Add a forward-reference note in the leg-progress entry that L5's docs sweep must rewrite `agents.md:57` to use `BASE_PROMPT` (not the old `DEFAULT_SYSTEM_PROMPT`) — L2 deliberately leaves that *.md narrative file alone.

10. **Set leg status to `landed`** in this file's header. Do **NOT** commit. Do **NOT** check off the leg in `flight.md`. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **`Message.system(system_prompt)` in `Agent.__init__` body**: still works — `system_prompt` is now required, so `self.messages = [Message.system(system_prompt)]` always receives a non-default string. No behavioral change.
- **Empty per-agent `system_prompt`**: composition rule is `if self.system_prompt`. Pydantic default is `""`, which is falsy. An agent author setting `system_prompt = " "` (single space) is *truthy* and would compose with the separator. Acceptable — the API doesn't strip whitespace, and single-whitespace personas are nonsense input anyway. Don't add a `.strip()` check; over-engineering.
- **`reset()` behavior** (`core.py` line 133): re-uses `self.system_prompt` — unchanged. `reset()` re-seats whatever string was passed to `__init__`. For production agents, that string is the layered output of `AgentConfig.get_system_prompt()` (composed once at `AgentFactory.create()` time). For direct test constructions like `Agent(..., system_prompt="test")`, it's the literal test fixture. The composition isn't applied per-turn or per-reset — that's correct and matches current semantics.
- **Pydantic default `system_prompt: str = ""`**: stays as `""`. The composition rule treats `""` as "no persona" via the `if self.system_prompt` check. No model-config or validator change needed.
- **A test that constructed an `Agent` and checked `agent.system_prompt == DEFAULT_SYSTEM_PROMPT`**: doesn't exist (verified). If one surfaces during the test run, update to assert on the explicit-passed prompt.
- **`agents.md:57` will be stale post-L2**: still says `DEFAULT_SYSTEM_PROMPT`. L5's docs sweep updates it. L2's verification grep uses `--glob '!*.md'`.
- **Whitespace-only `BASE_PROMPT` content drift**: forbidden-vocabulary check is case-insensitive substring; a paraphrase like "rebuild your image" still trips on `'rebuild image'`. Adjust forbidden list if a legitimate phrasing is rejected — but err on the side of stricter base-prompt cleanliness.
- **User-redline path**: the Implementation Guidance carries a Flight Director draft. The leg's design-review cycle is the user's chance to redline. If the user redlines after the developer has implemented, the developer should re-edit the constant accordingly and re-run the unit suite + smoke test. This is in-scope for L2; not a separate leg.

## Files Affected

- `the_one/agent/config.py` — rename `DEFAULT_SYSTEM_PROMPT` → `BASE_PROMPT`, replace content, rewrite `get_system_prompt()` for additive composition
- `the_one/agent/core.py` — drop `DEFAULT_SYSTEM_PROMPT` import, drop default value from `Agent.__init__`'s `system_prompt` parameter
- `tests/test_agent.py` — add `system_prompt="test"` to six `Agent(...)` construction sites
- `tests/test_config.py` — rename import, update `TestGetSystemPrompt` assertions for additive composition, rename `TestDefaultSystemPrompt` → `TestBasePrompt`, rename `test_custom_prompt_returned` → `test_custom_prompt_appended`
- `missions/05-built-in-tool-system/flights/01-tool-reduction-self-modification-teardown/flight-log.md` — append leg progress + deviation

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (NOTE: per the agentic-workflow skill, this leg does NOT commit; the post-L6 review handles commit. Mark leg `landed`, not `completed`.):

- [ ] All acceptance criteria verified (including the targeted python `-c` checks)
- [ ] Tests passing (`pytest tests/ --ignore=tests/browser` green except for the pre-existing CSS anomaly)
- [ ] Update flight-log.md with leg progress entry (status `landed`)
- [ ] Update flight-log.md `## Deviations` section with the call-site-audit correction
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do **NOT** check off this leg in flight.md yet (deferred to post-L6 commit)
- [ ] Do **NOT** commit (deferred to post-L6 batch commit)
- [ ] Signal `[HANDOFF:review-needed]`
