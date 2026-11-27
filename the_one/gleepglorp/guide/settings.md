# Settings

Settings holds the choices that apply to the whole app, rather than to one agent.

The pages are listed down the left of [Settings](#settings/appearance), in three groups.

## Assistant

- [GleepGlorp](#settings/gleepglorp): the built-in assistant's model, its switches, how long its chats are kept, and its saved notes. See "gleepglorp".

## General

- [Appearance](#settings/appearance): choose **Light**, **Dark** or **Auto**. Auto follows your operating system.
- [Date and time](#settings/date-and-time): pick the time zone agents use when they tell the time. The app shows times in it too. You can use the system's zone, or **Choose a time zone** and search by city, zone or offset. If your browser's zone differs from the chosen one, the page offers a one-step switch. It saves as you choose, and a preview shows what agents will see. A chat that is already open keeps the date it last loaded, and the next or a reopened chat gets the new one.
- [Prompts](#settings/prompts): a read-only view of the text the app adds to every agent's instructions, in the order it is put together: the platform text, the **Rules** layer, the **Notes** layer, the **Secrets** layer and the date line. Each block says when it applies, and the rules, notes and secrets blocks use placeholder content. Nothing here can be edited.
- [Encryption](#settings/encryption): the app stores provider keys, sign-in tokens, server and connector secrets and tool settings encrypted with one key. The page shows when the key last changed and how many stored items it covers. **Rotate encryption key** makes a new key and re-encrypts everything with it. Choose it twice to confirm. The old key is discarded, so this can't be undone.

## Defaults for agents

- [Built-in tools](#settings/tools): the app-wide settings for the tools that come with the app, in tabs by kind (in a small window, one button that lists the kinds). Each tool has a switch, "Enable ... for all agents". A tool that is off here is off for every agent. Select a tool's name to open it. You see its description, the **Enabled for all agents** switch and its configuration, such as allowed folders or a search engine. Some tools have a **Test connection** button. If a change would affect agents that already have their own overrides, the app tells you how many and asks you to confirm.
- [Knowledge indexing](#settings/knowledge-indexing): the chunk size (200 to 2,000 characters), the chunk overlap (at most half the chunk size), how often folders are re-checked (10 seconds to 24 hours) and whether folders are watched for changes. The embedding model and vector store are shown but fixed by the app. See "knowledge-bases".

## With GleepGlorp

GleepGlorp can propose changes, which you approve. On **Built-in tools** it can switch a tool on or off and set its limits or search engine. On **Date and time** it proposes the time zone. On **Knowledge indexing** it proposes chunk size, overlap and folder watching. It can also fill the Built-in tools and Knowledge indexing forms for you to save. It never sets allowed folders, hosts or API keys.

## Saving

Pages with a form, such as GleepGlorp and Knowledge indexing, have **Save** and **Cancel** at the top. If you leave with unsaved changes, the app asks first. Appearance, Date and time, and the tool switches save as soon as you choose.

## Related topics

- "agent-tools" for how an agent's tools relate to the app-wide ones.
- "gleepglorp" for the assistant's own page.
