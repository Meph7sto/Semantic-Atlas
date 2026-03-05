---
name: excuting-tasks
description: Implement tasks from an SuperSpec change. Use when the user wants to start implementing, continue implementation, or work through tasks.
---

# Executing Tasks

## Overview

Implement tasks from an SuperSpec change. DRY. YAGNI. TDD. Frequent commits.

**Announce at start:** "I'm using the executing-tasks skill to implement tasks."

## **The Process**

### Step 1: Read context files

- Read context document created for developing in this change, especially `tasks.md`. 
- If needed, recall `proposal.md`, `specs`, `design.md`.

### Step 2: Implement tasks(loop until done or blocked)

**You MUST follow **

```
 For each pending task:
   - Show which task is being worked on
   - Make the code changes required or complete the work according to the task requirements.
   - Keep changes minimal and focused
   - Check tasks off as you complete a task
     - Mark task complete in the tasks file: `- [ ]` → `- [x]`
```

**Pause if:**

- Task is unclear → ask for clarification
- Implementation reveals a design issue → suggest updating artifacts
- Error or blocker encountered → report and wait for guidance
- 

### Step 3: **If paused, show status**

   Display:

   - Tasks completed this session
   - Overall progress: "N/M tasks complete"
   - If paused: explain why and wait for guidance

**Output On Pause (Issue Encountered)**

 ```
## Implementation Paused

**Change:** <change-name>
**Schema:** <schema-name>
**Progress:** 4/7 tasks complete

### Issue Encountered
<description of the issue>

**Options:**
1. <option 1>
2. <option 2>
3. Other approach

What would you like to do?
 ```

### Step 4: **Complete Development**

After all tasks complete and verified:
- Report "Output On Completion"

**Output On Completion**

```
## Implementation Complete

**Change:** <change-name>
**Schema:** <schema-name>
**Progress:** 7/7 tasks complete ✓

### Completed This Session
- [x] Task 1
- [x] Task 2
...

All tasks complete! 
```

**Guardrails**

- Keep going through tasks until done or blocked.
- Always read context files before starting .
- If implementation reveals issues, pause and read related context documents. Try updating them.
- Keep code changes minimal and scoped to each task.
- Update task checkbox immediately after completing each task.
- Pause on errors, blockers, or unclear requirements - don't guess.

## **Fluid Workflow Integration**

This skill supports the "actions on a change" model:

- **Can be invoked anytime**: Before all context document are done (if tasks exist), after partial implementation, interleaved with other actions
- **Allows document updates**: If implementation reveals design issues, suggest updating documents - not phase-locked, work fluidly
