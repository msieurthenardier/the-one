# GleepGlorp

GleepGlorp is the assistant built into the app, there to explain how things work and help you set them up, and it can look and propose changes, but you approve anything that changes.

## Talking to it

GleepGlorp isn't one of your agents, so it doesn't appear in the Agents list and you can't give it tools, knowledge or routines. Start a chat from [Chats](#chats): choose **New chat** and pick GleepGlorp under "Built in". You can also press Ctrl K and search for it. It is available even before you have created an agent, as long as it has a model.

## What it can do

- **Read how your app is set up**: your agents, MCP servers, model providers, knowledge bases, connectors, routines, built-in tools and settings, and the names of your secrets and their keys. It never sees a secret's value or a provider's API key.
- **Read this guide**, so its answers about the app match what the app does.
- **Tell the time**, in the time zone you chose.
- **Search the web and read pages**, when Web access is on. If web search isn't set up, it can only read pages you give it, and the page shows a link to [set up web search](#settings/tools/web_search).
- **Keep notes about you**, when notes are on, such as how you like answers written, so it remembers between chats.

## What it can't do

- It can't change anything by itself. It can't run a command, or read or write your files. For agents, their rules and routines, MCP servers, model providers, knowledge bases, a secret's details (never its value), built-in tools, the time zone and knowledge indexing it can propose a change, which takes effect only when you approve it (see "proposals"). For most of these it can instead fill in the form for you to save. For anything else it explains where to go and what to press, and you make the change yourself.
- It doesn't read your conversations with other agents, your files or the app's logs.

## Privacy

What GleepGlorp reads is sent to the model provider you chose for it, just as your chat messages are. Descriptions, instructions, rules and routine prompts are shown to it as you wrote them, so don't put a password or key in one. Use a secret for that.

## Its settings

Open [Settings › GleepGlorp](#settings/gleepglorp):

- **GleepGlorp**: turns it on or off. When it is off, it isn't offered in Chats.
- **Provider** and **Model**: which of your model providers and which model it uses. Small local models may struggle with it.
- **Keep chats for**: how many days its chats are kept, from 1 to 365. The default is 30.
- **Web access**: lets it search the web and read pages.

Choose **Save** to apply changes. They reach open chats too.

The **Notes** section has the **Let GleepGlorp keep notes** switch, which saves as soon as you flip it. The section lists what GleepGlorp has kept. You can delete one note or choose **Clear all**. Turning notes off stops new notes, but the existing ones stay until you delete them.

## If it isn't ready

A chat with GleepGlorp tells you what is missing: it is turned off, it needs a model, or its provider was removed. A button takes you to the right page, or to the Library to add a provider.

## Related topics

- "overview" for a tour of the app.
- "model-providers" for adding the provider it needs.
- "rules-and-notes" for how notes work for agents.
