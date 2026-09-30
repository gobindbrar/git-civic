---
name: Artifact workflow working directory
description: Managed artifact workflow commands start in the artifact's directory, unlike root-level deployment commands.
---

Managed artifact development commands start with the working directory set to the artifact directory. A command that changes to `artifacts/<slug>` again will fail because the relative path no longer exists there. Production commands may be evaluated from the workspace root, so make their working directory explicit.

**Why:** A migration's first managed workflow start failed even though the Python app and dependencies were correct; the command performed a redundant relative directory change.

**How to apply:** Use artifact-relative commands for development services and explicit root-to-artifact paths for production build/run commands. Verify the actual workflow output after a metadata change.