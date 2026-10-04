---
document: "Focus Play: Product Plan (MRD) - Ship Happens! Group 2, 49-751 Product Management, CMU-SV, October 2026"
section_id: "6"
section_title: "6. Hypothesis Traceability"
file_order: 6 of 13
previous_file: "05_s05_competitors_and_alternatives.md"
tables: 1
contains_image: false
subsections: []
cross_references_sections: ["7"]
cross_references_ids: ["AC-01", "AC-02", "EV-01", "EV-02", "EV-03", "EV-04", "EV-05", "H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9"]
source_citation_numbers_used: ["1"]
next_file: "07_s07_top_3_concepts_and_how_we_prioritized.md"
---

# 6. Hypothesis Traceability

<!-- TABLE 8: 3 data rows x 6 columns; first row is the header row -->
| **Customer hypothesis** | **Evidence from discovery** | **MVP feature that tests it** | **Type** | **Validation artifact** | **Roadmap gate** |
|---|---|---|---|---|---|
| H5 + H8: Under deadline pressure, finding the useful part of a video eats study time | Deadline pressure 18 of 18; finding the useful section 13 of 18 [1] | AI finds relevant videos and the useful moment in each; the lesson fits the student's time without repeating content, in a vertical feed; students rate whether it saved them time | AI + Det. | EV-01, EV-04, EV-05, AC-01, AC-02 | Release 1 continues only if EV-01, EV-04 and EV-05 pass 4 of 5, AC-01 and AC-02 pass, and at least 70% say the lesson saved them time |
| H2: Students do not fully trust what they find, and check it elsewhere | Trust 14 of 18 [1] | The lesson is built only from its source moments, with links to the exact moment and an AI-generated label | AI + Det. | EV-02 | Release 1: EV-02 must pass 5 of 5 (guardrail) |
| H9: Students use AI tools for quick answers and YouTube for demonstrations | 18 of 18 [1] | Focus Play stays a video study tool: it refuses requests outside study lessons and keeps students tied to creators' demonstrations | AI | EV-03 | Release 1: EV-03 must pass 5 of 5 (guardrail) |

**Hypotheses we dropped or test later:** progress tracking (H1, 5 of 18), because students organize themselves; quitting when confused (H3, 2 of 18), because students switch resources and keep going; distraction (H4, 15 of 18), which is real, but the focused workspace that addressed it failed on strategic fit (Section 7); language support (H6, 6 of 18), which matters to a smaller group; and judging fit before watching (H7, 16 of 18), which we test later, when trust information and course notes return after the MVP [1]. Every MVP feature traces to a hypothesis above; the like, dislike and end-of-lesson rating (AC-02) measure H5 directly by asking whether the lesson saved time.
