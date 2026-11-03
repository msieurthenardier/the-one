# Squawk 0098: The extractor seam's "zero pipeline change" claim is false for binary formats, in three places

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-22
**Completed**: 2026-11-03
**Related**: 0096, 0099: docstring and doc claims that overstate the knowledge/vector code; complete together ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

## Report

The documentation states that adding a file-format handler is "one module plus
one `register` call, with zero pipeline change", and names PDF and Office as
following that path. It is false for exactly those formats.

`index_item` resolves the extractor and then applies an **unconditional** binary
sniff before calling it, with no branch on the resolved extractor and no
capability flag on the `Extractor` Protocol by which a handler could declare it
consumes binary input. A `.docx` is a ZIP (`PK\x03\x04\x14\x00\x00\x00…`, null
bytes at offset 4), so every file would land `failed` with error
`"binary content"` and `extract` would never be called. Introducing such a
handler requires editing `index_item` — which is the indexing pipeline.

The claim is true for a **text-shaped** handler (the `HtmlExtractor` the
docstrings use as their example needs no pipeline change), so the correction is
to scope the claim, not to delete it.

**The pinning test cannot detect this and asserts the opposite.** This squawk
covers the documentation and the false test comment only. Actually lifting the
binary gate belongs to the deferred PDF/Office mission, where a real handler
exists to test against — it needs a design decision (capability flag on the
Protocol? gate moved into the extractor?) and so does not qualify as a squawk.

## Evidence

- `the_one/knowledge/indexer.py:143` — `extractor = extractor_for(path)`
- `the_one/knowledge/indexer.py:155` — `if await asyncio.to_thread(is_binary_head, path): raise _Reject("binary content")`, unconditional
- `the_one/knowledge/indexer.py:159` — `text = await asyncio.to_thread(extractor.extract, path)`, reached only if the sniff passed
- `the_one/knowledge/indexer.py:77-85` — `is_binary_head` returns True on any null byte in the first 8 KiB
- `the_one/agents.md:1211` — "Adding a new format is one module plus one `register` call, with zero pipeline change — pinned by `tests/test_kb_extractors.py`'s M7 test"
- `the_one/knowledge/extractors/text.py:5-8` — "PDF and Office formats follow the same path in a later mission"
- `tests/test_kb_extractors.py:255-257` — writes text content under the comment
  "Content is irrelevant — StubExtractor always returns STUB_TEXT, ignoring
  what's on disk." Content is **not** irrelevant: `index_item` reads the first
  8 KiB before the extractor is consulted. Write ZIP or PDF header bytes and the
  test fails on `outcome.error == "binary content"`.

## Corrective Action

Scoped the claim to text-shaped handlers in `the_one/agents.md` (Knowledge indexing),
`the_one/knowledge/extractors/__init__.py` and `extractors/text.py`, naming the
unconditional `is_binary_head` gate in `index_item` as the blocker for PDF/Office. Corrected
the M7 test comment in `tests/test_kb_extractors.py`.

## Verification

Read-back against `index_item` (`indexer.py` binary sniff precedes `extractor.extract`):
every remaining claim is true. The M7 test comment now states the content must be text.
Comment-only test change.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
