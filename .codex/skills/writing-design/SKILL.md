---
name: writing-design
description: Technical design document with implementation details.
---

# Writing Design Skill

## Overview

Create the design document that explains HOW to implement the change. The design captures technical approach and architecture decisions. 

Use `template` as the structure - fill in its sections.

See template at: writing-design/template.md

Save design to: superspec/<change-name>/design.md

## When to create a design.md

Create only if any apply:

- Cross-cutting change (multiple services/modules) or new architectural pattern
- New external dependency or significant data model changes
- Security, performance, or migration complexity
- Ambiguity that benefits from technical decisions before coding

## When to update design.md

- Implementation reveals the approach won't work
- Better solution discovered
- Dependencies or constraints change

## How to create design.md

Firstly, Read the **proposal.md** for this change carefully.

Use template to write designs. Include the following sections: 

### Design Sections:

- **Context**: Background, current state, constraints, stakeholders
- **Goals / Non-Goals**: What this design achieves and explicitly excludes
- **Decisions**: Key technical choices with rationale (why X over Y?). Include alternatives considered for each decision.
- **Risks / Trade-offs**: Known limitations, things that could go wrong. Format: [Risk] → Mitigation
- **Migration Plan**: Steps to deploy, rollback strategy (if applicable)
- **Open Questions**: Outstanding decisions or unknowns to resolve

Focus on architecture and approach, not line-by-line implementation.
Reference the proposal for motivation and specs for requirements.

## Remember
Good design docs explain the "why" behind technical decisions.