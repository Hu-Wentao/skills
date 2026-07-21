# Structure and formatting

Use this reference for page architecture, headings, paragraphs, lists, procedures, tables, notices, and figures.

## Organize the page

- Start from the reader's goal. State the outcome or purpose before background details.
- Put prerequisites and constraints before the task that depends on them.
- Group information into the smallest coherent sections. Avoid headings for isolated fragments that belong in the surrounding section.
- Use progressive disclosure: present the common path first, then alternatives, explanations, and edge cases.
- Keep related explanation next to the action, code, table, or figure that it supports.
- Link to a maintained explanation instead of copying long material across pages.

## Titles and headings

- Use a unique, descriptive title that identifies the page's subject or task.
- Use sentence case unless the target project's style requires another convention.
- Prefer task headings that begin with an imperative verb and conceptual headings that use a noun phrase.
- Keep headings concise and parallel at the same level.
- Use a logical hierarchy with one page title. Do not skip heading levels or use heading markup only for visual styling.
- Put content under every heading. Ensure headings work as stable, understandable link targets.
- Avoid gerunds when an imperative or noun phrase states the purpose more directly.

## Paragraphs

- Cover one topic per paragraph and lead with its main point.
- Keep paragraphs short enough to scan; split dense blocks by meaning, not by an arbitrary sentence count.
- Use transitions only when they clarify the relationship between ideas.
- Avoid single-sentence paragraphs that merely repeat a heading or announce what comes next.
- Do not force line breaks inside prose to control visual width.

## Lists

- Use numbered lists for sequences and ranked items; use bullets for unordered sets.
- Use a description list or a two-column table for term–description pairs when the output format supports it.
- Introduce a list when its relationship to the surrounding text is not self-evident.
- Keep items grammatically parallel and use consistent capitalization and punctuation.
- Use complete sentences when items contain multiple sentences or complex ideas.
- Avoid embedding headings inside list items unless the target format and hierarchy require it.
- Do not use a one-item list unless the item is a single-step procedure or local style requires list formatting.

## Procedures

- Introduce the goal or context without repeating the heading.
- Use a bullet for a one-step procedure. Use a numbered list for two or more sequential steps.
- Begin each step with an imperative verb and state one primary action.
- Put conditional clauses and purposes before the action.
- Keep steps at the same conceptual level. Use substeps for genuinely subordinate actions, not long explanatory tangents.
- For a complex command step, present the action, command, placeholder definitions, explanation, sample output, and result in that order as applicable.
- Place expected results after the action that produces them. Distinguish sample output from exact expected output.
- Mark optional steps with **Optional:** at the start.
- Prefer the shortest supported method when several methods accomplish the same task. Separate materially different methods into named sections or tabs.
- Do not omit a required prerequisite, permission, navigation point, or verification step.

## Tables

- Use a table only when readers need to compare values across consistent dimensions. Use prose or a list for simple sequences and uneven entries.
- Introduce the table in the preceding text.
- Give every column a concise heading; use row headings when rows identify distinct items.
- Keep cell content brief and parallel. Move multi-paragraph explanations outside the table.
- Do not merge cells or communicate state through symbols or color alone.
- Avoid tables inside numbered procedures when a list or separate section is clearer.
- Make the table understandable when read linearly by assistive technology.

## Notes and warnings

- Use a notice only for information that must stand apart from the main flow.
- Use a note for helpful context, an important notice for information needed to complete the task, a caution for possible data or state loss, and a warning for likely harm or serious consequences.
- State the consequence and the preventive action directly. Do not hide mandatory steps in an optional-looking note.
- Avoid stacking notices or placing routine information in callouts.

## Figures and media

- Use a figure only when it communicates structure, appearance, or a relationship more effectively than text.
- Provide concise alt text that explains the figure's purpose; use empty alt text for a purely decorative image.
- Put essential facts in nearby text, not only in an image, animation, audio track, or video.
- Prefer text over screenshots for code, commands, logs, and error messages.
- Use vector or high-resolution images when practical, and keep screenshots current with the documented UI.
- Add captions, transcripts, or descriptions for audio and video.
- Do not rely on color, direction, or visual position as the only cue.

## Sources

- [Headings and titles](https://developers.google.com/style/headings)
- [Paragraph structure](https://developers.google.com/style/paragraph-structure)
- [Lists](https://developers.google.com/style/lists)
- [Procedures](https://developers.google.com/style/procedures)
- [Tables](https://developers.google.com/style/tables)
- [Notes and other notices](https://developers.google.com/style/notices)
- [Figures and other images](https://developers.google.com/style/images)
- [Write accessible documentation](https://developers.google.com/style/accessibility)
