# Squawk 0098: The extractor seam's "zero pipeline change" claim is false for binary formats, in three places

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-22
**Completed**: —

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

*(written at completion)*

Scope the claim to text-shaped handlers in both restatements, and name the
binary gate at `indexer.py:155` as the known blocker for the deferred PDF/Office
mission. Correct the false comment in the M7 test.

## Verification

Read-back against `index_item`: every remaining claim is true of the code as
written. The M7 test's comment describes what the test actually exercises.

## Sign-Off

*(written at completion)*
