# Squawk 0231: Filesystem tool config fields have no descriptions, so their override panels show no info buttons

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-22
**Completed**: —

## Report
On an agent's Built-in Tools tab, the Overrides panel for any Filesystem tool (`read_file`, `write_file`, `list_dir`, `grep`, ...) shows its fields (`path_allowlist`, `path_denylist`, `read_size_cap_bytes`, `allow_binary_files`) with no info button. The Execution and Web tools show one on every field. The info button renders only when the schema property carries a `description` (`static/js/areas/studio/tool-override-fields.js`, `render` → `ui.field({info: prop.description || undefined})`), and `GET /api/tools/configs/{name}` returns none for the Filesystem fields. The admin Built-in tools editor reads the same schema, so it lacks them too. Found at Mission 31 Flight 2's HAT (step 5).

## Evidence
- `the_one/tools/filesystem.py` `FilesystemConfig`: `path_allowlist`, `path_denylist`, `read_size_cap_bytes` and `allow_binary_files` are declared without `Field(description=...)`. Compare `the_one/tools/execution.py` `ExecutionConfig`, whose fields carry descriptions.
- At the HAT, `GET /api/tools/configs/read_file` listed the four properties with no `description`, and `shell`'s seven properties all had one.

## Corrective Action
*(written at completion)*

## Verification
- Each `FilesystemConfig` field has a plain one-sentence description. `GET /api/tools/configs/read_file` returns them, and a unit test pins that every overridable field of every built-in tool config has a non-empty description. The Filesystem Overrides panels then show info buttons.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
