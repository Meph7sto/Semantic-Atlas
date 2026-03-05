---
name: superspec-run-change-to-done
description: Entry skill for SuperSpec autonomous delivery. Use when Codex needs to create or select a change, initialize and validate its plan, execute all actions via the protocol loop until terminal done, and return structured success or failure feedback.
---

# SuperSpec Run Change To Done

Drive one change from setup to terminal outcome using the SuperSpec pull protocol.

## Inputs

Resolve these inputs first:
- `change_name` (recommended)
- `owner` for `plan next` (default: `agent`)
- `plan_schema` for `plan init` (default: `SDD`)

If `change_name` is missing, derive a kebab-case name (e.g., "add user authentication" → `add-user-auth`).

## End-to-End Workflow

### Step 1: Resolve the target change.
   - List existing changes first:
     ```bash
     superspec change list
     ```
   - Reuse existing change when the target name already exists in the command output.
   - Create when absent:
     ```bash
     superspec change new "<change_name>"
     ```

### Step 2:  Ensure change-scoped plan exists and is valid.
   - Resolve `plan_schema` from external input; when missing, set `plan_schema=SDD`.
   - Initialize when `superspec/changes/<change_name>/plan.json` is missing:
     ```bash
     superspec plan init "<change_name>" --schema "<plan_schema>"
     ```

### Step 3: Run protocol loop until terminal.
   - Pull next action:
     ```bash
     superspec plan next "<change_name>" --owner "<owner>" --json
     ```
   - Handle response state:
     - `ready`: dispatch executor and report `complete` or `fail`.
     - `blocked`: use fixed-interval polling, then poll again.
     - `done`: stop loop and fetch terminal status.
   - Execution loop contract:
     1. Call `next`.
     2. If `state=ready`, **goto step4**. Execute exactly one action and report `complete` or `fail`.
     3. Immediately call `next` again.
     4. If `state=blocked`, use **blocked polling policy** and call `next` again.
     5. Exit only when `state=done`.

#### Blocked Polling Policy

When `next.state=blocked`:
1. Sleep 2s.
2. Call `next` again.
3. Track consecutive blocked cycles; if blocked exceeds 30 consecutive loops, stop and report `execution_stalled`.

### Step 4: Dispatch `ready` action by executor.
   - `script` executor:
     - Execute `action.script_command`.
     - On success:
       ```bash
       superspec plan complete "<change_name>" "<actionId>" --output-json '{"ok":true,"executor":"script","actionId":"<actionId>","summary":"script completed"}'
       ```
     - On failure:
       ```bash
       superspec plan fail "<change_name>" "<actionId>" --error-json '{"code":"script_failed","message":"script execution failed","executor":"script"}'
       ```
   - `skill` executor:
     - Follow `action.prompt` and invoke `action.skillName`.
     - On success:
       ```bash
       superspec plan complete "<change_name>" "<actionId>" --output-json '{"ok":true,"executor":"skill","actionId":"<actionId>","summary":"skill completed"}'
       ```
     - On failure:
       ```bash
       superspec plan fail "<change_name>" "<actionId>" --error-json '{"code":"skill_failed","message":"skill execution failed","executor":"skill"}'
       ```
   - `human` executor:
     - Present `action.human.instruction` and wait for human decision.
     - Treat reviewer input equal to `action.human.approveLabel` as approval. Run
       ```bash
       superspec plan approve "<change_name>" "<actionId>"  --summary "human review approved"
       ```
     - Treat reviewer input equal to `action.human.rejectLabel` as rejection. Run
       ```bash
       superspec plan reject "<change_name>" "<actionId>" --code "human_rejected" --message "human review rejected"
       ```

### Step 5: Produce terminal result and feedback.
   - Read terminal status:
     ```bash
     superspec plan status "<change_name>" --json
     ```
   - Read status after loop exits on `next.state=done` (terminal confirmation), not after each action.

## Reporting Contract

Use structured payloads.

`complete --output-json` should include:
- `ok` (boolean)
- `executor` (`script` or `skill` or `human`)
- `actionId` (string)
- optional `summary`, `outputs`

`fail --error-json` should include:
- `code` (machine-readable)
- `message` (human-readable)
- `executor` (`script` or `skill` or `human`)
- optional `details`

## Guardrails

- Use the exact `action.id` returned by `next`.
- Do not report `complete` or `fail` before real execution.
- Do not call `status` after every success; use checkpoint/terminal reads.
- Do not call `status --full` after every failure; keep the loop pull-driven by `next`.
- Treat `plan fail` as terminal failure and escalate to a human.
- Do not terminate on first `blocked`; continue polling.
- Stop only when `next` returns `done`.

## Final Feedback Template

On success, report:
- `change_name`
- terminal `status`
- progress (`done/total`, `failed`, `running`)
- key completed actions

On failure, report:
- `change_name`
- terminal `status`
- failed action id(s)
- error code/message and that human intervention is required
