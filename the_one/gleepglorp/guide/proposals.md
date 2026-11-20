# Proposals

GleepGlorp can propose changes to your agents, their rules and their routines, and nothing happens until you approve.

## How a proposal works

When you ask GleepGlorp to change something, such as a new rule for an agent or a different schedule for a routine, it doesn't make the change itself. It reads how the item is set up now, then puts a proposal card in the chat. It says the change is proposed and waiting, never done.

## The card

The card names the item and shows what would change, field by field, as **Now** and **Proposed**. Fields that stay the same aren't listed. Read it as the exact list of edits you are agreeing to.

- **Approve** applies exactly those fields and nothing else. GleepGlorp then carries on with the next step, if you asked for more than one.
- **Dismiss** changes nothing. The item stays as it was, and GleepGlorp is told you said no.

## Warnings on a card

- **Check this** means GleepGlorp proposed the change after reading content that didn't come from you, such as a web page or a tool's answer. Look at the proposal more carefully before you approve it.
- **Changed since** means the item was edited after the proposal was made. If you choose **Approve anyway**, the proposal replaces what is there now, so compare the **Now** column with the current item first.

## When it fills a form instead

If you ask for a new agent, or a change to one, from the GleepGlorp drawer on a page, it fills in the open form with unsaved edits and you choose **Save** yourself; no card appears (see "drawer"). It proposes when you ask from Chats, for rules and routines, and for the next step after an approval.

## What it never proposes

- It never proposes deleting anything. If you want an agent, rule or routine removed, it sends you to the page, such as [Agents](#agents), and you delete it yourself.
- It never puts a key, token or password in a proposal and never asks you to paste one in the chat. It links you to the page where you enter it, such as [Add a model provider](#library/providers/~new) or [Add a secret](#library/secrets/~new).

## Related topics

- "gleepglorp" for what it can and can't do, and its settings.
- "agents", "rules-and-notes" and "routines" for the items it can propose changes to.
- "self-configuration" for letting an agent edit its own prompt and routines.
