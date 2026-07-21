# Code, UI, and links

Use this reference when documentation contains technical tokens, code samples, command lines, placeholders, interface actions, or links.

## Code in prose

- Use code formatting for identifiers and literal text that readers enter or that a system returns: filenames, paths, commands, flags, method names, classes, keys, values, status codes, and short code fragments.
- Do not use code formatting for product names, conceptual terms, URLs used as links, or ordinary abbreviations.
- Preserve the exact capitalization and spelling of code elements.
- Use a grammatical noun around an identifier when needed, such as “the `open()` function” or “the `--force` flag.”
- Do not pluralize a code token by adding punctuation inside code formatting. Rewrite the sentence or add the plural ending outside the token only when the target style supports it.
- Avoid putting long or multiline code in a sentence. Use a fenced block with the correct language identifier.

## Code samples

- Include only code that advances the documented task. Keep setup and unrelated production scaffolding out of focused examples.
- Make samples correct, runnable when promised, secure for the stated context, and consistent with the surrounding explanation.
- State prerequisites before the sample and explain the result afterward when it is not obvious.
- Use realistic but safe sample data. Never place secrets, live credentials, real personal data, or production endpoints in examples.
- Identify omitted code explicitly. Do not use unexplained ellipses that readers might copy as syntax.
- Explain non-obvious lines, but do not narrate syntax that the intended audience already understands.
- Keep comments concise and use them for information that belongs inside the sample. Put broader teaching material in prose.
- Validate samples with the documented toolchain when possible. Never claim that an untested sample was tested.

## Commands and output

- Put commands in fenced blocks. Keep prompts such as `$` out of copyable command text unless the prompt itself is being explained.
- Show one logical command per example unless a sequence must be copied or understood together.
- Distinguish commands from output with separate blocks and introductory text.
- Introduce non-exact output as sample output rather than a guaranteed byte-for-byte result.
- Explain whether a command is destructive, requires elevated permission, changes external state, or depends on a working directory.
- Use line continuations according to the documented shell and make every continuation copyable.
- Document mutually exclusive, optional, and repeatable arguments explicitly; do not rely on typography alone to express command grammar.

## Placeholders

- Use descriptive uppercase placeholder names separated by underscores, such as `PROJECT_ID`, unless the target syntax or project convention requires another form.
- Put placeholders in code formatting in prose and in their natural position inside code blocks.
- Explain every placeholder immediately after the sample or before the reader must replace it.
- Use one placeholder name for one concept throughout the page.
- Do not combine placeholder brackets with syntax brackets unless the command convention explicitly defines both.
- Distinguish a placeholder from a literal environment variable, shell expansion, or metavariable used by the tool.

## UI elements and interaction

- Match the visible UI label exactly, including capitalization. Format named interactive elements in bold.
- Use the action verb that fits the control: *click* for buttons and links, *select* for options and checkboxes, *enter* for text fields, and *press* for keyboard keys.
- Refer to an element by its accessible label, not by color, shape, icon appearance, or screen position.
- Put the navigation path before the action when the reader must reach another page or panel.
- Use `>` between sequential menu items only when the target format handles it accessibly; otherwise write the sequence in words.
- Use **Keyboard shortcut** notation consistent with the target platform and name keys exactly.
- Describe the current UI. If multiple versions exist, label each version and avoid mixing their navigation paths.

## Links and cross-references

- Write descriptive link text that identifies the destination or action when read out of context.
- Do not use generic phrases such as *click here*, *this page*, or *learn more* as the entire link text.
- Use **see** to introduce a cross-reference when an introduction is needed. Do not tell the reader to “refer to” a link.
- Link the shortest phrase that names the destination; do not link an entire sentence.
- Avoid adjacent links and repeated links to the same destination in one short section.
- Explain unexpected behavior such as a download, a new application, or a jump within the page.
- Verify that the destination exists, supports the claim, and points to the most authoritative stable page available.
- Use a relative link for content in the same maintained documentation set when project rules prefer portable links.
- Do not use a bare URL where readable link text is possible.

## Sources

- [Code in text](https://developers.google.com/style/code-in-text)
- [Code samples](https://developers.google.com/style/code-samples)
- [Document command-line syntax](https://developers.google.com/style/code-syntax)
- [Format placeholders](https://developers.google.com/style/placeholders)
- [UI elements and interaction](https://developers.google.com/style/ui-elements)
- [Cross-references and linking](https://developers.google.com/style/cross-references)
- [API reference code comments](https://developers.google.com/style/api-reference-comments)
