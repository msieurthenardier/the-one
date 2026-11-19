# Self-configuration

Self-configuration lets an agent change a small, fixed part of its own setup, with you able to review, approve and undo every change.

## Where to find it

Open [Agents](#agents), pick a saved agent, then open its **Self-configuration** tab. Everything is off until you turn it on. Each switch saves at once.

## What an agent can change

The tab has a "What this agent can change" section with two items:

- **Agent prompt**: with "Let this agent edit its description and system prompt" on, the agent can read its own settings and replace its description or its system prompt. Each change replaces the whole text. It can't touch anything else, such as its model, tools or other settings.
- **Routines**: with "Let this agent manage its routines" on, the agent can list, schedule, change and cancel its own routines, including ones you made. See "routines".

When the agent changes its prompt or description it chooses when the change lands: at the end of its current turn, or the next time the conversation is reopened. It never changes mid-turn.

## Approval

Each item has its own "Require approval" switch: "Require approval for prompt edits" and "Require approval for routine changes". They are off by default.

- With approval **off**, the agent's change applies at once.
- With approval **on**, the change waits under "Waiting for approval". Choose **Approve** to apply it or **Dismiss** to drop it.
- If the value changed since the agent proposed its edit, approving would overwrite your newer value, so the app shows both and asks you to choose **Overwrite and approve**.

Turning the Routines item off withdraws any routine changes still waiting.

## History and restore

The Agent prompt item keeps a history of every change to the agent's description and system prompt, whoever made it. Under "Restore to an earlier value" you can put either field back to any earlier value it held. A restore applies immediately, it is never held for approval, and it is recorded as a new entry. The Routines item keeps a list of the agent's routine changes.

## Check this flag

If the agent made a change after reading content that didn't come from you, such as a web page, the change carries a "Check this" flag. Read it before you approve it.

## External access

At the bottom of the tab, **External access** lets you give another tool, or another agent, a credential that works only for this agent's self-configuration. Enter a label and choose **Grant access**. The token appears once, so copy it then. You can **Rotate** or **Revoke** a grant at any time, and the change takes effect immediately. This section is available only while self-configuration is on.

## Related topics

- "agents" for the other tabs.
- "routines" for what the Routines item manages.
