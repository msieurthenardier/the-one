"""Pure, stdlib-only JSON-Schema tool ``input_schema`` normalization primitives.

A library of schema-normalization primitives for coercing a tool
``input_schema`` into the shape a given provider's tool-definition API
requires. The first such primitive, :func:`sanitize_tool_schema`, encodes the
**Anthropic** Messages API constraint: a tool's top-level ``input_schema`` must
be a single ``object`` schema with no top-level ``oneOf`` / ``allOf`` /
``anyOf`` combinator. A future provider with a different constraint set (e.g.
OpenAI strict mode) would add its *own* sibling function here rather than
overloading this one.

Design constraints (flight M16 F02 DD1–DD4):

- **DD1** — pure leaf kernel: stdlib only, no ``the_one.llm`` (or any project)
  imports, no logging, no I/O. Transforms or raises; nothing else.
- **DD2** — operates on a deep copy of the input. The input object is never
  mutated: after a call it is ``is``-identical and byte-unchanged.
- **DD3** — top-level only. Nested combinators and ``$ref`` (inside properties,
  inside ``$defs``) are carried through untouched.
- **DD4** — the transform rule table, plus the
  :class:`UnsanitizableToolSchema` signal for shapes with no representable
  top-level object form.
"""

from __future__ import annotations

import copy

# Appended to ``description`` (exactly once) when a top-level combinator was
# flattened, so a human reading the tool definition understands the merged shape.
_MERGE_NOTE = "(Note: alternative input forms were merged; provide the fields that apply.)"

# Combinator keys processed at the top level. ``allOf`` unions requireds;
# ``anyOf``/``oneOf`` intersect them.
_INTERSECTION_COMBINATORS = ("anyOf", "oneOf")


class UnsanitizableToolSchema(Exception):  # noqa: N818  (name is the F02 cross-leg contract; leg 02 imports it verbatim)
    """Raised when a tool input_schema has no representable top-level object form."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _is_object_fragment(branch: object) -> bool:
    """A combinator branch we can merge into a top-level object.

    An object-fragment is a dict that contributes ``properties`` and/or
    ``required`` and/or declares ``type: "object"``. A ``$ref`` branch, a
    ``not`` branch, a scalar/array ``type`` branch, or a non-dict branch is not
    mergeable — those force an :class:`UnsanitizableToolSchema`.
    """
    if not isinstance(branch, dict):
        return False
    if "$ref" in branch or "not" in branch:
        return False
    branch_type = branch.get("type")
    if branch_type is not None:
        # A branch that pins a non-object type cannot merge into an object.
        if isinstance(branch_type, str):
            return branch_type == "object"
        if isinstance(branch_type, list):
            return "object" in branch_type
        return False
    # No type declared: mergeable iff it carries object-ish shape.
    return "properties" in branch or "required" in branch


def _dedup_preserve_order(items: list) -> list:
    """De-duplicate a list of (hashable-or-not) values, preserving first order."""
    out: list = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def _merge_branch_properties(
    target_props: dict,
    branch_props: dict,
) -> None:
    """Union ``branch_props`` into ``target_props`` (mutating ``target_props``).

    On a key already present with a *different* schema, the property becomes a
    nested ``{"anyOf": [<distinct variants>]}`` — nested combinators are legal,
    and this is the only lossless representation of a colliding key. Identical
    variants deduplicate to a single entry.
    """
    for key, schema in branch_props.items():
        if key not in target_props:
            target_props[key] = schema
            continue
        existing = target_props[key]
        if existing == schema:
            continue
        # Collision with a differing schema → collapse to a nested anyOf of the
        # distinct variants. If the existing value is already such an anyOf we
        # built, extend it rather than nesting anyOf-of-anyOf.
        if (
            isinstance(existing, dict)
            and set(existing.keys()) == {"anyOf"}
            and isinstance(existing["anyOf"], list)
        ):
            variants = list(existing["anyOf"])
        else:
            variants = [existing]
        variants.append(schema)
        target_props[key] = {"anyOf": _dedup_preserve_order(variants)}


def sanitize_tool_schema(schema: dict | None) -> dict:
    """Normalize a tool ``input_schema`` into a single top-level object schema.

    Returns a new dict (never the input). Raises
    :class:`UnsanitizableToolSchema` when no valid top-level object schema can
    be produced. The input is never mutated (DD2); only the top level is
    rewritten (DD3).
    """
    if schema is None or schema == {}:
        return {"type": "object"}
    if not isinstance(schema, dict):
        raise UnsanitizableToolSchema(f"top-level schema is {type(schema).__name__}, not an object")

    work = copy.deepcopy(schema)

    # (a) Resolve/merge top-level combinators BEFORE reconciling ``type`` — the
    # press_key case has both a top-level ``type`` and a top-level ``anyOf``,
    # and Anthropic rejects the combinator even when ``type`` is already object.
    flattened_combinator = False

    # --- allOf: union of requireds ---------------------------------------
    if "allOf" in work:
        branches = work.pop("allOf")
        if not isinstance(branches, list):
            raise UnsanitizableToolSchema("top-level allOf is not a list")
        if branches:
            flattened_combinator = True
            props = work.setdefault("properties", {})
            required = list(work.get("required", []))
            for branch in branches:
                if not _is_object_fragment(branch):
                    raise UnsanitizableToolSchema(
                        "top-level allOf contains a non-object branch "
                        "(a $ref, not, scalar, or array cannot merge into an object)"
                    )
                _merge_branch_properties(props, branch.get("properties", {}))
                required.extend(branch.get("required", []))
            work["required"] = _dedup_preserve_order(required)
            if not props:
                # Avoid leaving an empty ``properties`` we synthesized when no
                # branch contributed any.
                work.pop("properties", None)
        # Empty allOf list → no constraint; drop it, do not flatten/raise.

    # --- anyOf / oneOf: intersection of requireds ------------------------
    for combinator in _INTERSECTION_COMBINATORS:
        if combinator not in work:
            continue
        branches = work.pop(combinator)
        if not isinstance(branches, list):
            raise UnsanitizableToolSchema(f"top-level {combinator} is not a list")
        if not branches:
            # Empty list → no constraint; drop it, do not flatten/raise.
            continue
        flattened_combinator = True
        props = work.setdefault("properties", {})
        base_required = list(work.get("required", []))

        branch_requireds: list[list] = []
        for branch in branches:
            if not _is_object_fragment(branch):
                raise UnsanitizableToolSchema(
                    f"top-level {combinator} contains a non-object branch "
                    "(a $ref, not, scalar, or array cannot merge into an object)"
                )
            _merge_branch_properties(props, branch.get("properties", {}))
            branch_requireds.append(list(branch.get("required", [])))

        # Intersection of branch requireds: a field is unconditionally required
        # only if every branch requires it.
        if branch_requireds:
            intersection = [
                name
                for name in branch_requireds[0]
                if all(name in br for br in branch_requireds[1:])
            ]
        else:
            intersection = []
        # Base-level requirements are unconditional → unioned on top.
        merged_required = _dedup_preserve_order(base_required + intersection)
        if merged_required:
            work["required"] = merged_required
        else:
            # Both base and intersection empty → no unconditional requirements.
            work.pop("required", None)
        if not props:
            work.pop("properties", None)

    # (b) Reconcile ``type`` now that combinators are merged.
    declared_type = work.get("type")

    if isinstance(declared_type, list):
        if "object" in declared_type:
            # Collapse to the scalar string "object" — drop the array entirely.
            work["type"] = "object"
        else:
            raise UnsanitizableToolSchema(f"top-level type {declared_type} has no 'object' member")
    elif isinstance(declared_type, str) and declared_type != "object":
        # A scalar non-object type with nothing to merge into an object.
        raise UnsanitizableToolSchema(
            f"top-level type is '{declared_type}', tool inputs must be objects"
        )

    # A bare $ref / top-level ``not`` with no object shape → unsanitizable.
    # By this point an array type containing "object" has been collapsed to the
    # scalar string and a non-object scalar type has already raised, so the only
    # remaining object signals are ``properties`` or a scalar ``type=="object"``.
    # A sibling $ref *alongside* an object shape is preserved untouched (DD3).
    has_object_shape = "properties" in work or work.get("type") == "object"
    if not has_object_shape:
        if "$ref" in work:
            raise UnsanitizableToolSchema("top-level schema is a bare $ref with no object shape")
        if "not" in work:
            raise UnsanitizableToolSchema("top-level schema is a bare 'not' with no object shape")

    # (c) Finalize — ensure a scalar object type, append the merge note once.
    work["type"] = "object"
    if flattened_combinator:
        existing_desc = work.get("description")
        if existing_desc:
            work["description"] = f"{existing_desc} {_MERGE_NOTE}"
        else:
            work["description"] = _MERGE_NOTE

    return work
