# Model providers

A model provider is the connection an agent uses to reach a model: an account with a company, or a server on your own computer.

## Add a provider

Open the [Library](#library), choose **Add**, then **Model provider**, or go straight to [a new model provider](#library/providers/~new). Enter a **Name**, choose a **Type**, fill in the fields that appear and choose **Create**. Then open it and choose **Test**.

Agents pick a provider and model on their General tab; GleepGlorp picks one in Settings.

## The types

- **Ollama**: models running on your computer or another machine. The base URL starts as the local Ollama address. No key is needed.
- **OpenAI**: your OpenAI account. Enter an API key.
- **Anthropic**: your Anthropic account. Enter an API key.
- **OpenRouter**: one account that reaches many companies' models. Enter an API key.
- **OpenAI-compatible**: any other service or server that speaks the OpenAI way. Enter its base URL and, if it needs one, a key.
- **Claude Plan (OAuth)** and **Claude Plan (Token)**: use a Claude Pro or Max subscription instead of an API key. See below.

API keys are stored encrypted. After you save one, the field shows a mask. Leave the mask alone to keep the stored key.

## Settings that depend on the type

- **Context window** (Ollama): how much text the model holds at once. The default is 32,768. A larger window allows longer conversations but can be slower.
- **Extended thinking** (Claude types): lets newer Claude models, version 4.6 and later, reason step by step before they answer. New Claude providers start with it on.
- **Reasoning effort**: **Provider default**, **low**, **medium** or **high**. It guides how much a reasoning-capable model thinks.

## Using a Claude subscription

**Claude Plan (OAuth)** has an **Anthropic account** section. Choose **Sign in with Anthropic**, approve access in the window that opens, and paste the code you are shown, then choose **Confirm code**. If no window opens, open or copy the link it shows in any browser. Afterwards you can **Re-authenticate** or **Reset connection**.

**Claude Plan (Token)** takes a token instead. In a terminal run `claude setup-token`, then paste the token it prints into **Token**. It lasts about a year, and the editor warns when it is close to expiring.

Both types share your plan's usage limits.

## Models and Ollama

An existing provider shows an **Available models** section. For Ollama you can also **Pull** a model (with **Cancel pull**), load, unload or delete models, and **Refresh** the list.

## Ask GleepGlorp

GleepGlorp can propose a new provider, or a change to a provider's name, type, address or settings. Nothing changes until you approve. It never sees or sets a key: enter keys here, and sign in here for Claude Plan (OAuth). Changing the type clears the stored key when the new type takes none, and signs out a Claude Plan (OAuth) provider. A proposal can't carry a key between two types that take one: change the type yourself. The card warns about each effect and how many agents use the provider.

From the drawer it can instead fill this form for you as unsaved edits, type changes included. A type change away from a key type empties the key field: enter the new key, then **Save**.

## Delete a provider

**Delete provider** is in the Danger zone. If agents still use the provider, it tells you which, and you must move them to another provider first.

## Related topics

- "agents" for choosing a provider and model for an agent.
- "gleepglorp" for the assistant's own model.
