# INDEX: Focus Play Product Plan (MRD), Markdown by section

Source: `MRD_for_PM_Assignment.docx`. Converted losslessly (all text, tables, lists, bold/italic, hyperlinks and the embedded roadmap image) into one Markdown file per top-level section.

## How to use these files with an LLM

- Each file is self-contained and starts with YAML front matter (section id, title, subsections, cross-references to other sections and to test IDs such as EV-01 / AC-01 / H5, and which numbered sources [n] it cites).
- Numbers in square brackets such as [3] refer to the numbered list in `13_sources.md` (the Sources section).
- Tables are GitHub-style pipe tables. A `<br>` inside a cell is a line break between paragraphs or list items in that cell. HTML comments (`<!-- ... -->`) are parser notes, not document content.
- `ZZ_full_document.md` is the whole document in order, for long-context use. Use the per-section files for retrieval/RAG.

## File map

| File | Section | Tables | Size (bytes) |
|---|---|---|---|
| 00_document_header.md | Document header (title, subtitle, team and course) | 0 | 698 |
| 01_s01_executive_summary.md | 1. Executive Summary | 0 | 2931 |
| 02_s02_business_case.md | 2. Business Case | 6 | 15943 |
| 03_s03_who_persona_and_use_case.md | 3. Who: Persona and Use Case | 0 | 3854 |
| 04_s04_customer_problem_statement.md | 4. Customer Problem Statement | 0 | 1712 |
| 05_s05_competitors_and_alternatives.md | 5. Competitors and Alternatives | 1 | 3741 |
| 06_s06_hypothesis_traceability.md | 6. Hypothesis Traceability | 1 | 2582 |
| 07_s07_top_3_concepts_and_how_we_prioritized.md | 7. Top 3 Concepts and How We Prioritized | 1 | 3454 |
| 08_s08_mvp_validation_plan.md | 8. MVP Validation Plan | 3 | 6880 |
| 09_s10_product_roadmap.md | 10. Product Roadmap | 1 | 13596 |
| 10_appendix_7a_full_kill_sheet.md | Appendix 7A: Full Kill Sheet | 1 | 2455 |
| 11_appendix_7b_concept_evolution.md | Appendix 7B: Concept Evolution | 1 | 1549 |
| 12_appendix_7c_feature_prioritization_kano_and_moscow.md | Appendix 7C: Feature Prioritization (Kano and MoSCoW) | 1 | 4979 |
| 13_sources.md | Sources | 0 | 4159 |

## Glossary of IDs used across sections

- **H1-H9**: customer hypotheses from discovery (Assignments 4-5). **EV-01..EV-05**: eval cases for AI-native features (EV-02 and EV-03 are labelled guardrails in Section 8). **AC-01, AC-02**: acceptance criteria for deterministic features. **S-01..S-06**: seam contracts. **R0-R3**: roadmap stages (R0 Park/NOW, R1 Crawl, R2 Walk, R3 Run). **SOM/SAM/TAM**: market size tiers.
- Definitions are in the section files; this glossary only orients the reader.

## Parser notes (for transparency)

- No comments, tracked changes, footnotes, headers or footers exist in this version of the .docx.
- The document numbering jumps from Section 8 to Section 10; there is no Section 9 in this version.
- The only image (roadmap graphic, in Section 10) contains text; it is transcribed in full next to the image reference.
- Shaded table cells in the original (key rows/cells) are flagged in an HTML comment above each affected table.
- The roadmap graphic says "four levers" but lists six items; this is reproduced exactly as in the source.
