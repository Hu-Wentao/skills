# Wording and naming

Use this reference for capitalization, abbreviations, dates, numbers, filenames, example data, and names. For exact word usage or a current product spelling, follow the live-lookup policy in `source-index.md`.

## Capitalization and punctuation

- Use sentence case for titles and headings unless project style specifies otherwise.
- Preserve the official capitalization of products, companies, APIs, protocols, code identifiers, and UI labels.
- Use US English spelling and punctuation in English documentation unless the project requires another dialect.
- Use the serial comma in a list of three or more items.
- Use punctuation to clarify syntax, not to carry meaning that disappears for a screen-reader user.
- Avoid ampersands as a replacement for *and* except in exact UI labels, company names, space-constrained labels, or code.
- Avoid semicolons when two shorter sentences are clearer.
- Do not use all caps for emphasis. Use the target format's semantic emphasis sparingly.

## Abbreviations and terms

- Spell out an unfamiliar abbreviation on first use, followed by the abbreviation in parentheses when it recurs.
- Do not define an abbreviation that appears only once.
- Preserve an abbreviation that is more familiar than its expansion or is the official product name.
- Use one term consistently for each concept, including the same capitalization and singular or plural form.
- Check the project's glossary before selecting a synonym.
- Do not turn a trademark or product name into a possessive, plural, or verb when a neutral rewrite is available.

## Numbers and units

- Follow project conventions first. Otherwise, use numerals for measurements, versions, percentages, times, and numbers 10 or greater; spell out zero through nine in ordinary prose.
- Use a numeral when a mixed set contains values both below and above 10 and readers need to compare them.
- Do not begin a sentence with a numeral; rewrite it or spell it out.
- Put a space between a number and most unit symbols. Preserve established exceptions and syntax.
- Use a consistent unit and precision within a comparison. Convert units when the audience needs a common basis.
- State ranges unambiguously and distinguish inclusive ranges from endpoints or alternatives.
- Avoid vague quantities such as *several* when an exact threshold matters.

## Dates and times

- Use an unambiguous month-name format in prose, such as “January 15, 2026,” when writing US English.
- Use ISO 8601 forms where machine readability, sorting, logs, APIs, or cross-locale interchange is the goal.
- Include the year when omission could create ambiguity.
- State the time zone for scheduled events, deadlines, and timestamps that cross regions.
- Use a 12-hour or 24-hour clock consistently. Include `a.m.` or `p.m.` with a 12-hour time.
- Use explicit dates instead of relative terms such as *today*, *tomorrow*, or *next Friday* in durable documentation.
- Do not use seasons to identify a release period for a global audience.

## Filenames, paths, and extensions

- Format filenames, directory names, paths, and extensions as code.
- Preserve exact case. Do not capitalize a filename merely because it begins a sentence; rewrite the sentence.
- Include the extension when readers need it to identify, create, or distinguish the file.
- Use forward slashes or backslashes according to the documented platform and do not silently mix platform conventions.
- Distinguish a file type from a filename: write “a PNG file” but “the `diagram.png` file.”
- Use safe, descriptive example paths that do not expose a real username or local secret.

## Example names and data

- Use reserved example domains such as `example.com`, `example.org`, and `example.net` instead of real third-party domains.
- Use documentation-reserved IP addresses and identifiers when the exact value does not matter.
- Use diverse personal names only when a person is necessary to the scenario. Avoid stereotypes and culturally loaded roles.
- Label fake credentials and tokens clearly, and use visibly nonfunctional values.
- Keep example names consistent across prose, code, output, and diagrams.
- Avoid `foo`, `bar`, and other opaque metasyntactic names when a descriptive name teaches more.

## Product names and trademarks

- Verify the current official spelling and capitalization from the product owner or official product-name list.
- Use a generic noun after a trademark when it improves grammar or clarity.
- Do not alter a product name to match a heading's sentence case.
- Do not add trademark symbols unless the project or legal guidance requires them.
- Do not imply endorsement, ownership, or compatibility that the evidence does not establish.

## Sources

- [Capitalization](https://developers.google.com/style/capitalization)
- [Abbreviations](https://developers.google.com/style/abbreviations)
- [Numbers](https://developers.google.com/style/numbers)
- [Dates and times](https://developers.google.com/style/dates-times)
- [Filenames and file types](https://developers.google.com/style/filenames)
- [Example domains and names](https://developers.google.com/style/examples)
- [Trademarks](https://developers.google.com/style/trademarks)
