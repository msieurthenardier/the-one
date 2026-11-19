# Agent tools

What an agent can do beyond writing text comes from its tools, which you choose on the agent's Tools tab and Knowledge tab.

## Where to find it

Open [Agents](#agents), pick an agent, then open its **Tools** tab. The tab has three sections, from top to bottom: **Secrets**, **MCP servers** and **Built-in tools**. Attaching knowledge is on the separate **Knowledge** tab.

Changes on these tabs are saved with the agent's **Save** button, except the MCP server credential changes described below, which save on their own.

## Built-in tools

Built-in tools come with the app and are grouped by kind:

- **Filesystem**: read, write, edit, move and delete files, make folders, and search and list files.
- **Execution**: run shell commands and Python, including longer shell sessions.
- **Web**: fetch a page, search the web, make web requests and download files.
- **Connectors**: send to and read from chat platforms, and look up where to send.
- **Time**: the current time.

Each kind has a master switch, "Enable all ... tools", and each tool has its own switch. The count shows how many are on. The agent loads tools as it needs them. With a model that has room, it may be given all its enabled tools from the start.

The current time tool is always available to the agent, even if you limit its other tools. Turn it off on this tab if you don't want this agent to have it.

A tool that is switched off for everyone in [Built-in tools](#settings/tools) in Settings can't be used by any agent.

## Overrides

Each enabled tool has an **Overrides** section. It lets you give this one agent a narrower setting than the app-wide one, such as fewer allowed folders. An override can only narrow. If a setting would let the agent do more than the app-wide setting allows, saving is refused and the field shows why.

If you later tighten the app-wide setting, an agent's override that now goes too far is trimmed to fit, and the Tools tab shows a notice saying so.

The shell and Python tools aren't limited by an agent's path lists. Turn them off for this agent if you want to keep it to those paths.

## MCP servers

MCP servers are extra tool servers you add in the Library. Each one appears as a tile with an "Attach" switch. Turn it on to give the agent that server's tools. Open the tile to:

- switch off individual tools from that server;
- see the server's headers (for a remote server) or environment variables (for a local program);
- choose **Override headers** or **Override environment variables** to give this agent its own values, then **Save**. The change applies the next time the agent connects, and a credentialed agent sees only its own tool list;
- choose **Test** to check the connection with this agent's values.

"mcp-servers" explains adding and signing in to a server.

## Knowledge

On the **Knowledge** tab each knowledge base has a switch. Turning one on gives the agent a search tool for it, and the row shows that tool's name. An agent can search only the knowledge bases you attach to it. See "knowledge-bases".

## Secrets

The **Secrets** section lists your secrets, each with its description and how many tools it is allowed in. Turn one on to let this agent use it. The agent never sees the value. See "secrets".

## Related topics

- "agents" for the other tabs.
- "settings" for the app-wide tool defaults.
