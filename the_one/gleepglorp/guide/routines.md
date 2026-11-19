# Routines

A routine is a named prompt that an agent runs on a schedule, with no one in the chat.

## Where to find it

Open [Agents](#agents), pick a saved agent, then open its **Routines** tab and choose **New routine**. Routines belong to one agent, so a new agent must be saved first.

## What a routine does

Each time a routine runs, it starts a new chat owned by the agent and titled with the routine's name. The agent works from the prompt using the tools it normally has. Nobody approves its steps along the way. Choose your prompt and the agent's tools with that in mind.

A routine doesn't post to Discord or Telegram by itself. If the prompt asks the agent to send a message, the agent uses its own platform-sending tool, as it would in any chat.

## Create or edit a routine

The form has:

- **Name**.
- **Prompt**: what the agent should do each run. It can be up to 4,000 characters.
- **Start**: choose **On** and set a date and time, **In** and set a number of minutes, hours or days, or **Immediately**, which runs the first time as soon as you save.
- **Repeat**: **Does not repeat**, **Every day**, **Every weekday (Monday to Friday)**, a weekly, monthly or yearly choice based on the start date, or **Custom…**. Custom lets you repeat every number of minutes, hours, days, weeks, months or years, choose weekdays, and end **Never**, **On** a date or **After** a number of runs.

Times are in the time zone you chose in [Date and time](#settings/date-and-time).

## Working with routines

Each routine in the list has a switch to turn it on or off, and a menu with **Run now**, **Edit** and **Delete**. Open a routine to see its prompt and its recent runs. Each run shows when it happened, how it started, the outcome, and an **Open chat** link to read what the agent did. **Show more runs** loads older ones.

- **Run now** starts a run at once, outside the schedule. If the routine is already running, you are told so.
- A one-time routine shows as done after it runs. Edit its schedule to run it again.
- Deleting a routine removes its run history. The chats its runs started stay.

## When the app isn't running

Routines run only while the app is open. If a run was due while the app was closed, the app catches it up when it starts, as long as it is within a short grace period, which is up to two hours for a repeating routine and up to a day for a one-time routine. After that the run is recorded as **Missed** and the routine waits for its next time. If the previous run is still going when the next is due, the new one is skipped.

A run is stopped after 15 minutes by default.

## Limits

One agent can have up to 50 routines turned on and up to 200 unfinished routines in all.

## Routines the agent writes

If you allow it on the agent's Self-configuration tab, the agent can list, schedule, change and cancel its own routines. Those show a "Made by the agent" label, and you can require your approval first. See "self-configuration".

## Related topics

- "agents" for the other tabs.
- "settings" for the time zone page.
