# The app at a glance

The app has four main pages, listed down the left edge: Chats, Agents, Library and Settings.

In a small window, narrower than 768 pixels, the app shows one pane at a time: the page's list (or, in Settings, its menu of pages) or the item you opened. Choose an item to see it. To get back to the list or menu, choose the page's icon on the left again; this works for Settings too. In such a small window the agent's panel in a chat (the button at the right end of the chat's header) fills the whole area beside the left edge and the buttons behind it are switched off until you put it away: choose the **Close** button (an X) in the panel's header or press Esc. It starts closed each time you load the app, and choosing another page also puts it away. Window size does not change what you can do, only what is on screen at once.

## Chats

[Chats](#chats) is where you talk to an agent. The list on the left holds your conversations, newest first, grouped by how recent they are. Choose **New chat** to pick who you want to talk to. The picker lists GleepGlorp under "Built in", then your recently used agents, then all your agents. You can search it by name, model or description.

Inside a chat you can attach images, stop a reply that is running, and open a panel about the agent you are talking to. That panel shows its model and what it can use, and it has a link to the agent's settings.

## Agents

[Agents](#agents) is where you create and tune assistants. An agent is a model from one of your providers, plus instructions, plus the tools and knowledge you let it use. Pick an agent in the list to edit it, or choose **New** to create one.

## Library

[Library](#library) holds the things agents can use. You add each one once, then choose which agents get it in the agent's own settings. There are five groups:

- **Model providers**: the accounts or servers that run models.
- **Knowledge bases**: folders of documents agents can search.
- **MCP servers**: extra tools from tool servers.
- **Connectors**: links to chat platforms such as Discord and Telegram.
- **Secrets**: values an agent can use in a tool without seeing them.

Use the **Add** button at the top of the list to add any of them.

## Settings

Settings covers the whole app rather than one agent:

- **GleepGlorp**: the built-in assistant's model and switches.
- **Appearance**, **Date and time**, **Prompts** and **Encryption**.
- **Built-in tools** and **Knowledge indexing**, which set defaults for every agent.

## Getting started

Add a model provider in the Library first, because every agent needs one. Then create an agent, and chat with it from Chats. If you are stuck at any step, GleepGlorp can explain the screen you are on, and it can read how your app is set up. It cannot change anything for you.

## Jumping around

Press **Ctrl K** (**Cmd K** on a Mac), or use the **Jump to** button at the bottom of the left edge, to search for an agent, chat, Library item or Settings page and go straight to it.

## Where to read more

- [Agents](#agents) explains agent settings, and the guide topics "agent-tools", "rules-and-notes", "routines" and "self-configuration" go deeper.
- "model-providers", "mcp-servers", "knowledge-bases", "connectors" and "secrets" cover each Library group.
- "settings" describes each Settings page, and "gleepglorp" covers the assistant itself.
