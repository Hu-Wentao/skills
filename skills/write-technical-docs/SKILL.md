---
name: write-technical-docs
description: Write, rewrite, and review clear developer documentation by applying the Google Developer Documentation Style Guide. Use for English-language tutorials, how-to guides, concepts, API or CLI documentation, READMEs, troubleshooting content, UI instructions, release notes, and technical-documentation style reviews; also use its language-neutral structure and accessibility guidance for documentation in other languages. Follow project-specific terminology and style before this skill.
---

# Write Technical Docs

Produce task-oriented documentation that is accurate, easy to scan, accessible, and usable by a global technical audience. Treat the Google guide as editorial guidance rather than a substitute for product facts, project requirements, or user intent.

## Establish Authority and Scope

Apply guidance in this order:

1. Follow explicit user instructions and the target project's documented style, terminology, templates, and lint rules.
2. Follow this skill and the Google Developer Documentation Style Guide where project guidance is silent.
3. Preserve intentional local consistency when changing it would create a mixed or misleading document.
4. Ask for a decision only when competing interpretations materially change meaning, audience, or required structure.

For non-English content, apply the workflow, information design, accessibility, code, UI, and linking guidance. Do not impose US English grammar, spelling, capitalization, or punctuation on another language.

Never invent commands, flags, API behavior, prerequisites, outputs, product names, links, or compatibility claims. Mark unresolved facts or ask for evidence instead.

## Select References

Load only the references needed for the task:

| Need | Read |
| --- | --- |
| Tone, clarity, grammar, accessibility, inclusion, or localization | [voice-and-language.md](references/voice-and-language.md) |
| Page organization, headings, paragraphs, lists, procedures, tables, notices, or images | [structure-and-formatting.md](references/structure-and-formatting.md) |
| Inline code, code samples, commands, placeholders, UI instructions, or links | [code-ui-and-links.md](references/code-ui-and-links.md) |
| Capitalization, abbreviations, numbers, dates, filenames, examples, or trademarks | [wording-and-naming.md](references/wording-and-naming.md) |
| Exact Google guidance, word-list lookup, product-name lookup, or source verification | [source-index.md](references/source-index.md) |

For a full-document draft or review, read the first four references. Read `source-index.md` only when a question requires exact or current source guidance.

## Write or Rewrite

1. Identify the reader, their goal, the document type, assumed knowledge, prerequisites, and the evidence that supports technical claims.
2. Inspect neighboring documentation and project rules before choosing terminology or formatting.
3. Put the outcome and essential context first. Organize the page around reader tasks and decisions, not the implementation history.
4. Build the smallest structure that makes the content findable. Use descriptive sentence-case headings and reveal details in the order readers need them.
5. Draft in a conversational, respectful, direct voice. Address the reader as **you**, prefer active voice and present tense, and put conditions before instructions.
6. Turn actions into procedures. Keep one primary action per step, place commands and expected results next to the relevant step, and distinguish optional actions explicitly.
7. Format code, placeholders, UI labels, links, images, lists, and tables according to the applicable references.
8. Verify every technical statement against the available source material. Test commands and samples when the task authorizes and permits testing.
9. Remove repetition, filler, unsupported claims, cultural shorthand, and wording that implies a task is easy.
10. Preserve the target format and make the smallest edit that fully satisfies the request.

## Review Existing Documentation

Separate correctness from editorial quality. Do not let a polished sentence conceal an unverified technical claim.

Review in this order:

1. **Technical fidelity:** Check commands, code, links, version claims, prerequisites, results, terminology, and internal consistency.
2. **Task completeness:** Confirm that the reader can identify the goal, prerequisites, actions, expected result, and recovery path when one is required.
3. **Information architecture:** Check title, heading hierarchy, ordering, navigation, and duplication.
4. **Language:** Check voice, tense, sentence structure, terminology, inclusivity, and global readability.
5. **Presentation:** Check lists, tables, code formatting, UI labels, links, images, alt text, and notices.
6. **Accessibility:** Confirm that meaning does not depend only on position, color, punctuation, an image, or mouse interaction.

When asked only for a review, report actionable findings with locations and proposed fixes. Do not edit the document unless the user also requests changes.

## Resolve Tensions

- Prefer accuracy and reader comprehension over mechanical compliance.
- Preserve required product and code identifiers exactly, even when their spelling conflicts with prose style. Format code identifiers as code and write around problematic terms when possible.
- Keep a necessary technical term when an alternative would be less precise; define it on first use.
- Use passive voice when the actor is irrelevant or when the object or result genuinely deserves emphasis.
- Depart from a guideline when the target audience benefits, but apply the chosen exception consistently and report it when it is material.

## Complete the Editorial Pass

Before delivery, verify that:

- the opening states what the reader can accomplish or learn;
- prerequisites appear before the actions that require them;
- headings and link text remain meaningful out of context;
- procedures use imperative steps in a logical order;
- terminology, capitalization, and formatting stay consistent;
- abbreviations are defined when needed and pronoun references are unambiguous;
- code, commands, placeholders, outputs, and UI labels are visually distinct and technically accurate;
- images have useful alt text and do not contain the only copy of essential information;
- dates, times, numbers, and units are unambiguous for the audience;
- no statement promises an unannounced feature or makes an unsupported superlative claim;
- the result follows project-specific rules and preserves intentional exceptions.

For a review handoff, distinguish blocking correctness issues from editorial improvements. For a write or rewrite handoff, summarize the document created or changed, the evidence verified, and any unresolved technical assumptions.

## Resources

- `references/voice-and-language.md`: voice, grammar, accessibility, inclusion, and global-audience guidance.
- `references/structure-and-formatting.md`: page structure and presentation patterns.
- `references/code-ui-and-links.md`: technical tokens, samples, commands, interface instructions, and links.
- `references/wording-and-naming.md`: terminology, capitalization, dates, numbers, filenames, examples, and trademarks.
- `references/source-index.md`: official Google topic map and live-lookup policy.
