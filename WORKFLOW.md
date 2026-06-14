# WORKFLOW.md

## Disciplined AI-Assisted Architecture Workflow

**Status:** Living document
**Calibration:** Prototype-stage workflow. Failure is acceptable when it is detectable and recoverable.
**Review trigger:** Re-evaluate this workflow when real customer data, revenue dependency, production use, or irreversible operational impact enters scope.
**Review owner:** Project owner.

---

### 1. Core Principle

The workflow exists to support good engineering judgment, not replace it.

It should expose uncertainty, reduce avoidable mistakes, and preserve architectural intent.

It must not become default ceremony for every change.

---

### 2. Process Is Proportional To Cost-Of-Being-Wrong And Detection Lag

Before choosing a workflow path, ask:

> If this is wrong, how would we find out, how long would it take to notice, and can we recover?

The amount of process depends on:

```
cost of being wrong
×
delay before detection
×
recoverability
```

A small change with late detection can be high-risk.

A larger change with immediate detection and easy rollback can be low-risk.

---

### 3. Lightweight Path Is The Default

For prototype work, the default path is:

```
Build
→ Observe
→ Keep / Change / Remove
```

Use this path unless the work touches something hard to detect, hard to undo, destructive, security-sensitive, persistent, or customer/context-sensitive.

The heavyweight path must justify itself in one line:

> The hard-to-undo or late-detected risk is: ______

This line is the main challenge point: it should be questioned, not trusted by default.

If that line cannot be filled honestly, use the lightweight path.

---

### 4. Three Starting Questions

For every meaningful change, ask:

1. What do we think is true?
2. What is the cheapest way to find out if we are wrong?
3. If we are wrong, how soon would we know, and can we recover?

If detection is fast and recovery is cheap, prefer doing over discussing.

If detection is slow or recovery is expensive, slow down.

---

### 5. STOP Outcomes

STOP can lead to three valid outcomes:

```
STOP AND STEER
STOP AND SIMPLIFY
STOP AND ABANDON
```

Learning that something should not be built, migrated, generalized, preserved, or automated is a successful result.

---

### 6. Reality Over Plausibility

Tests, code review, and AI reasoning are not enough.

For meaningful changes, verify against reality:

- real data,
- real rendering,
- real browser behavior,
- real workflows,
- real operational output.

For lightweight prototype work, reality verification may simply be: look at the result and decide whether to keep it.

For late-detected risks, reality verification is mandatory.

---

### 7. Documentation Has A Lifecycle

Documentation can become stale authority.

Durable architectural decisions may be captured in ADRs.

Transitional decisions must include one of:

- expiry date,
- review condition,
- removal condition,
- owner.

Temporary compatibility, migration scaffolding, unused parameters, deprecated behavior, and "later cleanup" notes must not become permanent architecture by accident.

---

### 8. Human / AI Division Of Labor

The human owns:

- value,
- priority,
- risk tolerance,
- acceptance,
- and whether failure is acceptable.

AI may assist with:

- investigation,
- implementation,
- comparison,
- review,
- summarization,
- drafting.

AI is useful but non-authoritative.

This workflow assumes human judgment. It can amplify good judgment, but it cannot manufacture it.

---

### 9. Heavyweight Workflow

Use this only when justified by hard-to-undo or late-detected risk.

```
SURVEY
    ↓
STEERING / ARCHITECTURAL DISCUSSION
    ↓
PRE-CLEANUP, IF NEEDED
    ↓
ADR, IF NEEDED
    ↓
PHASED IMPLEMENTATION
    ↓
REALITY VERIFICATION
    ↓
COMMIT + HANDOVER
```

At any point:

```
STOP AND STEER
STOP AND SIMPLIFY
STOP AND ABANDON
```

may interrupt the work.

---

### 10. Push And Confirm

At phase boundaries for meaningful committed work:

```
commit
→ push
→ confirm local HEAD equals origin HEAD
```

For throwaway local experiments, this requirement applies only after the work is kept.

---

### 11. Summary

Cheap, detectable, recoverable failure should move fast.

Expensive, silent, or hard-to-recover failure should move carefully.

The goal is not maximum process.

The goal is safe learning at the right speed.
