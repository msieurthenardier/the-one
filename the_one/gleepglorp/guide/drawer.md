# The GleepGlorp drawer

The drawer is a small GleepGlorp chat that sits beside the page you are on, so you can ask about what you are looking at, and it can fill in an agent's form for you.

## Opening and closing it

- Choose the violet **Ask GleepGlorp** button in the bottom corner, or press Ctrl K and pick **Ask GleepGlorp**.
- Choose **Close** in the drawer's header, or press Esc, to put it away. The drawer is always closed when the app loads.

The drawer is on Agents, Library and Settings. It isn't on [Chats](#chats), where you talk to GleepGlorp in the main chat instead, and it is hidden while GleepGlorp is turned off in [Settings › GleepGlorp](#settings/gleepglorp). If GleepGlorp needs a model, the drawer shows what is missing and a link to fix it.

## One conversation across pages

The drawer keeps one conversation as you move between pages, and it is still there after you reload. Choose **New chat** in its header to start a fresh one. Choose **Open in Chats** to continue the same conversation in the main chat. Each message you send carries the page you are on.

## It knows which page you are on

A line above the drawer's chat, "Looking at", shows the page, such as Library › MCP servers › New MCP server. GleepGlorp sees that line with each message, so "What does this page do?" gets an answer about the page in front of you. It never sees what you have typed into a form that you haven't saved.

## Filling in a form

On the page for a new agent, or an agent you have open, you can ask GleepGlorp to create or change the agent. Instead of a proposal card, it types the values into the open form:

- The values are **unsaved edits**. Nothing is stored until you choose **Save**, so you can read them, change them or leave without saving.
- A field you have already changed and not saved is kept as you left it, and the receipt says the form was only partly filled.
- It never fills in a key or a token.

A receipt in the chat says what was filled and what wasn't, and each field it filled carries a small note until you edit it. If the form couldn't be filled, for example because you were on Chats or had a dialog open, choose **Fill now** on the receipt to try again.

Changes to rules and routines, and anything you ask for from Chats, still come as proposals you approve (see "proposals"). To start from a blank form yourself, go to [New agent](#agents/~new).

## Related topics

- "gleepglorp" for what it can and can't do, and its settings.
- "proposals" for the cards that ask you to approve a change.
- "agents" for the agent form it fills.
