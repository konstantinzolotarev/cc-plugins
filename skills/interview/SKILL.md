---
name: interview
description: Interview me about a plan before implementation. Activates on "interview me", "question the plan", "review my plan", "challenge this design", "poke holes", or when user wants thorough questioning of a plan or design document.
argument-hint: "[plan-file]"
---

# Interview

Conduct a thorough interview about a plan or design document before implementation begins.

## Finding the Plan

1. If a plan file path is provided as an argument, read that file
2. Otherwise, look in `docs/plans/` for the most recent plan file
3. If no plan file is found, ask the user which file to review

## Process

1. **Read the plan thoroughly** - understand every section before asking questions
2. **Ask questions one at a time** using the AskUserQuestion tool
3. **Go deep** - ask about technical implementation, edge cases, failure modes, UI/UX decisions, performance implications, and tradeoffs
4. **Don't ask obvious questions** - focus on gaps, assumptions, and risks the plan doesn't address
5. **Challenge decisions** - ask "why this approach over X?" when alternatives exist
6. **Cover all sections** - don't skip parts of the plan, work through it systematically

## Guidelines

- Prefer multiple-choice questions when the answer space is bounded
- Ask follow-up questions when answers reveal new gaps
- Track which sections have been covered
- When the interview is complete, summarize findings and update the plan file with any new decisions, clarifications, or changes agreed upon during the interview
