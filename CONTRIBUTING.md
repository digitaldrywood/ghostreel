# Contributing

ghostreel is a teaching reference. Contributions that make the method clearer or the
example pipeline more correct are welcome.

## Ground rules

- **No secrets, ever.** No keys, tokens, or private data in code, commits, or issues. The
  only key surface is `.env` (gitignored) and `.env.example` (placeholders only).
- **Keep examples small and readable.** This repo is read by humans and AI assistants
  learning the method. Clever beats long, but clear beats clever.
- **No labeled AI images.** Anything with text/labels in an example must be a capture,
  diagram, or HTML — not an AI image. That's the whole point.
- **Match the voice.** Docs are direct and plain. No filler, no AI-crutch phrases.

## Workflow

1. Fork and branch.
2. Make the change; run `python3 -m py_compile src/*.py` and `node --check src/*.mjs`.
3. Open a PR explaining what got clearer or more correct.

## Scope

Bug fixes, clearer docs, additional small examples (a Mermaid diagram step, a Piper
rough-cut helper, a caption generator) are great. A full framework is not — keep it a
reference you can read in one sitting.
