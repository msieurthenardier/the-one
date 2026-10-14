# Squawk 0207: Connector send tool's description contradicts inbound auto-delivery

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: —

## Report
`send_to_platform_channel` tells the agent that its "plain-text replies in this session do NOT auto-reach the platform — only calling this tool delivers content to peers". In an inbound connector session (a peer messages the agent on Discord), the turn's final assistant text **is** delivered to the originating target mechanically. So the description is wrong for connector-originated sessions and may lead an agent to send its reply twice (once through the tool, once by auto-delivery). Found during Mission 30 Flight 2 research.

## Evidence
- `the_one/tools/connector_send.py::SendToPlatformChannelTool.description`: "Your plain-text replies in this session do NOT auto-reach the platform — only calling this tool delivers content to peers."
- `the_one/connectors/inbound.py::_auto_deliver_reply`: "DD-10: mechanically deliver the turn's final assistant text to the ORIGINATING target, so a reply reaches the peer independent of the model's tool-calling reliability."
- The statement holds for web-chat sessions and is false for inbound connector sessions.

## Corrective Action
*(written at completion)* Qualify the sentence. Note that this is a starting-tool description, so under the Mission 30 convention the change lands with an eval run compared against the current baseline, including its token cost.

## Verification

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
