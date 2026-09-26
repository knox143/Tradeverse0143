# Andrej Karpathy LLM Coding Principles Rule

This project strictly adheres to the Andrej Karpathy LLM coding guidelines:

1. **Think Before Coding**:
   - Always analyze the complete system context and control flow before proposing or writing code.
   - Pinpoint the root cause; do not apply superficial patches or mask errors.
   - Outline a clear hypothesis and execution plan before modifying any file.

2. **Simplicity First**:
   - Prefer the simplest, most readable, and minimal solution.
   - Avoid unnecessary abstractions, premature optimization, or unneeded third-party packages.
   - Keep code modular, cohesive, and easy to maintain.

3. **Surgical Changes**:
   - Make minimal, targeted modifications. Touch only the lines directly related to the task.
   - Preserve existing coding styles, variable conventions, and comments.
   - Prevent collateral regressions in neighboring modules.

4. **Goal-Driven Execution**:
   - Relentlessly focus on the user's core objective.
   - Always verify changes end-to-end (run test suites, execute scripts, check endpoints, verify database/container state).
   - Never consider a task done without concrete, observable validation.
