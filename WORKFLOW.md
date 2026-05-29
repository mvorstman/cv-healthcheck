# WORKFLOW.md

## Disciplined AI-Assisted Architecture Workflow

**Status:** Living document
**Last updated:** 2026-05-28
**Purpose:** Document the architecture and implementation workflow used for long-lived AI-assisted software projects.
**Scope:** Complex, architecture-sensitive systems where regressions may be difficult to detect and architectural decisions are expensive to reverse.

---

## 1. Introduction

This document describes the workflow currently used for architecture and implementation work in AI-assisted software projects.

The workflow evolved through practical experience while building long-lived systems with LLM collaborators (Claude, ChatGPT, Codex, etc.). It is not a theoretical methodology designed upfront. It is a set of practices that emerged in response to repeated real-world failure modes:

- plausible but incorrect AI synthesis,
- hidden regressions,
- architecture drift,
- implementation momentum after assumptions failed,
- and tests passing while real behavior was broken.

The workflow should be treated as:

- empirical,
- mutable,
- and continuously refined through practice.

This is not intended to be a rigid process for all software work.

---

## 2. Scope of Applicability

This workflow is intentionally heavyweight.

It is designed for:

- long-lived systems,
- architecture-sensitive platforms,
- foundational refactors,
- operational tooling,
- reporting systems,
- data normalization pipelines,
- platform abstractions,
- and systems where regressions may remain hidden for extended periods.

Examples:

- canonical artifact design,
- registry-driven architecture,
- persistence-layer redesign,
- normalization pipelines,
- cross-cutting platform abstractions.

---

## 3. When NOT To Use This Workflow

This workflow is usually excessive for:

- throwaway scripts,
- prototypes,
- experimentation,
- temporary tooling,
- small isolated utilities,
- cosmetic-only changes,
- low-risk UI tweaks,
- or highly reversible work.

For small tasks:

- direct implementation,
- lightweight verification,
- and rapid iteration

are often preferable.

The process cost must remain proportional to:

- reversibility,
- architectural risk,
- and regression impact.

---

## 4. Core Philosophy

### 4.1 Controlled Learning Under Uncertainty

The goal is not architectural certainty upfront.

The goal is:

controlled learning under uncertainty while minimizing irreversible mistakes.

The workflow assumes:

- understanding evolves during implementation,
- reality frequently differs from assumptions,
- and AI-generated reasoning is probabilistic rather than authoritative.

### 4.2 Reality Over Plausibility

LLMs optimize for plausibility.

Architecture work requires:

- grounding,
- consistency,
- and operational truth.

This creates a critical distinction:

Plausible != correct

and:

Code truth != system truth

The workflow therefore prioritizes:

- real-world verification,
- real datasets,
- real rendering,
- and operational behavior

over:

- implementation confidence,
- passing tests alone,
- or architectural elegance in isolation.

### 4.3 Surprise Is Architectural Signal

Unexpected behavior is not implementation noise.

Unexpected behavior often indicates:

- incorrect assumptions,
- abstraction mismatch,
- terminology instability,
- hidden coupling,
- or architectural drift.

The workflow explicitly treats surprise as a signal to stop and reassess.

---

## 5. Human / AI Division of Labor

This workflow exists partly because current LLMs have predictable failure modes.

The process is intentionally designed to compensate for them.

### 5.1 Human Responsibilities

The human provides:

- architectural judgment,
- domain understanding,
- prioritization,
- operational context,
- reversibility assessment,
- and final acceptance criteria.

The human is responsible for deciding:

- whether the architecture is appropriate,
- whether complexity is justified,
- and whether the resulting system matches real needs.

### 5.2 AI Responsibilities

The AI assists with:

- synthesis,
- implementation acceleration,
- structural analysis,
- exploration of alternatives,
- code generation,
- summarization,
- and large-context reasoning.

The AI is treated as:

- powerful,
- useful,
- fast,
- but non-authoritative.

### 5.3 Known AI Failure Modes

The workflow explicitly compensates for:

- confident incorrect synthesis,
- smoothing over ambiguity,
- vocabulary drift,
- abstraction inflation,
- local optimization that damages architecture,
- implementation continuation after assumptions fail,
- and "looks correct" output that fails against reality.

---

## 6. High-Level Workflow

```
SURVEY
    ↓
STEERING / ARCHITECTURAL DISCUSSION
    ↓
PRE-CLEANUP (if needed)
    ↓
ADR DRAFT
    ↓
PHASED IMPLEMENTATION
    ↓
REALITY VERIFICATION
    ↓
COMMIT + HANDOVER
    ↓
NEXT PHASE
```

At any point:

```
STOP AND STEER
```

may interrupt implementation and return work to architectural discussion.

This interruption loop is intentional and critical.

---

## 7. Workflow Stages

### 7.1 Survey Phase

**Purpose**

Understand the actual problem space before committing to architecture.

The survey phase is intentionally adversarial.

The objective is to:

- break assumptions,
- expose hidden complexity,
- identify unstable concepts,
- and locate architectural risk.

The survey is not implementation planning.

It is architectural reconnaissance.

**Typical Activities**

- inspect real data,
- analyze current behavior,
- map conceptual boundaries,
- identify hidden coupling,
- test edge cases,
- compare competing approaches,
- challenge terminology,
- identify irreversible decisions,
- identify architectural debt,
- and identify uncertainty.

**Deliverables**

Typical outputs:

- risks,
- observations,
- constraints,
- open questions,
- architectural pressure points,
- and possible directions.

Not finalized solutions.

### 7.2 Steering / Architectural Discussion

**Purpose**

Convert survey findings into architectural direction.

This stage exists because architecture should remain exploratory until:

- concepts stabilize,
- terminology stabilizes,
- and major unknowns become visible.

Premature commitment produces fragile architecture.

**Important Principle**

Architecture discussion should optimize for:

- understanding,
- tradeoff visibility,
- and conceptual clarity

before optimizing for implementation speed.

### 7.3 Pre-Cleanup Phase

**Status:** Established practice (introduced during ADR 0004 workflow evolution)

**Purpose**

Stabilize foundational truths before drafting the ADR.

This phase emerged after implementation repeatedly exposed hidden instability in assumptions that should have been resolved earlier.

Examples:

- unstable identifiers,
- weak validation,
- naming inconsistency,
- missing loud-fail behavior,
- hidden assumptions,
- and ambiguous ownership.

**Principle**

The ADR should lean on stable reality, not unstable assumptions.

### 7.4 ADR (Architecture Decision Record)

**Purpose**

Capture durable architectural decisions and reasoning.

The ADR documents:

- context,
- problem framing,
- constraints,
- decision rationale,
- tradeoffs,
- consequences,
- and deferred concerns.

**Important Distinction**

The ADR is not:

- a full implementation specification,
- a task tracker,
- or exhaustive technical documentation.

It is:

- architectural memory,
- decision rationale,
- and design intent.

**Recommended ADR Sections**

- Status
- Context
- Problem
- Constraints
- Decision
- Tradeoffs
- Consequences
- Open Questions
- Known Unknowns
- Deferred Work
- Validation Strategy

### 7.5 Phased Implementation

**Purpose**

Implement architecture incrementally while preserving learning opportunities.

Implementation is intentionally phased because:

- architecture evolves during contact with reality,
- assumptions fail during implementation,
- and AI-generated code can drift from architectural intent.

**Important Principle**

Do not optimize for implementation velocity at the expense of architectural visibility.

Fast incorrect architecture is expensive.

**Typical Phase Structure**

Each phase should ideally:

- have narrow scope,
- remain independently verifiable,
- preserve rollback capability,
- and produce clear operational feedback.

### 7.6 Reality Verification

**Purpose**

Validate the actual system behavior.

This is one of the most important stages in the workflow.

**Reality Anchors**

Validation should involve one or more of:

- real datasets,
- real rendering,
- real workflows,
- real operational behavior,
- browser inspection,
- or user-facing output verification.

**Why This Exists**

AI-assisted workflows frequently produce situations where:

- tests pass,
- implementation appears structurally correct,
- but actual system behavior is wrong.

Reality verification exists to prevent:

- plausible failure,
- silent regression,
- and architecture drift.

---

## 8. STOP AND STEER

**Purpose**

Interrupt implementation momentum when assumptions fail.

This is one of the most important control mechanisms in the workflow.

**Common STOP Triggers**

Examples:

- unexpected abstraction growth,
- data model mismatch,
- terminology instability,
- excessive mapping logic,
- repeated exceptions,
- architecture drift,
- surprising implementation complexity,
- rendered behavior diverging from expectations,
- "temporary" workarounds accumulating,
- uncertainty becoming difficult to explain clearly.

**Principle**

Surprise is architectural signal. Do not power through surprise.

---

## 9. Design Truth vs System Truth

The workflow distinguishes between three validation layers.

### 9.1 Design Truth

Question:

- Does the implementation align with the intended architecture?

Validated through:

- ADR consistency,
- structural review,
- conceptual consistency.

### 9.2 Implementation Truth

Question:

- Does the implementation technically function?

Validated through:

- builds,
- tests,
- static checks,
- and implementation verification.

### 9.3 System Truth

Question:

- Does the actual system behave correctly under reality?

Validated through:

- real rendering,
- real datasets,
- operational workflows,
- and real-world usage.

---

## 10. Established vs Emerging Practices

Not all parts of this workflow are equally mature.

Some practices are repeatedly validated through real usage.

Others are emerging ideas still under evaluation.

### 10.1 Established Practices

Practices repeatedly used successfully:

- survey before architecture,
- steering discussions,
- phased implementation,
- STOP-and-steer escalation,
- reality verification,
- browser validation,
- real-data validation,
- commit + HANDOVER discipline,
- push-and-confirm at every phase close,
- methodology marker capture,
- and multi-chat workflow separation.

**Push and confirm at every phase close.**

A phase is not "closed" until it is pushed to origin *and the push is confirmed*.

The closing sequence is fixed:

per-deliverable commits → CHANGELOG/HANDOVER commit → pointer commit → push to origin → confirm the push landed.

Confirmation means verifying the local branch HEAD matches `origin/<branch>` — `git status` clean and ahead-by-0, or `git rev-parse HEAD` equal to `git rev-parse origin/<branch>` — not merely that the push command returned without error.

"Pushed" is verified, not asserted. This is the same reality-over-report discipline as browser verification: don't trust that it rendered, look; don't trust that it pushed, confirm the remote moved.

The remote is the durable record of verified work. It must never sit behind the verified local state at a phase boundary.

### 10.2 Emerging Practices

Practices partially adopted but not yet stabilized:

- formal retrospectives,
- explicit reversibility classification,
- architecture debt tracking as separate category,
- formalized change classes,
- and structured known-unknown categorization.

These should be treated as experimental workflow evolution rather than mandatory process.

---

## 11. Continuous Methodology Marker Capture

The workflow includes continuous capture of:

- surprises,
- workflow lessons,
- AI failure patterns,
- architectural pressure points,
- and operational observations.

This differs from retrospectives.

The capture happens continuously during implementation and review.

Typical locations:

- HANDOVER files,
- implementation summaries,
- architecture notes,
- and steering discussions.

---

## 12. Multi-Context AI Workflow

The workflow intentionally separates AI interaction modes.

Different conversation contexts are used for different purposes.

Examples:

- steering chats,
- architecture drafting chats,
- implementation prompts,
- review sessions,
- and retrospective discussions.

This separation exists because different forms of reasoning benefit from different conversational contexts.

---

## 13. Process Cost

This workflow has real overhead.

That overhead is intentional.

The process cost is justified when:

- architecture longevity matters,
- regressions are difficult to detect,
- reversibility is low,
- and hidden complexity is high.

The workflow should remain adaptable.

If process overhead exceeds architectural benefit, the workflow should be simplified.

---

## 14. Concrete Lessons Learned

Examples from actual workflow evolution:

### 14.1 Chart Regression Incident

ADR 0003 modernized data collection but accidentally downgraded data presentation, because rendering intent lived in hand-written legacy builders rather than in catalog metadata. Tests passed throughout. Code review passed. Several subjects silently lost their charts and summary metrics for weeks, until a screenshot surfaced the gap.

**Lesson**

If no human looks at the rendered output, no amount of code-level discipline catches the regression. Programmatic verification (tests, builds, type checks) cannot substitute for human inspection of the actual rendered surface that users see.

**Result**

- browser validation against the workspace became mandatory for any change touching rendering or data flow into rendering,
- the "reality anchors" stage of the workflow was strengthened to explicitly require user-visible output verification, not just code-level verification.

### 14.2 LS Structural Surprise During ADR 0003 Phase 5

ADR 0003's original survey covered License Summary at a high level but did not probe its full structural depth. Phase 5 of implementation began as a routine migration, then surfaced that LS required page-aware GUID resolution, cross-dataset parameter substitution, and per-row value formulas — none of which fit the catalog model the ADR had committed to.

Implementation did not power through. Phase 5 stopped, the discovery was investigated, and the ADR was amended honestly: LS was deferred as a bespoke path rather than retrofitted into a model it did not fit.

**Lesson**

Late-phase rigor can rescue an ADR. Even when a survey misses structural complexity, STOP-and-steer discipline at the moment of discovery prevents architectural damage. Powering through the surprise would have produced either a broken LS migration or a contorted catalog model warped to accommodate one outlier.

**Result**

- the STOP-and-steer principle was reinforced as an architectural control, not merely an implementation pause,
- subsequent ADRs (notably ADR 0004) invested more heavily in adversarial surveying to reduce reliance on late-phase rescue.

### 14.3 Inline Prompt Truncation / Tooling Constraints

Large inline implementation prompts containing full document content (an ADR draft, in this case) became operationally fragile: the prompt was silently truncated at the implementation tool's boundary, and the receiving session only saw a partial document.

**Lesson**

Workflow tooling constraints can become architectural constraints. The mechanism by which content is delivered between sessions matters as much as the content itself.

**Result**

- preference shifted toward file-based context delivery for any substantial document,
- structured handovers via files on disk replaced large inline prompts for ADRs, surveys, and other multi-page artifacts.

---

## 15. Retrospectives

**Status:** Emerging practice (planned, not yet fully operationalized)

Retrospectives exist outside the implementation loop.

They focus on:

- methodology quality,
- recurring failure patterns,
- workflow refinement,
- and operational lessons.

The goal is to improve:

- how the work is performed,
- not merely what was built.

The first retrospective is currently queued in HANDOVER and will be the first real test of this section. The accuracy of this section's description should be revisited after that retrospective happens.

---

## 16. Important Warning

The workflow itself is not the objective.

The workflow exists to:

- improve reasoning,
- reduce hidden failure,
- expose uncertainty,
- preserve architectural visibility,
- and safely collaborate with probabilistic AI systems.

The process must remain:

- adaptable,
- empirical,
- and subordinate to reality.

If the workflow becomes:

- ritualized,
- bureaucratic,
- or disconnected from actual engineering value,

then it has failed.

Reality always outranks process.

---

## 17. Summary

This workflow is best described as:

Disciplined AI-assisted architecture practice for long-lived, low-reversibility systems.

It combines:

- architectural reasoning,
- phased implementation,
- operational verification,
- explicit uncertainty management,
- and AI-specific compensating controls.

The workflow assumes:

- architecture emerges through contact with reality,
- AI systems are powerful but non-authoritative,
- and disciplined interruption is necessary to prevent plausible failure.

The objective is not perfection.

The objective is:

- durable systems,
- controlled learning,
- and safe iteration under uncertainty.
