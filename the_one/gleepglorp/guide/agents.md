# Agents

An agent is an assistant you set up for a kind of work, with a model, instructions, and the tools and knowledge you let it use.

## Create an agent

Open [Agents](#agents) and choose **New**, or go straight to [a new agent](#agents/~new). Fill in the **General** tab and choose **Create**.

You need at least one model provider first. If you have none, add one in the Library.

## The General tab

- **Name**: up to 64 characters. It can't contain a slash or backslash, can't be just dots, and can't contain control characters. The names "default" and "GleepGlorp" are kept for the app, in any capitals. Two agents can't share a name.
- **Description**: a short note about what the agent is for. It shows in the chat picker.
- **Provider** and **Model**: where the agent's answers come from. The model list loads from the provider you choose. **Test** checks that the provider can be reached. It doesn't check the rest of the agent.
- **System prompt**: the instructions that shape how the agent behaves.
- **Chat history retention (days)**: how long its chats are kept. The default is 30 days. You can set 1 to 365.
- **Max iterations**: the most steps the agent can take on one message, from 1 to 100. The default is 20. When an agent reaches it, the chat shows a notice with a **Continue** button.
- **Rich visuals**: when on, the agent is told it can answer with charts and widgets. When off, it isn't told, but any chart or widget it still writes is shown.

Choose **Save** to keep your changes. If you leave with unsaved changes, the app asks first.

## The other tabs

An agent has six tabs in all:

- **General**: the settings above.
- **Rules and notes**: standing rules you write, and notes the agent keeps.
- **Knowledge**: which knowledge bases it can search.
- **Tools**: its built-in tools, MCP servers and secrets.
- **Routines**: prompts it runs on a schedule.
- **Self-configuration**: whether it may edit its own prompt and routines.

Rules, notes and routines need a saved agent, so on a new agent they ask you to save first.

## Chatting with an agent

A saved agent has a **Chat** button at the top of its settings. It starts a new chat with that agent. You can also start one from Chats.

## Purge and delete

At the bottom of the General tab, **Purge now** deletes the agent's chats, its routines' run history and its finished approval history. The agent, its routines, rules and notes stay. **Delete agent** removes the agent with all of its chats, routines, rules, notes and settings, and can't be undone. It asks in a dialog that says how many chats it will delete; you tick "I understand this will delete all of this agent's chat history" before Delete turns on. Purge now asks in place, with a second click.

## Changes take effect

A new model, prompt or setting applies to chats you start or reopen after you save. A chat that is already running may keep what it started with until you reopen it.

## Related topics

- "agent-tools" covers the Tools tab.
- "rules-and-notes", "routines" and "self-configuration" cover those tabs.
- "knowledge-bases" explains what you can attach on the Knowledge tab.
- "model-providers" explains the providers behind the Provider list.
