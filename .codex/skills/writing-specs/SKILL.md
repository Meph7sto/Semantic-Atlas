---
name: writing-specs
description: Detailed specifications for the change.
---

# Writing Specs Skill

## Overview

Delta specs are the key concept that makes SuperSpec work for brownfield development. They describe what's changing relative to the current specs rather than restating the entire spec.

In this skill, you will create specification files that define WHAT the system should do. Refer to `template` as the structure - fill in its sections.

See template at: writing-specs/template.md

Save every spec to: superspec/<change-name>/specs/<capability>/spec.md

## How to create Delta Specs
Firstly, Read the **proposal.md** for this change carefully.

**Create one spec file per capability listed in the proposal's Capabilities section.**

- New capabilities: use the exact kebab-case name from the proposal (specs/<capability>/spec.md).
- Modified capabilities: use the existing spec folder name from superspec/specs/<capability>/ when creating the delta spec.


**Delta operations (use ## headers):**

- **ADDED Requirements**: New capabilities
- **MODIFIED Requirements**: Changed behavior - MUST include full updated content
- **REMOVED Requirements**: Deprecated features - MUST include **Reason** and **Migration**
- **RENAMED Requirements**: Name changes only - use FROM:/TO: format


**Format requirements:**

- Each requirement: `### Requirement: <name>` followed by description
- Use SHALL/MUST for normative requirements (avoid should/may)
- Each scenario: `#### Scenario: <name>` with WHEN/THEN format
- **CRITICAL**: Scenarios MUST use exactly 4 hashtags (`####`).Using 3
      hashtags or bullets will fail silently.
- Every requirement MUST have at least one scenario.


**MODIFIED requirements workflow:**

1. Locate the existing requirement in superspec/specs/<capability>/spec.md
2. Copy the ENTIRE requirement block (from `### Requirement:` through all scenarios)
3. Paste under `## MODIFIED Requirements` and edit to reflect new behavior
4. Ensure header text matches exactly (whitespace-insensitive) 

Common pitfall: Using MODIFIED with partial content loses detail at archive time.
If adding new concerns without changing existing behavior, use ADDED instead.


Example:

```
## ADDED Requirements


### Requirement: User can export data

The system SHALL allow users to export their data in CSV format.


#### Scenario: Successful export

- **WHEN** user clicks "Export" button

- **THEN** system downloads a CSV file with all user data


## REMOVED Requirements


### Requirement: Legacy export

**Reason**: Replaced by new export system

**Migration**: Use new export endpoint at /api/v2/export

```

## Remember
- Specs should be testable - each scenario is a potential test case.

