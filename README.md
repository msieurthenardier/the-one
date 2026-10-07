<p align="center">
  <img src="the_one/interfaces/web/static/brand/gleepglorp_med.png" alt="GleepGlorp AI" width="280">
</p>

# GleepGlorp AI

<p align="center"><em>Orchestrate your own constellation of AI agents — local, customizable, yours.</em></p>

---

## What this is

GleepGlorp AI is a personal AI agent that runs on your own computer. You pick the language model, give an agent a goal in plain English, and it chooses tools, runs them, reads the results and keeps going until the work is done. Your data and settings stay on your machine.

## What it can do

- **Chats**: talk to an agent and open the full tool-call trace for any reply.
- **Agents**: set each agent's model, system prompt and which tools it may use.
- **Built-in tools**: 22 tools for files, shell and interactive terminal sessions, Python, web fetch, download and search, raw HTTP requests, and connector messaging.
- **MCP servers**: connect external Model Context Protocol servers over stdio or streamable HTTP. Local servers run in a sandbox on Linux.
- **Knowledge bases**: point at a folder and agents can search it. The index stays current as files change.
- **Connectors**: let an agent chat on Discord and Telegram. See [docs/connector-setup.md](docs/connector-setup.md).
- **Self-configuration**: an agent can propose edits to its own description and system prompt. It is off by default, and you can require your approval for each change.
- **Desktop window**: run it as a native window with a tray icon instead of a browser tab.

## Install

**Windows installer.** Download and run it. You need no Python and no command line. See [docs/windows-install.md](docs/windows-install.md).

**From source** (Python 3.11+, all platforms):

```bash
pip install -e ".[all-llms]"
the-one serve   # web UI at http://localhost:8484
```

Other commands: `the-one chat` (terminal chat), `the-one app` (desktop window), `the-one doctor` (check the runtime), `the-one rotate-api-credential`, `the-one version`.

### Desktop window

```bash
pip install -e ".[gui]"
the-one app
```

On Windows and macOS the window uses the system web view. On Linux it needs WebKitGTK:

```bash
sudo apt install python3-gi gir1.2-webkit2-4.1   # older distros: gir1.2-webkit2-4.0
```

Closing the window hides it to the tray, and Quit in the tray menu exits. Starting `the-one app` again focuses the running window instead of opening a second one. With no web view available, it opens your system browser instead.

## Getting started

1. Open the app and go to **Settings → Providers**. Choose **Add provider** and enter the details for your model provider.
2. Go to **Agents**, choose **New**, and pick that provider and a model.
3. Go to **Chats**, choose **New chat**, pick your agent and start talking.

## Supported LLM providers

- **Ollama**: local models, no API key. Use `http://localhost:11434` (the `/v1` suffix is added for you). Pull a model first, for example `ollama pull llama3.2`.
- **OpenAI-compatible**: any server that speaks the OpenAI API, with its base URL and optional key.
- **OpenAI**: GPT models, with an API key.
- **Anthropic**: Claude models, with an API key.
- **Anthropic plan**: Claude through your Pro or Max subscription. Sign in from Settings → Providers, no API key.
- **OpenRouter**: many providers behind one API key.

API keys are encrypted at rest. You can rotate the key from **Settings → Encryption**.

## Security

GleepGlorp AI is a single-user, local-only tool. Every route except `GET /api/live` needs a local credential, and the server accepts requests only from local origins. See [SECURITY-MODEL.md](SECURITY-MODEL.md) for the threat model.

## Accessibility

The UI targets WCAG 2.1 AA: it works from the keyboard, respects reduced-motion settings, and keeps contrast on both light and dark themes. To report a problem, [open a GitHub issue](https://github.com/msieurthenardier/the-one/issues) with the `accessibility` label.

## Developing

```bash
pip install -e ".[all-llms,dev]"
make up           # run the app in the background
make test-unit    # unit tests
ruff check the_one/ tests/ scripts/ && ruff format --check the_one/ tests/ scripts/
```

Read [CLAUDE.md](CLAUDE.md) for the working rules and [the_one/agents.md](the_one/agents.md) for architecture and module internals. [SECURITY-MODEL.md](SECURITY-MODEL.md) covers the security choices. The project is planned with [Mission Control](https://github.com/msieurthenardier/mission-control), and its mission records live in [`missions/`](missions/).
