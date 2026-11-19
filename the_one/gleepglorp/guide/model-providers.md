# Model providers

A model provider is the connection an agent uses to reach a model, such as an account with a company or a server that runs models on your own computer.

## Add a provider

Open the [Library](#library), choose **Add**, then **Model provider**, or go straight to [a new model provider](#library/providers/~new). Enter a **Name**, choose a **Type**, fill in the fields that appear and choose **Create**. Once it is saved, open it and choose **Test** to check the connection.

Every agent picks one of your providers, and one of its models, on its General tab. GleepGlorp picks one too, in Settings.

## The types

- **Ollama**: models running on your computer or another machine. The base URL starts as the local Ollama address. No key is needed.
- **OpenAI**: your OpenAI account. Enter an API key.
- **Anthropic**: your Anthropic account. Enter an API key.
- **OpenRouter**: one account that reaches many companies' models. Enter an API key.
- **OpenAI-compatible**: any other service or server that speaks the OpenAI way. Enter its base URL and, if it needs one, a key.
- **Claude Plan (OAuth)** and **Claude Plan (Token)**: use a Claude Pro or Max subscription instead of an API key. See below.

API keys are stored encrypted. After you save one, the field shows a mask. Leave the mask alone to keep the stored key.

## Settings that depend on the type

- **Context window** (Ollama): how much text the model holds at once. The default is 32,768. A larger window allows longer conversations but is slower when the model doesn't fully fit in your graphics memory.
- **Extended thinking** (Claude types): lets newer Claude models, version 4.6 and later, reason step by step before they answer. New Claude providers start with it on. Older models answer without it.
- **Reasoning effort**: **Provider default**, **low**, **medium** or **high**. It guides how much a reasoning-capable model thinks.

## Using a Claude subscription

**Claude Plan (OAuth)** has an **Anthropic account** section. Choose **Sign in with Anthropic**, approve access in the window that opens, and paste the code you are shown, then choose **Confirm code**. If no window opens, open or copy the link it shows in any browser. Afterwards you can **Re-authenticate** or **Reset connection**. The app renews the sign-in for you.

**Claude Plan (Token)** takes a token instead. In a terminal run `claude setup-token`, then paste the token it prints into **Token**. It lasts about a year, and the editor shows roughly when it expires and warns when it is close.

Both types share your plan's usage limits. If the plan is out of room, the app shows a clearer message than the service's bare "Error".

## Models and Ollama

An existing provider shows an **Available models** section with the models it offers. For Ollama you can also manage models there:

- **Pull** downloads a model. Choose one from the list, then **Pull**. The app checks the size first, shows progress, and lets you **Cancel pull**.
- The list shows **Running** and **Available** models. Each can be loaded into memory, unloaded, or deleted.
- **Refresh** reloads the list.

## Delete a provider

**Delete provider** is in the Danger zone. If agents still use the provider, it tells you which, and you must move them to another provider first.

## Related topics

- "agents" for choosing a provider and model for an agent.
- "gleepglorp" for the assistant's own model.
