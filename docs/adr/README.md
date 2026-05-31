# Architecture Decision Records

This directory holds ADRs — short, dated, factual records of significant architectural decisions made during this project's evolution.

## What an ADR is

An ADR captures a decision that:

- Was contested (multiple options were considered).
- Shapes the code beyond a single function (will influence future sessions' choices).
- Has a "why" that future maintainers need to know to avoid re-litigating the same question.

ADRs are written for readers months or years later. Keep them factual, short, and free of rhetorical flourish.

## Format

Each ADR is a single markdown file in this directory named `NNNN-short-slug.md`, where `NNNN` is the next four-digit sequence number.

Required sections:

- **Title** — what the decision is, in a sentence.
- **Status** — `Accepted`, `Superseded by NNNN`, or `Rejected`.
- **Date** — `YYYY-MM-DD` the decision was accepted.
- **Context** — the situation that forced the decision. Concrete, not abstract.
- **Decision** — what was chosen. Direct, no hedging.
- **Consequences** — what changes as a result. Both intended and accepted-tradeoff consequences.
- **Alternatives considered** — the other options and why they were rejected.
- **References** — links to commits, CHANGELOG entries, investigation reports, code locations.

Optional sections (when relevant):

- **Open questions** — things this decision intentionally leaves unresolved.
- **Revisit triggers** — concrete events that should prompt reopening the decision.

## When to add an ADR

Add an ADR when:

- A session has hit an architectural wall and needs to record why the wall is real.
- A decision was made between options that have similar plausibility (so future readers don't pick differently by accident).
- A code feature exists intentionally that looks like technical debt at first glance.

Don't add an ADR for routine implementation choices. The bar is "would the next session re-derive the same question if this weren't written down?"

## How to read an ADR

If you see a comment like `# See docs/adr/0001-...` in code, read that ADR before changing the surrounding code. The annotation exists because someone before you investigated the area and decided the current shape is correct. The ADR explains why.
