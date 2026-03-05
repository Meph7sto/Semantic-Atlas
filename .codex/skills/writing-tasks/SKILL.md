---
name: writing-tasks
description: Implementation checklist with trackable tasks
---

# Writing Tasks Skill

## Overview

Create the task list that breaks down the implementation work.

**IMPORTANT: Follow the template below exactly.** The implement phase parses checkbox format to track progress. Tasks not using `- [ ]` won't be tracked.

Guidelines:

- Group related tasks under ## numbered headings
- Each task MUST be a checkbox: `- [ ] X.Y Task description`
- Tasks should be small enough to complete in one session
- Order tasks by dependency (what must be done first?)
- Testing is also treated as a task, with an emphasis on unit testing and end-to-end testing.
- Commit the task-group changes as a verifiable small step.(If change is small, you can commit after several related groups of tasks, but don't let it get too big - ideally each commit should be a logical unit that can be verified and understood on its own.)

Example:

```
## 1. Setup
- [ ] 1.1 Create new module structure
- [ ] 1.2 Add dependencies to package.json
- [ ] 1.3 Add unit tests

## 2. Core Implementation
- [ ] 2.1 Implement data export function
- [ ] 2.2 Add CSV formatting utilities
- [ ] 2.3 Make a git commit

```
## Remember
- Reference specs(if present) for what needs to be built, design (if present) for how to build it.
- If neither specs nor design exists, refer to the proposal to determine what to do and how to do it.
- If not spec-driven development, directly based on human needs and goals .
- **Each task should be verifiable - you know when it's done.**