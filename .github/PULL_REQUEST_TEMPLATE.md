## What this PR does

<!-- One sentence; the headline that should become the squash-merge
     subject line. Imperative tense, ~70 chars. -->

## Why

<!-- The user / engineering problem it solves. Link any related issue
     or ROADMAP.md row. -->

## How

<!-- The shape of the change. Files touched, key decisions, anything
     non-obvious about the approach. -->

## Roadmap impact

<!-- If this lands a 📋 next / 🔮 planned row, flip it to ✅ shipped
     in ROADMAP.md and describe what actually landed. -->

## Tests

- [ ] `pytest packages/kerf-<plugin>/` (touched plugins) passes
- [ ] `npm test` passes
- [ ] `npm run lint` clean
- [ ] Manual: <what you exercised in the running app>

## Checklist

- [ ] Commit messages in imperative tense, ~70 chars
- [ ] Docs updated (`llm_docs/` for new LLM tools, `docs/` for
      user-facing docs)
- [ ] No breaking changes to existing routes / file-kind schemas
      without a migration story
- [ ] No new heavy runtime dep without strong motivation (optional
      extras are fine)
- [ ] Anything proprietary lives under `kerf-billing/`, `kerf-cloud/`,
      or `src/cloud/`

## Screenshots / output

<!-- For UI changes, drop in a before/after screenshot. For backend
     changes, paste relevant test output or curl examples. -->
