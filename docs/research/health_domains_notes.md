# Health Domains Discovery Notes

**Status:** Discovery Notes  
**Purpose:** Capture current thinking and findings around Health Domains and future Domain Label consumers.

## Background

Domain Labels v1 has been implemented and merged.

Current label vocabulary:

- governance
- compliance
- backup
- reporting

The first consumer has not yet been designed.

These notes capture observations, findings, and reasoning that should be preserved for future design discussions.

---

# What is a Health Domain?

A Health Domain is not a report section, technical component, or implementation area.

A Health Domain represents a management-level health question.

Examples:

- Can we recover our data?
- Are backups operating correctly?
- Are responsibilities and controls managed?
- Are required controls implemented?
- Do we know when something is wrong?

Domains are intended to group evidence from multiple subjects.

---

# Domain Derivation Principles

A domain earns its place only if:

1. It answers a management-level question.
2. It groups evidence from multiple subjects or checks.
3. It cannot be reproduced by a single category query.
4. It remains meaningful across multiple customers and health checks.

Domains should be derived from management questions, not from report chapter names.

---

# Important Distinctions

## Observability

Answers:

> Do we know when something is wrong?

Examples:

- Monitoring
- Alerting
- Dashboards
- Reporting
- Trend Analysis

Observability provides visibility.

It does not itself prove recoverability.

---

## Backup Operations

Answers:

> Are backups executing correctly?

Examples:

- Job success rates
- Failed jobs
- Schedule compliance
- Copy completion
- Backup workflow execution

Backup Operations measures execution quality.

---

## Recoverability

Answers:

> Can we get the data back?

Examples:

- Restore testing
- Disaster recovery exercises
- Recovery SLA compliance
- Recovery evidence
- Recovery readiness

Recoverability is not the same as reporting.

Observability supports Recoverability.

Backup Operations supports Recoverability.

Neither should be treated as synonymous with Recoverability.

---

# NIS2 Thought Experiment

NIS2 does not appear to be a domain itself.

Instead, NIS2 consumes evidence from multiple domains:

- Governance
- Security
- Compliance
- Infrastructure
- Recoverability

This suggests that future compliance profiles may consume domains rather than replace them.

---

# Findings From Existing Health Check Practice

Current health-check analysis suggests the following candidate domains:

- Governance
- Compliance
- Backup Operations
- Security
- Infrastructure
- Resilience / Availability
- Storage
- Reporting / Observability

Examples:

- Network segmentation → Infrastructure, Security
- Authentication policies → Security, Governance
- Backup workflows → Backup Operations, Governance
- Disaster recovery → Resilience, Backup Operations
- Alerting → Observability, Governance
- Storage protection → Storage, Security

---

# Current Assessment

Strong candidates:

- Governance
- Compliance
- Backup Operations
- Recoverability
- Observability

Likely future candidates:

- Security
- Infrastructure
- Licensing

Require additional evidence:

- Storage
- Capacity

---

# Open Questions

1. What should be the first Domain Label consumer?
2. Are Health Domains computed from labels or stored as first-class catalog objects?
3. Should single-subject domains be allowed?
4. Should unlabeled subjects appear in future domain consumers?

---

# Current Recommendation

Do not implement a Health Domain consumer yet.

Use these notes as input for a future discovery phase focused on:

- Domain consumer design
- Health Profiles
- Compliance Profiles
- Domain-driven reporting

No architecture decision has been made yet.
