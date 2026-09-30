---
name: Vite bundle module loading
description: A standalone Vite browser entry can retain import.meta even when it has no imports or exports.
---

Load custom Vite browser bundles that use `import.meta` with `<script type="module">`. `defer` on a classic script does not make `import.meta` valid.

**Why:** A classic script fails before mounting React with `Cannot use 'import.meta' outside a module`, leaving the page functional-looking but omitting the auth UI.

**How to apply:** When adding a separately built Vite entry to server-served HTML, inspect it in a real browser and use a module script tag; confirm that the entry mounts before relying on API smoke tests.