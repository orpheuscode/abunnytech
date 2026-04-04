---
name: e2e-implementation
description: "Activate for end-to-end feature implementation that crosses architectural boundaries — tasks touching routes, business logic, persistence, and UI in the same change. Covers requirements capture, full flow tracing, structured planning, implementation with reviewer-agent quality gate, and auditable handoff. Not needed for single-layer bug fixes, config changes, or focused refactors within one module."
---

# End-to-End Implementation Workflow

## When to use this

Activate when the task requires building or modifying a feature across
multiple architectural layers in a single effort. Examples:

- Wiring a new API endpoint through handler → service → database → UI.
- Adding a payment flow, auth system, or data pipeline end-to-end.
- Any feature where a contract mismatch between layers would cause a
  silent failure.

Do NOT activate for: single-file bug fixes, CSS changes, dependency
updates, refactors within one module, config changes, or any task that
stays within a single architectural layer. The CLAUDE.md handles those.

---

## Workflow

Follow these steps in order. Do not skip steps. Each step produces an
artifact that the next step depends on.

### Step 1: Capture Requirements

Before touching code, capture and confirm:

- **Functional requirements.** What does this feature do? What are the
  inputs, outputs, and user-visible behaviors?
- **Non-functional constraints.** Performance targets, security
  requirements, architecture constraints, UX expectations.
- **Completion criteria.** What does "done" look like? Define this
  before implementation, not after. (Supplements §1.3 and §8.1 — the
  CLAUDE.md covers mechanical completion; this covers functional
  completion.)
- **Project guardrails.** Any repo-level instructions, conventions, or
  restrictions from existing documentation.

If requirements are ambiguous, state your assumptions explicitly and get
confirmation before proceeding. Do not infer silently.

### Step 2: Trace the Relevant Flow End-to-End

This is the step most implementations skip, and it is where most
cross-layer bugs originate. Before planning any changes, trace the
actual execution path through the codebase:

- **Entry points** — UI events, route handlers, API endpoints, jobs,
  CLI commands, WebSocket listeners.
- **Contract boundaries** — schemas, DTOs, shared types, API contracts,
  database models. These are where layer mismatches hide.
- **Business logic** — domain rules, validation, transformations,
  orchestration.
- **Persistence** — database queries, cache interactions, file I/O,
  external API calls.
- **Side effects** — state mutations, event emissions, notifications,
  logging, analytics, downstream triggers.

Anchor every conclusion to a specific file and call path. "The user
service probably calls the database" is not tracing — it is guessing.
Open the file and read the function.

Context management note: follow §5.1 (file read budget) and §6.1
(agentic search) during this step. Do not dump entire files into
context. Search for specific entry points, read the relevant functions,
and trace from there.

### Step 3: Plan Implementation

Produce a minimal, ordered plan:

- Which files and modules will change.
- What changes in each, and why.
- The order of changes (contracts and shared types first, then
  implementations, then consumers, then tests).
- Validation scope — which checks apply (per §8.1) and any additional
  targeted tests.
- Risk notes — what could regress, what assumptions you are making.

Structure the plan into phases per §1.4 (max 5 files per phase). Get
approval before starting implementation.

### Step 4: Implement

Apply focused edits only in the files identified in the plan. Follow
all CLAUDE.md directives during implementation:

- Edit safety per §7 (re-read before/after, 3-edit batch limit, grep
  all reference categories on rename).
- Architecture per §4 (single responsibility, interface boundaries,
  dependency direction, one source of truth).
- Code quality per §3 (senior dev standard, consistency, type safety,
  error handling, no forbidden patterns from §14).
- Context management per §5 (re-read files after 10 messages, chunk
  large files, use sub-agents for 5+ file phases).

Preserve existing contracts. If a contract must change, change it first,
then update all consumers before moving on. A half-migrated contract is
worse than the original.

Avoid unrelated refactors unless they are required for correctness. If
you spot a structural problem outside the scope of this task, note it in
the handoff — do not fix it mid-implementation and risk scope creep
(§11.4).

### Step 5: Validate

Run verification per §8.1 (type-checker, linter, tests, logs). Then
run any additional targeted checks specific to this feature:

- If the change involves an API contract, verify request/response
  shapes match between client and server.
- If the change involves a database migration, verify the migration
  runs forward and backward cleanly.
- If the change involves UI state, verify the state flows correctly
  from source to display.

If any required check cannot run, record the exact blocker and surface
it in the handoff.

### Step 6: Reviewer-Agent Loop

After validation passes, run the reviewer-agent loop per §8.3. Spawn a
reviewer sub-agent with this prompt:

```text
Review the recent changes for bugs, regressions, contract mismatches,
and missing edge cases. Prioritize correctness. Return findings ordered
by severity with exact file and line references. If no actionable issues
remain, respond with PASS.
```

Iteration protocol:
1. Run reviewer.
2. Fix actionable findings.
3. Re-run validation (Step 5).
4. Re-run reviewer.
5. Stop only when the reviewer returns PASS or an explicit external
   blocker exists that cannot be resolved in this session.

### Step 7: Handoff

Produce a structured handoff report (supplements §12.3):

- **Requirement summary.** What was requested, including completion
  criteria from Step 1.
- **Flow summary.** The end-to-end execution path traced in Step 2,
  with file references.
- **Plan and changes.** The plan from Step 3, annotated with what was
  actually implemented (and any deviations).
- **Validation results.** The specific commands run and their outcomes.
- **Reviewer status.** PASS, or findings that remain with explanation.
- **Residual risks.** Anything that could not be verified, any
  assumptions that were not confirmed, any deferred items.

Write this to `context-log.md` so the next session can pick up cleanly.

---

## Relationship to CLAUDE.md

This skill does not replace the CLAUDE.md. It layers on top of it. The
CLAUDE.md governs how the agent operates mechanically (context
management, edit safety, verification, communication). This skill
governs the workflow sequence for a specific category of task (end-to-end
cross-layer implementation).

Every step in this workflow references the relevant CLAUDE.md section
rather than restating its rules. If a conflict exists between this skill
and the CLAUDE.md, the CLAUDE.md wins — it is the always-on behavioral
layer.
