# 17 — Design: run-time enforcement of app capabilities

Status: **proposal.** Nothing here is built yet. Install-time checks already exist
(`APP_CAPABILITIES` in `ai/aios.py`: only `fs:/ai/state` is accepted, and `net:*` is
refused). This document covers what happens after install, when an app actually runs.

## 1. What is true today

- An installed app's entry in `/ai/bin` is an ordinary executable. Running it gives it
  the caller's full permissions inside the VM, so the manifest does not limit it.
- The acceptance test runs with `AIOS_ALLOW_NETWORK` removed from its environment. That
  is a convention that the `net` tools check. It is not an operating-system block.
- The shell tool refuses commands that match a network-command pattern unless
  `AIOS_ALLOW_NETWORK=1`. Pattern matching is easy to evade, so this is a guardrail,
  not a boundary.
- `docs/09-SECURITY-MODEL.md` describes a sandbox with no network namespace. That is the
  target, not the current state.

So "network disabled" in the install prompt is currently a promise the harness keeps,
not something the kernel enforces. The design below makes the promise real.

## 2. Goals

1. An app can do only what its manifest declares, while it runs, whether it was started
   by the harness, the console, or a shell.
2. Enforcement is not optional and does not depend on the app's cooperation.
3. The first version works on the Alpine guest with no new host dependencies.
4. Failures are visible: a denied operation is logged and the app sees a clear error.

## 3. Guest facts (checked 2026-10-20)

- Kernel `6.12.110-0-virt`; the active LSM list includes `landlock`.
- `unshare -n` fails for the `ai` user (uid 1001). Network namespaces need root, and `ai`
  has passwordless sudo, but the launcher should not depend on root.

## 4. Options

| Option | How | Pros | Cons |
| --- | --- | --- | --- |
| A. Wrapper launcher | `aios run-app NAME` starts the app with a `unshare -n` network namespace and a filesystem view limited to declared paths (bind mounts) | Uses tools already in Alpine (`unshare`, bind mounts); real kernel boundary for network | Needs root or user namespaces; paths via bind mounts need care |
| B. seccomp filter | Load a syscall filter that blocks `socket` and `connect` unless declared | Strong for network; no mounts | Harder to write for Python apps; path rules are not expressed by seccomp |
| C. Landlock (Linux ≥ 5.13) | Restrict filesystem access per process without root | Fine-grained paths; unprivileged | Kernel support on the guest must be checked; no network rules in older kernels |
| D. Keep the convention | Document the limits and rely on the review gate | Zero cost | Does not meet goal 2 |

**Recommendation (revised after the guest check):** Landlock is available and works without
root, so use **C** for filesystem paths. For network, use **B** (a seccomp filter that denies
`socket` and `connect` unless a `net:` capability is declared), which also needs no root.
Keep **A** (`unshare -n`) as a later option that needs a root helper, which would be a separate,
reviewed change.

## 5. Proposed behavior

- The harness and the console launch every installed app through `aios run-app NAME -- args`,
  never by calling `/ai/bin/NAME` directly. A PATH shim in `/ai/bin` can route direct calls
  through the same launcher.
- The launcher reads the registry entry (not the manifest on disk), so a changed manifest
  cannot widen permissions without a new install and approval.
- Empty `capabilities` means: no network, and filesystem access only to the app's own
  directory `/ai/apps/NAME` and `/ai/tmp`.
- `fs:/ai/state` adds read/write access to `/ai/state`.
- Every launch emits an audit event (`app_run`, with the app, version, and declared
  capabilities). Every denied access emits `app_denied`, so denials show up in the console.
- The acceptance test runs under the same launcher, so "tests pass" means "tests pass under
  the same limits the app will have".

## 6. Tests

- Launch an app that tries to open a socket: it fails, and the audit log has `app_denied`.
- Launch an app that writes outside its declared paths: it fails.
- Launch an app with `fs:/ai/state`: it can write there and nowhere else.
- The registry install gate runs the acceptance test through the launcher.
- The guest test suite runs these checks on the real VM kernel, not on the host.

## 7. Open questions

1. Landlock needs the ABI version the launcher targets; confirm which features the 6.12 guest
   supports before writing rules.
2. Should the model be able to call `run-app` directly? My recommendation: yes, but only for
   apps already in the registry.
3. Does a PATH shim break anything that calls `/ai/bin/NAME` with absolute paths?
4. Should the policy file for each app be the manifest alone, or a separate reviewed file?

## 8. Next steps

1. Build `aios run-app` with the seccomp network filter only, and test it on the VM.
2. Route the acceptance test and console launches through it.
3. Add Landlock filesystem limits once step 1 is proven.
