# MCP servers

An MCP server is a separate program or service that gives your agents extra tools, such as a browser, a database or another app's API.

## Add a server

Open the [Library](#library), choose **Add**, then **MCP server**, or go straight to [a new MCP server](#library/mcp/~new). Give it a **Name** and choose its **Type**:

- **Local program (stdio)**: the app starts a program on this computer.
- **Remote server (HTTP)**: the app connects to a web address.

Choose **Create**. The app then tries to connect and shows the result.

## Local programs

Pick a **Command** from the list: **Python package (uvx)**, **Node package (npx)**, **Python package (pipx)**, **Python module or script**, **Node script**, **Shell script**, or **Other command…** to type your own. A hint under the list says what to put in **Arguments**.

**Arguments** are entered one per row, in order. Use the add button for a new row, and the row controls to remove or move one.

You can also set a **Working directory**, and **Environment variables** as key and value pairs.

Local programs run in a sandbox on systems that support one. Under **Sandbox**, **Allow network access** is needed the first time uvx, npx or pipx downloads a package.
## Remote servers

Enter the **URL**. Add **Headers** if the server needs them, for example an API key. Turn on **Sensitive** for a value to store it encrypted. It is hidden after you save.

## Connecting, Test and sign-in

The Connection section shows one of: **Connected**, **Sign-in needed**, **Couldn't connect** or **Not connected**.

- **Test** checks the connection using what is on the form.
- A server that needs you to sign in shows **Sign in**. A sign-in window opens. If none does, use **Open sign-in page**. The app notices when you finish.
- If a server with headers answers "unauthorized", the app says it rejected the configured credentials. Check the headers. No sign-in is offered in that case.
- **Reset connection** signs out a signed-in remote server.
- **Forget tools list** clears the saved list of tools, so the app asks the server again.

## Ask GleepGlorp

GleepGlorp can propose a new server, or a change to a server's name, address, command, arguments, headers or environment variables. Nothing changes until you approve. It can't enter a secret: add Sensitive values yourself in the editor, with **Sensitive** turned on. It can't sign in for you, because sign-in happens on the page. And it can't change an existing server's type, working directory or sandbox: change those in the editor.

GleepGlorp can also fill this form without saving: each value gets a note, and nothing is stored until you choose **Create** or **Save**. For a secret it adds an empty **Sensitive** row for you to fill. Fields you already changed are left alone. A change you approve while the server is open updates the form, keeping your edits.

## Give an agent the server

Adding a server doesn't give any agent its tools. Open [Agents](#agents), pick an agent, open its **Tools** tab and turn on the server under **MCP servers**. There you can switch off single tools, and for a server that needs credentials you can give this agent its own headers or environment variables with **Override headers** or **Override environment variables**. Use **Test** to check them. See "agent-tools".

## Rename or delete

Renaming a server updates the agents that use it. **Delete MCP server**, at the bottom, removes it.

## Related topics

- "agent-tools" for attaching a server to an agent.
- "secrets" for values an agent can use in a tool without seeing them.
