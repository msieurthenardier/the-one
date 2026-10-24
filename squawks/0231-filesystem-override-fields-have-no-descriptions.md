# Squawk 0231: Filesystem tool config fields have no descriptions, so their override panels show no info buttons

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-22
**Completed**: 2026-10-24

## Report
On an agent's Built-in Tools tab, the Overrides panel for any Filesystem tool (`read_file`, `write_file`, `list_dir`, `grep`, ...) shows its fields (`path_allowlist`, `path_denylist`, `read_size_cap_bytes`, `allow_binary_files`) with no info button. The Execution and Web tools show one on every field. The info button renders only when the schema property carries a `description` (`static/js/areas/studio/tool-override-fields.js`, `render` → `ui.field({info: prop.description || undefined})`), and `GET /api/tools/configs/{name}` returns none for the Filesystem fields. The admin Built-in tools editor reads the same schema, so it lacks them too. Found at Mission 31 Flight 2's HAT (step 5).

## Evidence
- `the_one/tools/filesystem.py` `FilesystemConfig`: `path_allowlist`, `path_denylist`, `read_size_cap_bytes` and `allow_binary_files` are declared without `Field(description=...)`. Compare `the_one/tools/execution.py` `ExecutionConfig`, whose fields carry descriptions.
- At the HAT, `GET /api/tools/configs/read_file` listed the four properties with no `description`, and `shell`'s seven properties all had one.

## Corrective Action
Fixed in Mission 31 Flight 4 leg 05a. Every field of every built-in tool Config now carries a plain `Field(title=..., description=...)` (the four `FilesystemConfig` fields included, and the terse existing descriptions such as "Used when agent omits timeout." rewritten). The text is operator-facing only: `GET /api/tools/configs/{name}` serves it in the schema, and a unit test proves none of it is part of a tool's model-facing `to_schema()`. `tests/test_tool_config_text.py::test_every_served_property_has_a_written_title_and_description` walks every tool's served schema and fails on a missing description or an auto-generated title.

## Verification
- Each `FilesystemConfig` field has a plain one-sentence description. `GET /api/tools/configs/read_file` returns them, and a unit test pins that every overridable field of every built-in tool config has a non-empty description. The Filesystem Overrides panels then show info buttons.

## Sign-Off
*(flight review)*
**Reviewer**:
**Verdict**:
**Commit**:
