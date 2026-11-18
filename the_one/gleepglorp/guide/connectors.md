# Connectors

A connector links the app to a chat platform, so people can talk to your agents in Discord or Telegram.

## Add a connector

Open the [Library](#library), choose **Add**, then **Connector**, or go straight to [a new connector](#library/connectors/~new). Under **Identity**, enter a **Name**, choose the platform under **Type**, and paste the bot's **Token**. The **Enabled** switch turns the connector on or off. Choose **Create**.

The **Setup steps** section shows what to do on the platform's side:

- **Discord**: create an application and bot in Discord's developer portal, copy the token when it is shown, turn on the Message Content intent (without it the connector looks connected but silent), and invite the bot to your server with permission to send messages and read message history.
- **Telegram**: create the bot with BotFather and copy its token. Before adding the bot to a group, turn off its privacy mode with the /setprivacy command. Otherwise it sees only commands, mentions and replies there.

## Who the bot answers

- **Binding**: choose a **Default agent**. It answers messages that aren't covered by the channel map below. "— none —" means no default.
- **Admission**: the bot ignores a message unless its sender or its channel is on a list. List the **Allowlisted peers** (people) and **Allowlisted channels**, one per line. Other messages are dropped without a reply.
- **Always-listen channels**: normally the bot replies only to a direct message or when it is mentioned. In an always-listen channel it replies to every message.
- **Channel → agent map**: route a channel to a specific agent by its channel id. Direct messages always go to the default agent.

## Pairing

To admit a person without looking up their id, save the connector and use **Pairing**. They message the bot directly, you choose **Generate pairing code**, and they reply with the code within 10 minutes. They are then added to the allowed peers.

## Check the connection

On a saved connector the header shows the connection's state. **Run doctor**, under **Diagnostics**, checks the token and the platform setup and reports what is wrong.

## How conversations work

Each channel, thread or direct message is its own conversation, and it continues for about a day of activity. A person can send exactly /new to start a fresh one. These chats appear in your Chats list with the platform's badge. You can open one and read it, and a new reply from the agent appears there.

An agent bound to a connector also gets tools to send to a platform channel and to read a channel's history. It can send only to channels where it is the agent that answers, and to people on the allowed list when it is the default agent.

## Related topics

- "agents" for creating the agent a connector uses.
- "routines" for agents that post on a schedule using their send tool.
- "secrets" for keeping other credentials out of sight.
