# Secrets

A secret is a value, such as a password, a key or an address, that an agent can use in a tool call without ever seeing it.

## Create a secret

Open the [Library](#library), choose **Add**, then **Secret**, or go straight to [a new secret](#library/secrets/~new). Fill in:

- **Name** and **Description**: what it is and when to use it. Agents see the name and description.
- **Values**: one or more **Key** and **Value** pairs. The key is the short name the agent uses. The value is stored encrypted, and it isn't shown again after you save.
- **Allowed tools**: the tools that may receive this secret's values. Type to search the built-in and MCP tools. You must list at least one.

Then choose **Create**.

## Give an agent a secret

Creating a secret doesn't give it to anyone. Open [Agents](#agents), pick an agent, open its **Tools** tab, and turn on the secret under **Secrets**. Each row shows the description and how many tools it is allowed in. You can change grants at any time, and a change applies on the agent's next tool call.

## How an agent uses it

The agent is told the keys it has been given, with each secret's name, description and allowed tools, but never a value. When it needs one in a tool call, it writes a placeholder in the tool's input, in the form {{secret:key}}. When the tool runs, the app swaps in the real value. The chat history and what is sent to the model keep only the placeholder.

If the tool's output contains a secret's value, the app replaces it with [secret:key] before the agent or the chat sees it.

The app refuses the call, with a message that names the key and never the value, when:

- the agent hasn't been given that secret;
- the tool isn't in the secret's allowed tools.

## Tools that can't be allowed

A few tools can't be listed under **Allowed tools**, because they store or publish what they are given: the note and routine tools, the tool that sends to a chat platform, an agent's self-configuration tools, and the tool-search and continue steps. Saving a secret that lists one is refused.

## Keep in mind

The value is hidden from the agent and the model only while it stays the exact value. A tool that changes it, for example by encoding it, can return something the app can't recognise. Allow a secret only on tools you trust with it.

## Edit or delete

Open a secret to change its description, its keys, or its allowed tools. Values show as hidden, so to change one, type the new value. The **Used by** section lists the agents that have it. **Delete secret** removes it, and if agents use it, you are told how many it will be removed from before you confirm.

## Related topics

- "agent-tools" for the Tools tab.
- "mcp-servers" for the MCP tools you can allow.
- "settings" describes the Prompts page, which shows the agent-facing secrets text.
