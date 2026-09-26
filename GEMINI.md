# Project Guidelines: TradeVerse

This codebase is governed by **Andrej Karpathy's LLM Coding Principles**:

## 1. Think Before Coding
* Read the entire relevant flow and understand system boundaries before touching code.
* Identify the exact root cause of bugs rather than patching superficial symptoms.
* Formulate a clear hypothesis and plan before making any modifications.

## 2. Simplicity First
* Strive for the simplest robust solution with the minimum number of moving parts.
* Avoid premature abstraction, unnecessary layers, and gratuitous dependencies.
* Optimize for clarity, directness, and clean idiomatic code.

## 3. Surgical Changes
* Make minimal, targeted diffs. Never rewrite entire files or touch unrelated logic.
* Respect existing code style, naming patterns, architecture, and comments.
* Check for collateral damage or regressions across related components.

## 4. Goal-Driven Execution
* Focus relentlessly on the user's ultimate goal.
* Validate all changes end-to-end with automated tests and live runtime verification.
* Ensure functionality persists reliably across ephemeral serverless container lifecycles (Vercel).
