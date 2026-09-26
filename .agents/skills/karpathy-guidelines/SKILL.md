---
name: karpathy-guidelines
description: >-
  Enforces Andrej Karpathy's core LLM coding principles: Think Before Coding,
  Simplicity First, Surgical Changes, and Goal-Driven Execution. Use when designing,
  architecting, refactoring, fixing bugs, or implementing features across any language or framework.
---

# Karpathy LLM Coding Guidelines

> "Programming with an LLM is a partnership. The LLM is eager, fast, and capable of generating mountains of plausible-looking code in seconds. Your job is to supply the discipline, taste, rigorous thinking, and verification that prevents high-velocity entropy."
> — *Adapted from Andrej Karpathy's LLM Coding Insights*

These guidelines embody the four core tenets of high-leverage, reliable software engineering with Large Language Models:

1. **Think Before Coding**
2. **Simplicity First**
3. **Surgical Changes**
4. **Goal-Driven Execution**

---

## 1. Think Before Coding (Architecture & Root Cause First)

Never jump straight into writing code or applying blind patches. Eagerness without understanding generates tech debt at lightspeed.

### The Mindset
* **Understand the Whole System First:** Before touching a single line, read the relevant code, understand the data structures, trace the call stack, and comprehend the lifecycle of state.
* **Diagnose the Root Cause, Not Just the Symptom:** If an error occurs, find out *why* it occurred at its source. Do not wrap exceptions in blanket `try-except` blocks or hide errors with superficial `if not x: return None` bandages.
* **Formulate a Clear Hypothesis:** State explicitly:
  1. What is the current behavior and why is it happening?
  2. What is the desired behavior?
  3. What is the minimal logical path from current to desired?
* **Plan Before Modifying:** Outline the concrete steps before executing tool calls or editing files.

### Pre-Flight Questions
* *What happens to state across boundaries (e.g., restarts, network disconnects, serverless cold boots)?*
* *What are the edge conditions (empty lists, null values, concurrent calls, boundary numbers)?*
* *Does this change respect the existing architecture, or am I creating an accidental parallel subsystem?*

---

## 2. Simplicity First (Minimum Complexity, Maximum Clarity)

Complexity is the silent killer of software. The best solution is almost always the simplest solution that completely solves the problem.

### The Mindset
* **Occam's Razor for Code:** If there are multiple ways to solve a problem, choose the one with the fewest moving parts, fewest concepts, and least cognitive overhead.
* **Resist Premature Abstraction:** Do not build frameworks, generic factories, unnecessary class hierarchies, or speculative "future-proofing" layers for code that will only be used once or twice.
* **Write Idiomatic, Readable Code:** Code is read 10x more often than it is written. Optimize for immediate readability by another human engineer.
* **Minimize Dependencies:** Before adding a third-party library or package, ask: *Can standard language primitives or existing project dependencies solve this cleanly in 10 lines?*
* **High Signal-to-Noise Ratio:** Remove dead code, redundant comments, obsolete files, and confusing indirection.

---

## 3. Surgical Changes (Targeted Edits, Zero Collateral Damage)

When editing existing systems, act like a surgeon with a laser scalpel, not a sledgehammer.

### The Mindset
* **Minimal Diff Principle:** Only touch the exact lines, functions, or blocks necessary to achieve the goal.
* **Preserve Established Patterns:** Match the style, formatting, naming conventions, docstrings, and idioms of the existing file. Do not impose unrelated preferences or reformat whole files.
* **Never Rewrite What Works:** Avoid rewriting whole functions or files when fixing a localized bug. Full rewrites wipe out subtle edge-case handling, comments, and battle-tested nuances.
* **Zero Collateral Damage:** Always consider the downstream effects of every edit. Check if callers, imports, templates, APIs, or database queries depend on the code being modified.
* **Diff Self-Review:** Before finishing or committing, review the exact `git diff`. For every single modified line, verify: *Is this edit strictly necessary for the objective?*

---

## 4. Goal-Driven Execution (Relentless Focus & Verification)

Code that has not been executed and verified in the real runtime environment is merely a hypothesis.

### The Mindset
* **Focus on the User's Real Objective:** Never lose sight of what the user is actually trying to accomplish. Do not get distracted by side quests or trivial aesthetic tweaks.
* **End-to-End Verification (Proof Over Promise):** Never say "this should work" or "the code looks right." Run the tests, start the server, call the endpoint, inspect the database, check the logs, and verify actual execution.
* **Test the Failure and Cold-Start Modes:** Test real-world scenarios:
  * What happens after a server restart?
  * What happens if a database is empty or wiped?
  * What happens with invalid user input?
* **Close the Feedback Loop:** If an automated test fails, treat it as a blessing: read the trace, identify the flaw in the hypothesis, fix it surgically, and verify again until green.

---

## The Karpathy Coding Workflow Checklist

Whenever tackling a bug, feature, or refactor, follow this 4-phase sequence:

### Phase 1: Investigation & Diagnosis
- [ ] View and read the relevant source files and documentation.
- [ ] Reproduce or trace the issue to the fundamental root cause.
- [ ] Formulate a written explanation of the problem and the proposed fix.

### Phase 2: Design for Simplicity
- [ ] Find the simplest architectural approach.
- [ ] Eliminate unnecessary layers, flags, or dependencies.
- [ ] Ensure edge cases are handled organically by good design rather than endless ad-hoc patches.

### Phase 3: Surgical Implementation
- [ ] Apply minimal, precise edits using targeted tools (`replace_file_content`).
- [ ] Maintain consistent style, indentation, and docstring integrity.
- [ ] Avoid modifying unrelated code or files.

### Phase 4: Rigorous Verification
- [ ] Run automated test suites (`pytest`, unit tests, integration scripts).
- [ ] Test live or in staging environments where applicable.
- [ ] Inspect `git status` and `git diff` to confirm zero unintended changes.
- [ ] Confirm the user's primary goal is 100% satisfied.

---

## Anti-Patterns to Avoid

| Anti-Pattern | Why It Fails | Karpathy Way |
| :--- | :--- | :--- |
| **Blind Patching** | Patching the error message instead of the root cause creates a game of whack-a-mole. | Trace the flaw to its origin and solve it once and for all. |
| **The Full Rewrite Trap** | Rewriting a 500-line file to fix a 5-line bug destroys existing logic, comments, and edge cases. | Apply a surgical, pinpoint edit to the exact lines responsible. |
| **Over-Engineering** | Building elaborate abstraction layers for simple logic slows down the codebase and team. | Keep it straightforward, concrete, and minimal. |
| **Assumed Success** | Assuming code works without running it leads to embarrassing runtime crashes. | Run the code, check outputs, verify live endpoints, and confirm test passes. |
