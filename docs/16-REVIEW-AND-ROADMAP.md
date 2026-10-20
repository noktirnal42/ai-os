# 16 — Review: why installs stall, and how to make building feel better

Status: **review and proposal, not a spec.** Nothing in `docs/01`–`docs/15` was
changed. This file records what was observed on 2026-10-19 and what to do next.
Per `AGENTS.md` rule 8, any change to a spec should be flagged separately.

---

## 1. Summary

The build half of the loop works. The `mail` app (an mbox reader with import,
list, search, read, compose, and folders) was written inside the guest, and its
acceptance suite passes (`MAIL_ALL_PASS`). The install half does not work from the
console. The cause is an approval channel that no human can answer:

- The TUI launches Do-mode runs with `stdin=subprocess.DEVNULL`
  (`ai/aios_tui.py:361`).
- `Session.ask_human` calls `input()` (`ai/aios.py:476`). With DEVNULL, that raises
  `EOFError`, which is caught and returned as `approved: False`
  (`reason: non-interactive session`).
- The TUI shows "Waiting for your decision" for `ask_human` events
  (`ai/aios_tui.py:27`), but no prompt is ever shown and no answer can be sent.

So every install request is denied before the human sees it. The gate is safe by
default, but the default makes it unusable in the product's main interface.

## 2. What was verified

| Check | Result |
| --- | --- |
| `vm.sh status` | VM running, uptime 17h, model endpoint reachable on host port 11434 |
| `/ai/apps/mail` tests (`sh /ai/apps/mail/tests/run.sh`) | rc 0, `MAIL_ALL_PASS` |
| `registry query mail` | `null` (not registered) |
| `aios registry install mail </dev/null` | rc 1: `Approve registering mail v0.1.0? … [y/N] registry: app install was not approved by the human` |
| Session `20261019T210433Z-1c72a688` | Model called `registry install mail` → rc 1. It then called `ask_human` with options, and the model ended without tool calls. Verdict: `partial`, `verified: false`. |
| Sessions `20261019T230708Z`, `…230737Z`, `…230803Z` | Each contains only `session_start`. No tool calls and no verdict. Cause not determined; check `/ai/state/sessions` and the process log before assuming. |

Things I did **not** verify, and would not do without you:

- I did not approve the install. Approving it is the human gate's job, and
  piping `y` into the guest would bypass it. The app is still unregistered.
- I did not run a new model-driven Do task. It costs model calls against the
  configured NVIDIA NIM endpoint.
- I did not test an interactive approval from a real TTY (`vm.sh ssh`, then
  `aios registry install mail`, then `y`). That is the path the docs imply
  works, and it is the first thing to check.

## 3. Root cause and related problems

### 3.1 The approval channel is broken in the TUI (blocking)

- `run_child` passes `stdin=DEVNULL`. Nothing can be written to the child's stdin.
- `ask_human` is used for two things: the registry install gate
  (`aios.py:439`) and the model's own `ask_human` tool (`aios.py:341`). Both are
  denied in the TUI.
- Commit `1477bf0` changed the check from `isatty()` to a `try/except` around
  `input()`. That fixed the `ssh` case without `-t`, where the old check was
  wrong. It did not fix the TUI case, because both paths still end at `EOFError`.

### 3.2 The model keeps going after a denied gate

After the denial, the model called `ask_human` and then stopped without a tool
call. The harness recorded a `partial` verdict and left the human with no clear
next step. A denied install should end the run with a plain statement, such as
"Install needs your approval: run `aios registry install mail` in a terminal."

### 3.3 The approval prompt is not informative enough

The gate shows the name, version, entry path, and test path. It does not show the
test output, the test's list of checks, the app's `capabilities`, or a diff. The
human is being asked to trust a name.

### 3.4 Docs disagree about Do-mode limits

- `README.md` says 32 tools / 15 minutes.
- `docs/15-FIRST-RUN-AND-TUI.md` says 40 tool calls / 25 minutes.
- The TUI actually passes `--max-tools 40 --max-seconds 1500` (`aios_tui.py:105`).
- The `run` default in `aios.py` is 200 tools / 2700 seconds.

The README is wrong. Fix it when the other items change.

### 3.5 Evidence is hard to read

`ai/VALIDATION.md` is about 440 lines of dated logs. It answers "did this happen
once?" but not "what is true now?" There is no single place that lists which
apps are registered, which tests pass, and what the last green run was.

### 3.6 Smaller items

- `mail` has `"capabilities": []`, but nothing enforces capabilities yet.
- `mail`'s test writes to `/tmp`. Fine for now, but acceptance tests should use a
  per-run temp directory.
- `ai/apps/calc/build/calc` and `__pycache__` directories are checked into the
  tree. Ignore them.

## 4. Making it work (ordered)

1. **Give approvals a real channel.** Recommended design:
   - `run_child` uses `stdin=PIPE`.
   - `ask_human` writes a structured event before blocking, such as
     `{"ev":"gate_request","id":…,"question":…,"options":[…]}`.
   - The TUI shows an inline `[y/N]` prompt, then writes `y\n` or `n\n` to the
     child's stdin.
   - Denial still happens on EOF, so an unattended run stays safe.
   - Add a test that drives a fake child through the gate in both directions.
   This is a small change in two files plus a test. It is the single fix that
   unblocks installs from the console.
2. **Make a denial end the run.** When a gate is denied, end with
   `verdict: blocked_on_human` and the exact command to run. Do not let the model
   continue.
3. **Make install a first-class command.** `aios install <app>` runs the same gate,
   test, and registry write as the model's tool. The model and the human then use
   one code path, and it can be tested without a model.
4. **Show the evidence in the gate.** Print the last acceptance output (or its
   summary) and the declared capabilities before asking.
5. **Fix the Do-mode limits in the README** (3.4).

## 5. Making building and installing better

The current loop is free-form: a model chooses shell commands until it decides it
is done. That makes it hard to predict, hard to watch, and easy to stall. A more
reliable shape is a fixed pipeline with the model filling in stages:

```text
spec → scaffold → build → test (bounded fix loop) → checkpoint → gate → register → verify
```

- **Spec first.** The task starts from a short spec file (`/ai/apps/<name>/SPEC.md`)
  with acceptance cases. The model writes the tests from the spec before the code.
  Once the tests are green, the model cannot edit them without a new gate.
- **Stage-aware TUI.** Show the stage and the one thing being waited on
  (`build: 2/5 tests`, `waiting: your approval`). Stop printing raw tool events
  as the main view.
- **Checkpoint before register.** `vm.sh snapshot` (or the in-harness checkpoint)
  before every install, and an automatic rollback on failure.
- **Install is a verb.** `aios install <app>`, `aios remove <app>`, and
  `aios doctor` (re-runs every registered app's tests). These are the same
  commands for the model, the TUI, and a human at a shell.
- **Keep the model budget visible.** The mail build used a cloud model. Show the
  model name, token use, and wait time per stage, so a slow build is not mistaken
  for a hung one.

## 6. Reimagining the project

Keep what is already right: bounded tools, an append-only session log, a human
gate, and the emulator as the lab. Change the unit of work.

1. **The unit is an app, not a chat.** The primary command is
   `aios build "<spec>"`, which runs the pipeline in §5 and produces an app, a
   test report, and an install prompt. Chat stays as a side panel for questions.
2. **Deterministic orchestrator, model in the middle.** Code owns the stages,
   budgets, gates, and checkpoints. The model only proposes file contents and
   fixes inside a stage. Today the model owns the whole control flow, so the
   harness can only observe it.
3. **Typed tools per stage.** Replace general `shell` with `write_file`,
   `run_tests`, `install`, and `query` for most work. Keep `shell` for a narrow
   debugging case.
4. **Declared, enforced capabilities.** A manifest says which paths, network
   hosts, and commands the app may use. The sandbox enforces the list, and the
   gate shows it. `mail` already has the field; it should mean something.
5. **Evidence generated, not written.** Each install writes a small report
   (tests run, outputs hashed, model used, time, checkpoint tag). `VALIDATION.md`
   becomes an index generated from those reports.
6. **One CLI.** `aios` with `build`, `install`, `remove`, `doctor`, `run`,
   `approve`, `rollback`, and `status`. The TUI is a front end over the same
   commands and the same event stream.

The first real test of this design is the `mail` app: it already has a spec
(import, list, search, read, compose, folders), a passing test suite, and a
reason to install.

## 7. Suggested order of work

1. Approval channel in the TUI (§4.1), with a test. **Unblocks installs.**
2. `blocked_on_human` verdict (§4.2) and the README limits fix (§3.4).
3. `aios install` / `aios doctor` (§4.3, §5), and install `mail` through them.
4. Gate shows evidence and capabilities (§4.4).
5. Spec-first pipeline and stage view (§5). Larger; plan it as its own phase.
6. Generated evidence reports replace hand-written `VALIDATION.md` entries.

## 8. Open questions

1. Approval UX: inline `[y/N]` in the TUI (recommended), or a separate
   `aios approve` shell command?
2. Should the model's own `ask_human` tool stay, or should only the harness raise
   gates? (The model asking "should I proceed?" mid-task is mostly noise.)
3. Build tasks currently use a cloud model. Keep that, or move builds to the
   local Ollama model and keep cloud for review?
4. Is `mail` the first app you want installed, or should the first install test
   use a smaller app such as `textstats`?

---

## Update 2026-10-20: why the console showed no approval prompt

- The latest console runs (`20261020T002339Z…`, `…002413Z…`) stopped right after
  `session_start`. The model call failed with `HTTP 403 Forbidden` from the default
  NVIDIA NIM endpoint (`{"detail":"Authorization failed"}`). Do mode never reached
  a tool call, so no approval could be requested. The earlier `23:07` sessions were
  probably the same failure; their cause is not confirmed.
- This is a model-access problem, not an approval problem. Fix it by picking another
  provider with F3, or by renewing the NVIDIA key and running `emulation/sync-keys.sh`.
- With the local Ollama model (`qwen2.5-coder:3b`), the harness emitted
  `gate_request` events for both the registry gate and the model's own `ask_human`
  call. With stdin closed, both were denied as intended.
- New finding: the small model calls `ask_human` on its own and asks the human to
  approve things it has no reason to ask about. That is the open question in §8.2.
  Consider removing `ask_human` from the model's tool list and keeping gates in the
  harness.
