---
name: GitHub publishing through an integration
description: Why a connected GitHub account may not make git push work in the shell
---

A GitHub integration can authorize REST API writes without changing the shell's Git HTTPS credentials. A failed `git push` is not proof that the connection cannot publish a repository update; verify its API access before asking for credentials.

**Why:** The workspace's Git remote rejected an existing invalid HTTPS credential even after the GitHub connector was authorized. A non-forced Git Database API ref update published the requested file tree, but produced a different commit ancestry from local Git.

**How to apply:** Prefer an authenticated Git transport when available. If publishing through GitHub's Git Database API, compare the generated tree hash to the local commit tree, use a non-forced ref update, and acknowledge that the local branch will not be directly pushable until histories are reconciled. Never expose connection credentials to shell commands.