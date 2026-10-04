---
document: "Focus Play: Product Plan (MRD) - Ship Happens! Group 2, 49-751 Product Management, CMU-SV, October 2026"
section_id: "7"
section_title: "7. Top 3 Concepts and How We Prioritized"
file_order: 7 of 13
previous_file: "06_s06_hypothesis_traceability.md"
tables: 1
contains_image: false
subsections: []
cross_references_sections: ["2", "2.3", "2.5", "2.6"]
cross_references_ids: ["EV-02"]
source_citation_numbers_used: ["2"]
next_file: "08_s08_mvp_validation_plan.md"
---

# 7. Top 3 Concepts and How We Prioritized

We scored our three leading concepts against the Week 3 funding filter: user pain, strategic and business-model fit, and feasibility including cost [2]. Our cost model then changed the Stitcher's feasibility (Section 2).

<!-- TABLE 9: 3 data rows x 6 columns; first row is the header row -->
| **Concept** | **User pain** | **Strategic fit** | **Feasibility (Worksheet 2)** | **Feasibility now** | **Decision** |
|---|---|---|---|---|---|
| AI Video Stitcher: find a relevant explanation without searching several videos | Pass | Pass | Pass | **Fail on cost and speed** | Core concept. No-Go for now; recheck every six months |
| Trust Layer: judge whether a source is useful and credible | Pass | Pass | Conditional pass | Conditional pass | Paused and excluded from the MVP |
| Learning Aid: clarify ideas, check understanding, connect topics | Pass | Fail | Pass | Pass | Killed: turns YouTube into a general AI tutor |

**Why the Stitcher won:** it was the only concept aimed at the one pain all 18 students shared, deadline pressure, and it builds on YouTube's creator library. The Trust Layer addresses a real need but is not required to test the core Stitcher experience, while the Learning Aid would have shifted YouTube toward a general AI tutor.

**Feature prioritization.** We used Kano, judged from our 18 interviews rather than a Kano survey, to sort features by how students would react to them, and MoSCoW to draw the MVP line (full table in Appendix 7C). Must-haves are the features the core flow cannot run without, plus anything required by policy or safety or needed to measure the MVP. That gives 15 Must-haves: typing what to learn and the time available; AI finding relevant videos and the useful moment in each; AI turning those moments into a new lesson, without showing creator footage or repeating content, that fits the time available; refusing requests outside study lessons; still-frame video with an AI voice in a vertical feed of short parts that replay until the student swipes; source links to the exact moment; an AI-generated label; the unhappy path; and a like or dislike on each part plus an end-of-lesson rating of helpfulness and time saved. The MVP is the cheapest version in our cost model (Section 2.3), the one closest to affordable (Section 2.5). Course notes, teaching style, the broader Trust Layer, long-term personalization and language support come later; motion video waits because it drives cost.

**One deliberate exception:** fact-checking with expert review is a Kano basic feature and a safety measure, so our rule would make it a Must-have, and Section 2.6 explains why a full launch needs it. We hold it back from the MVP because the MVP is a controlled test with recruited students who know the lessons are AI-made and unchecked, so the risk of a wrong lesson is contained; EV-02 still requires every point to come from its sources, and full fact-checking returns before any wider release.
