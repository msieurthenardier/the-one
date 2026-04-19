# Leg: plugin-protocol

**Status**: completed
**Flight**: [Architecture Blueprint](../flight.md)

## Objective

Design the ToolProvider protocol, per-agent tool filtering, and the built-in vs MCP tool loading strategy.

## Context

- The current `load_defaults()` method tightly couples ToolRegistry to all 14 tool implementations
- Flight design decisions specify a ToolProvider protocol with BuiltinToolProvider replacing load_defaults()
- The protocol must support future MCP client integrations without breaking changes
- Per-agent tool views (enabled/disabled) are essential for multi-agent support
- Detailed ABC interface is deferred to Flight 2 stub; this leg makes high-level design decisions

## Inputs

- Target architecture from Leg 1 (tools/ module structure)
- Multi-agent model from Leg 2 (AgentConfig.enabled_tools, disabled_tools)
- Current ToolRegistry and load_defaults() implementation

## Outputs

- `plugin-protocol.md` — design artifact in the flight directory
- ToolProvider protocol, BuiltinToolProvider design, per-agent filtering strategy

## Acceptance Criteria

- [ ] ToolProvider protocol is defined with method signatures and semantics
- [ ] BuiltinToolProvider replaces load_defaults() with equivalent behavior
- [ ] Per-agent tool view mechanism (whitelist + blacklist) is specified
- [ ] Filtering happens at factory time, not inside Agent
- [ ] Future MCP integration surface is identified without over-designing
- [ ] Tool schema translation responsibilities are clearly assigned

## Verification Steps

- Verify BuiltinToolProvider produces the same 14 tools as current load_defaults()
- Confirm whitelist/blacklist logic handles edge cases (null=all, empty=none)
- Check that ToolProvider protocol is implementable for both built-in and MCP cases

## Implementation Guidance

1. **Define ToolProvider protocol** — name property, get_tools() method
2. **Design BuiltinToolProvider** — lazy-import strategy, tool instantiation
3. **Specify per-agent filtering** — enabled_tools (whitelist) + disabled_tools (blacklist)
4. **Place filtering in factory** — Agent receives a pre-filtered ToolRegistry
5. **Identify MCP integration surface** — how McpToolProvider would implement the protocol
6. **Clarify schema translation** — where LLMProvider.tool_schema() fits relative to ToolProvider

## Edge Cases

- **enabled_tools=null, disabled_tools=null**: All tools enabled (current behavior)
- **enabled_tools=[], disabled_tools=null**: No tools enabled
- **enabled_tools=["shell"], disabled_tools=["shell"]**: Blacklist wins (explicit disable overrides)

## Files Affected

- `missions/01-structural-foundation/flights/01-architecture-blueprint/plugin-protocol.md` — created (design artifact)
