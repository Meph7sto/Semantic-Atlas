---
name: writing-proposal
description: Initial proposal document outlining the change.
---

# Writing Proposal Skill

## Overview

Create the proposal document that establishes WHY this change is needed. The proposal captures human intent, scope, and approach at a high level. Use `template` as the structure - fill in its sections.

See template at: writing-proposal/template.md

Save proposal to: superspec/<change-name>/proposal.md

## Proposal Sections:

- **Why**: 1-2 sentences on the problem or opportunity. What problem does this solve? Why now?
- **What Changes**: Bullet list of changes. Be specific about new capabilities, modifications, or removals. Mark breaking changes with **BREAKING**.
- **Capabilities**: Identify which specs will be created or modified:
  - **New Capabilities**: List capabilities being introduced. Each becomes a new `specs/<name>/spec.md`. Use kebab-case names (e.g., `user-auth`, `data-export`).
  - **Modified Capabilities**: List existing capabilities whose REQUIREMENTS are changing. Only include if spec-level behavior changes (not just implementation details). Each needs a delta spec file. Check `superspec/specs/` for existing spec names. Leave empty if no requirement changes.
- **Impact**: Affected code, APIs, dependencies, or systems.

IMPORTANT: The Capabilities section is critical. It creates the contract between proposal and specs phases. Research existing specs before filling this in.

Each capability listed here will need a corresponding spec file.

Keep it concise (1-2 pages). Focus on the "why" not the "how" - implementation details belong in design.md.

## **Remember**

- First, you need to understand the background of the current project
- If context is unclear, ask the user before creating
- Once you understand what you're building, begin writing your proposal
- You must understand the structure and meaning of the proposal and write it according to the template.

