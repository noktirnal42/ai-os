# 18 — AI OS v2: plan and spec outline

Status: **proposal, emulator-only scope (revised).** Nothing here is built yet. Decisions needed are in §9.

## 1. Verdict on v1

The v1 experiment answered its narrow question: **can a bounded agent build and install
software inside a controlled VM, with a human gate?** Partly yes.

What worked (with evidence in git and the guest audit logs):
- The build-and-register loop: `mail` was built, its acceptance tests pass, and it installed
  through an approval prompt (sessions `20261020T003413Z-…`, `20261020T003708Z-…`).
- The safety gates: installs and removals need a human answer, the model cannot request
  approvals or remove apps, and unsupported capabilities are refused before the prompt.
- Reproducible evidence: 35 host tests, guest acceptance tests, audit logs per session.

What did not:
- **The model is the bottleneck.** The local 3B model ends runs as "partial" after successful
  work, and it loops on registry operations. The cloud model failed with 403, so Do mode was
  down for part of the day.
- **Installs are manual.** A human has to be at the console to approve each one. There is no
  `aios install` in the shell, and the console's `/install` path has not been tested live.
- **Capabilities are not enforced.** The manifest declares them, and install checks them, but a
  running app is not sandboxed. "Network disabled" is a convention, not a boundary.
- **No GUI, no kernel access, no user-facing docs.** The product is a terminal console inside
  a VM. A new user cannot yet build their first app without reading the harness code.

Conclusion: v1 proves the loop and the gates. It does not yet make the system pleasant to use,
and its agent is too weak to carry the build loop on its own.

## 2. Goals for v2

1. **A windowed desktop** that a newcomer can use without a terminal: a launcher, windows,
   a file browser, a text editor, a terminal, and a mail reader.
2. **An AI that can change the system.** It may read and write the system, build software, and
   propose kernel and driver changes. Freedom is granted by policy, not by lack of tools.
3. **Built-in getting-started material**: a first-run tour, guided "build your first app"
   tutorials, and a reference for the app contract, all inside the OS.
4. **Batteries included**: a usable default set of apps and settings, so the first session does
   not start from an empty system.
5. **Built and tested in the emulator.** Bare-metal or USB delivery is out of scope for now.

## 3. Hard constraints (emulator-only scope)

- **Target:** the Alpine aarch64 guest on QEMU/HVF, driven only through `emulation/vm.sh`
  (`docs/13`). No bare-metal or USB boot in v2 scope.
- **Hardware in the emulator:** 4 vCPU and 4 GB RAM by default, a 20 GB disk, no GPU device,
  and `-display none` today. The guest has about 17.6 GB free and Alpine 3.22 with `sway` and
  `foot` available in the package index.
- **Graphics:** there is no accelerated GPU in the emulator. The desktop renders in software
  (wlroots pixman). This is acceptable for v2 and is the same limit a real M3 Pro has today.
- **Accelerators:** no GPU or NPU is available to the guest. Model inference stays on the macOS
  host (Metal and Neural Engine) and is reached through `10.0.2.2`, as in v1.
- **Visible window:** a real on-screen desktop needs a display device in the QEMU definition
  (for example `virtio-gpu` plus a display backend). That changes `emulation/vm.sh` and the VM
  spec in `docs/13`. Per `AGENTS.md` rule 8, I'll flag that change before making it.
- **Testing without a window:** a headless compositor (`WLR_BACKENDS=headless`) can render frames
  that a test captures and checks. This needs no change to the VM and is the first step.
- **Host safety:** all v2 work stays inside the VM and the repo. The emulator keeps the host
  disks, including the 2 TB workspace drive, out of reach, as in v1.

## 4. Architecture (proposed)

| Layer | Choice | Why |
| --- | --- | --- |
| Base | Alpine (aarch64, musl) live image in emulation; Asahi-compatible kernel for the stick | Keeps v1's target. The stick kernel must boot M3 hardware, so it comes from Asahi's tree |
| Init and services | OpenRC or runit | Small, scriptable, already on Alpine |
| Display | Wayland compositor (e.g. `sway` with `wlroots` software renderer) | Works without GPU acceleration; a small, auditable compositor |
| Toolkit | Single toolkit for built-in apps (GTK4 or Qt6) | Consistent look and one set of tutorials |
| Agent | Harness from v1, rebuilt as a service with a window (chat pane) | Reuses the audit log, tools, and gates |
| Packages | v1 `aipkg` format, extended with a signed manifest | Keeps the install story from v1 |
| Model | Local model by default; cloud only when enabled and keyed (v1 providers) | Works offline; cloud is an explicit choice |

## 5. The agent's freedom model

- **Policy file, not code.** The AI's permissions are a single reviewed policy: what it can write,
  which kernel modules it can load, which network hosts it can reach.
- **Every privileged action is logged** to a session audit file, shown in the desktop's activity
  window.
- **Kernel changes are staged.** The AI builds a kernel module or patch in a sandbox, runs its
  tests in the emulator, and only then offers it for loading. Loading it on the stick still asks
  you, unless you turn that off in the policy.
- **Rollback is the default recovery.** Every change is checkpointed, and a reboot returns to the
  last known good state.

## 6. Built-in getting-started material

- **First-run tour** in the desktop: what the system is, what the AI can and cannot do, how to
  stop it.
- **Three guided tutorials** that the AI runs with you, each ending in a working app:
  1. A notes app (text file, search, a window).
  2. A tiny calculator with a test.
  3. A small network-free tool of your choice, installed through the approval flow.
- **Reference** in the OS: the app contract (manifest, tests, capabilities), the approval flow,
  and the audit log format. Written as versioned Markdown, shipped in the image.
- **"Ask the OS"**: a help window answered from the bundled reference, not from memory.

## 7. Phases (emulator-only)

- **Phase 1 — headless desktop core.** Install `sway` and `foot` in the guest. Start a headless
  compositor, open one terminal, and capture a frame with `grim`. Gate: a test script captures a
  frame and checks that the terminal window exists in the compositor's tree.
- **Phase 2 — on-screen desktop.** Add the display device to the VM definition (after a flagged
  spec change to `docs/13`), so the desktop shows in a macOS window. Gate: a window appears and
  responds to input.
- **Phase 3 — batteries included.** Default apps: terminal, file browser, text editor, mail reader
  (`mail`), calculator, settings, and the tutorials from §6.
- **Phase 4 — the agent in the desktop.** The v1 harness runs as a service with a chat window and
  approval dialogs. The freedom model from §5 is implemented and tested.
- **Phase 5 — release image.** A reproducible guest image with a checksum, and a snapshot of the
  finished state.

Each phase has a gate and a rollback, following the v1 bootstrap roadmap (`docs/06`).

## 8. Out of scope for v2

- Live USB, bare-metal boot, and anything that touches this Mac's disks or boot policy.
- GPU and NPU acceleration in the guest. Not available in the emulator or on this Mac's Linux path.
- Network-connected mail (IMAP). `mail` stays local until you decide the credential and network
  model.

## 9. Decisions I need from you

1. **Visible window:** may I add a display device to the emulator (a flagged change to
   `emulation/vm.sh` and `docs/13`), or stay headless until the frame tests pass?
2. **Freedom model:** is the bounded design in §5 right, or should the AI's kernel access be
   narrower?
3. **Model placement:** keep the model on the Mac host (faster, uses Metal) as in v1, or move a
   small model into the guest for a fully self-contained emulator?
4. **First release scope:** the three tutorials and default apps in §2 and §6, or a smaller first cut?

## 10. Risks

| Risk | Mitigation |
| --- | --- |
| Software rendering is too slow for the desktop | Keep the UI simple; measure frame times in phase 1 |
| The 3B local model is too weak for the agent | Use a stronger model for build tasks, or a staged pipeline (spec → build → test → gate) |
| Adding a display device changes the VM definition | Flag it as a spec change in `docs/13` before making it (AGENTS rule 8) |
| The AI damages the guest it should not touch | Snapshots before risky steps; `vm.sh rollback` for recovery |
| Kernel changes break boot | Test every kernel change in a snapshot; keep the last good image |

## 11. Progress log

- **Phase 1 (headless desktop core):** done. `ai/desktop/tests/run.sh` passes.
- **Display (flagged in `docs/13`):** done. `VM_DISPLAY=cocoa` opens a macOS window with the desktop.
- **Input:** keyboard and tablet reach sway through udev and libinput. Live presses in the macOS window not yet confirmed.
- **Phase 2 (default apps), first slice:** `micro` (editor), `ranger` (file browser), `fuzzel` (launcher), and `nano` installed. Keybindings: Alt+Enter terminal (verified: opens a second terminal), Alt+d launcher, Alt+e file browser, Alt+t editor, Alt+w welcome, Alt+q close, Alt+Shift+e exit. The welcome screen (`/ai/bin/welcome`, source `ai/desktop/bin/welcome`) shows on first start.
- **Phase 2 (default apps), done in the emulator:**
  - Mail: a GTK4 window (Alt+m) with an INBOX list, read and unread, and Compose (Ctrl+N). Compose queues to Outbox; nothing is sent. Verified on screen.
  - Calculator (Alt+c) over the `calc` app. Settings (Alt+s): system and model status, and the terminal font, which new terminals read from `~/.config/foot/foot.ini`.
  - Guided tutorial (`tutorial`): builds a `notes` app step by step, runs its acceptance test, and installs it through the approval prompt. The non-interactive path is verified. The interactive install is waiting for the user.
  - Agent: Alt+a opens a chat window in Chat mode. Ctrl+D (or the header toggle) switches to Do mode, where approvals appear in the window. Verified on screen: a request showed its full question, and Decline was recorded in the audit log.
  - Alt+Shift+a opens the terminal console (Do mode with the full console).
- **Phase 2 (desktop shell), done:** an app menu on Alt+Space, window keys (focus, move, fullscreen, floating, splits), workspaces 1 to 4, and a top bar with the model, free memory, and time.
- **Not yet:** the freedom model in section 5 (a policy file, staged kernel changes, checkpoints and rollback, and the activity window), and the release image in phase 5.
- **Known gaps:** keyboard and mouse presses in the macOS window are not yet confirmed; the chat window's Do-mode has not been run through a full approve path on screen (only decline has been); `mailview` and the CLI mail view are kept as fallbacks.

