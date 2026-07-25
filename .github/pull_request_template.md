## Checklist

Confirm each item before you request review.

- [ ] `./scripts/validate-all.sh` exits 0.
- [ ] `python3 scripts/ste-lint.py <changed files>` exits 0.
- [ ] `shellcheck scripts/*.sh` exits 0.
- [ ] The description states the observable behavior this change adds or alters.
- [ ] The prose follows ASD-STE100. See the Writing style section of `AGENTS.md`.
- [ ] The change adds no internal reference. It names no ticket, no internal
      hostname, no internal repository, and no server-side class name.
- [ ] No skill hardcodes a server hostname or a bare URL.
- [ ] Every tool name in skill prose stays bare, with no client prefix.
- [ ] Skills still only propose actions. No change here executes a trade or another account-changing action on its own.
- [ ] Every manifest pins one released version number.
