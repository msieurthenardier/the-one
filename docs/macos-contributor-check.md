# macOS contributor check

GleepGlorp AI's macOS app is built and tested on a hosted Apple Silicon runner, but a runner has
no person at it. Three things only a real Mac shows: **Gatekeeper's approval flow** for a
downloaded app, **real clicks on the Dock icon**, and **how it feels on a real display**. This
checklist is how you help verify them. It takes about 30 minutes and needs no knowledge of the
project. It is the written form of the behavior test
[`tests/behavior/macos-app-install.md`](../tests/behavior/macos-app-install.md); the numbering
matches its steps.

**What you need:** an Apple Silicon Mac on macOS 14 or later (note the version: Apple menu ›
About This Mac, or run `sw_vers` in Terminal), a user account you are happy to give GleepGlorp AI
data to, and a way to send back screenshots (Cmd-Shift-4, then click and drag) and pasted
Terminal output.

**What this does to your Mac:** it installs GleepGlorp AI in `/Applications`, creates
`~/Library/Application Support/the-one/` and `~/Library/Logs/GleepGlorp AI/`, and listens on
`127.0.0.1:8484` (only your own Mac). Step 11 removes the app; it leaves the data folder unless
you ask to delete that too. It touches nothing else. **Never send the contents of
`api-credential`**; the commands below print only its harmless `loc_<id>` prefix.

## Get the builds

You need three `.dmg` files, versions N, N+1 and N+2, from a dispatched run of the repository's
`macos-packages.yml` workflow (mode `lifecycle` or `full`): open the run on GitHub, **Artifacts**,
**`macos-dmg`**. The person running the check will tell you which run and give you the sha256
for each file. Download them **with Safari** (or your usual browser) from the artifact page, not
by copying them with `scp` or AirDrop, so macOS marks them as downloaded. That mark is what
triggers Gatekeeper, and it is part of what we check. An artifact is a zip containing the
`.dmg`; unzip it first.

Check each file: `shasum -a 256 ~/Downloads/GleepGlorp_AI-*-arm64.dmg`.

## Commands to paste

Open Terminal. These are used in the steps below. Paste each as a whole.

**State** (the window, tray and version):

```bash
CRED=$(cat "$HOME/Library/Application Support/the-one/api-credential")
echo "credential prefix: ${CRED%%.*}"
curl -s -H "Authorization: Bearer $CRED" http://127.0.0.1:8484/api/window/state; echo
```

It prints `credential prefix: loc_...` (only the id; never the secret) and a line like
`{"desktop":true,"mode":"window","visible":true,"mapped":null,"tray":"dock","version":"0.11.8","pid":1234}`.
If the app is not running, `curl` prints nothing or fails; that is the expected answer in the
steps that say "refused".

**Alive?** `curl -s http://127.0.0.1:8484/api/live; echo` should print `{"status":"ok"}` while the
app runs, and nothing (connection refused) after it quits.

**Agents** (to see your data):

```bash
curl -s -H "Authorization: Bearer $CRED" http://127.0.0.1:8484/api/agents; echo
```

**Create an agent** (step 8), in the app: **Library › Add › Model provider**, choose
**Ollama**, accept the defaults and save (nothing needs to be running); then **Agents › New**,
name it `mac-check-agent`, pick that provider, type any model name, and choose **Create**.

**Doctor** (step 10):

```bash
"/Applications/GleepGlorp AI.app/Contents/MacOS/the-one" doctor
```

## The steps

For each step, do the action, check the expectation, take the screenshots listed, and note
anything that differs. If a step fails, **note it and carry on** where you can; do not repair
anything by hand.

### 1. Download and open the disk image
Download build N in Safari and double-click the `.dmg`.
**Expect:** a Finder window showing **GleepGlorp AI** and an **Applications** shortcut.
*Screenshot:* the window.

### 2. Install and the first refusal
Drag **GleepGlorp AI** onto **Applications**, eject the disk image, then open the app from
Applications.
**Expect:** macOS refuses: a dialog "GleepGlorp AI Not Opened" (on macOS 15 with only **Done**
and **Move to Trash**) or an older-style "cannot be opened" dialog. No app window appears.
*Screenshot:* the dialog, with its exact wording and buttons. Note your macOS version.

### 3. Approve it and open it
Click **Done**, then **System Settings › Privacy & Security**, scroll to **Security**, click
**Open Anyway**, authenticate, and click **Open** in the next dialog. (See
[macos-install.md](macos-install.md) section 3.)
**Expect:** within 30 seconds a GleepGlorp AI window shows the Chats start page ("Hello."), the
Dock shows the brand icon, and no second Gatekeeper prompt appears later.
*Screenshots:* the Privacy & Security screen showing **Open Anyway** (or whatever is there
instead), the confirm dialog, and the running app with the Dock visible. Run the **State**
command and paste its output.

### 4. Close with the red button
Close the window with the red button and wait 5 seconds. Run **State**.
**Expect:** the window is gone, the Dock icon stays with its running dot, and the state shows
`"visible":false` and `"tray":"dock"`. No notification appears.
*Screenshot:* the Dock. Also try **Cmd-W** on the window once and note whether it also hides it.

### 5. Click the Dock icon
Click the Dock icon. Run **State**.
**Expect:** the same window returns in front, `"visible":true`, and the `pid` is the same as
in step 4.
*Screenshot:* the window back, and the state output.

### 6. Resize, move, Cmd-Q
Resize the window and drag it to a new spot. Press **Cmd-Q**.
**Expect:** the app quits within 10 seconds, the Dock's running dot is gone, **Alive?** prints
nothing, and no "quit unexpectedly" dialog appears.
*Screenshot:* the window before quitting, and the Dock after.

### 7. Reopen: size and position
Open the app from Applications again.
**Expect:** it opens at the size and position from step 6, with no Gatekeeper prompt.
Then right-click the Dock icon, choose **Quit**, and expect the same clean exit as step 6.
*Screenshot:* the reopened window.

### 8. Upgrade N to N+1
Open the app and create an agent (see **Create an agent** above). Quit with Cmd-Q. Download the N+1
`.dmg` in Safari, open it, drag the app onto **Applications**, and choose **Replace**. Open the
app (approve it again if macOS asks, as in step 3).
**Expect:** Finder asks to replace; afterwards the window opens, **State** shows the N+1 version,
and **Agents** lists `mac-check-agent`.
*Screenshots:* the replace prompt; the app. Paste both outputs.

### 9. Replace while running (N+1 to N+2)
With N+1 **running**, download N+2 and drag it over the app in Applications **without quitting**.
Then open it from Applications. This step records what happens; the install guide says not to do
it, because the running copy can crash when its bundle is swapped.
**Record:** whether Finder let you replace, whether a crash dialog appeared, what window you see,
and the `version` and `pid` from **State** afterwards (and from **Agents**, that the data is
intact). Expect the data to be intact either way. Then press Cmd-Q, open the app again and expect
N+2 to answer **State**.
*Screenshots:* anything that appears; the final **State** output.

### 10. Doctor
Run the **Doctor** command.
**Expect:** it ends `RESULT: PASS` and includes `tray: dock` and a `path:` line. On a Mac with no
Python 3 installed it may instead fail only the `python interpreter` check with a message telling
you to install Python 3; that is also acceptable, and worth noting.
*Paste* the whole output.

### 11. Remove
Quit the app. Drag **GleepGlorp AI** from Applications to the Trash. Then list the data folder:

```bash
ls "$HOME/Library/Application Support/the-one/"
```

**Expect:** the app is gone from Applications, and the folder still holds `the-one.db` and
`api-credential`. Finally tell us whether you are happy to delete the data folder; if so, move
`~/Library/Application Support/the-one/` and `~/Library/Logs/GleepGlorp AI/` to the Trash.
*Paste* the `ls` output.

## What to send back

- The macOS version and chip (`sw_vers`; Apple menu › About This Mac).
- The three sha256 values and which run the files came from.
- For each numbered step: pass or fail, the screenshots listed, pasted output, and any surprise.
- The last 50 lines of `~/Library/Logs/GleepGlorp AI/app.log`
  (`tail -n 50 ~/Library/Logs/GleepGlorp\ AI/app.log`), if anything went wrong.
- Anything the guide ([macos-install.md](macos-install.md)) said that did not match what you saw.
