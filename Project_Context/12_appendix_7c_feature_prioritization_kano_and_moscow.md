---
document: "Focus Play: Product Plan (MRD) - Ship Happens! Group 2, 49-751 Product Management, CMU-SV, October 2026"
section_id: "A7C"
section_title: "Appendix 7C: Feature Prioritization (Kano and MoSCoW)"
file_order: 12 of 13
previous_file: "11_appendix_7b_concept_evolution.md"
tables: 1
contains_image: false
subsections: []
cross_references_sections: ["2"]
cross_references_ids: []
source_citation_numbers_used: ["28", "29"]
next_file: "13_sources.md"
---

# Appendix 7C: Feature Prioritization (Kano and MoSCoW)

Kano categories are judged from our 18 interviews, not a Kano survey. MoSCoW rule: Must-haves are the features the MVP's core flow cannot run without, plus anything required by policy or safety or needed to measure the MVP; the MVP is every Must-have and Should-have.

<!-- TABLE 16: 29 data rows x 6 columns; first row is the header row -->
| **Feature** | **Type** | **Evidence** | **Kano** | **MoSCoW** | **Release** |
|---|---|---|---|---|---|
| Type what to learn | Deterministic | Deadline pressure 18/18 | Basic | Must | MVP |
| Set the time available | Deterministic | Deadline pressure 18/18 | Basic | Must | MVP |
| AI finds relevant videos | AI-native | Finding the useful section 13/18 | Basic | Must | MVP |
| AI finds the useful moment in each video | AI-native | Finding the useful section 13/18 | Basic | Must | MVP |
| AI turns those moments into a new lesson, without showing creator footage or repeating content | AI-native | Tools by task 18/18 | Performance | Must | MVP |
| Lesson fits within the time available | AI-native | Deadline pressure 18/18 | Basic | Must | MVP |
| Refuses requests outside study lessons | AI-native | Guards against misuse (prompt injection) [29] | Indifferent | Must (safety) | MVP |
| Still-frame video with an AI voice | AI-native | Students come to YouTube for visual explanation 18/18 | Performance | Must | MVP |
| Vertical feed of short parts | Deterministic | Finding the useful section 13/18 | Performance | Must | MVP |
| Part replays until the student swipes | Deterministic | Expected in a Shorts-style feed | Basic | Must | MVP |
| Source links that open at the exact moment | Deterministic | Trust 14/18; YouTube for demonstrations 18/18 | Performance | Must | MVP |
| AI-generated label | Deterministic | Required by YouTube's AI disclosure policy [28] | Indifferent | Must (policy) | MVP |
| Unhappy path: best creator moments when a lesson fails | Mixed: AI decides a lesson can't be built; the screen is deterministic | Guards against a failed or unreliable lesson | Basic | Must | MVP |
| Like or dislike on each part | Deterministic | Measures how students feel while watching | Indifferent | Must (measurement) | MVP |
| End-of-lesson rating: helpfulness (1–5) and time saved | Deterministic | Needed to measure the MVP's gate | Indifferent | Must (measurement) | MVP |
| Fact-check plus expert review | Mixed: AI links claims to sources; a human expert reviews | Trust 14/18; worst-case risk (2.6) | Basic | Could (held back) | Release 2 |
| Upload course notes, kept private | Mixed: upload and storage are deterministic; AI reads the notes | Fit before watching 16/18 | Performance | Could | Later |
| Basic trust information on source cards | Mixed: upload date and ratings are deterministic; judging a video's level is AI | Trust 14/18; fit 16/18 | Performance | Could | Release 2 |
| AI comment summaries | AI-native | Trust 14/18 | Delighter | Could | Release 2 |
| Teaching style | AI-native: choosing a style is a setting, but following it is AI | Style requests in interviews | Delighter | Could | Later |
| Outdated-version warnings | AI-native | Fit before watching 16/18 | Performance | Could | Later |
| Use likes and dislikes to improve future lessons | AI-native | Pays off only with repeated use | Performance | Could | Later |
| Learn from watch history, with permission | AI-native | Pays off only with repeated use; privacy risk | Delighter | Could | Later |
| Language and terminology support | AI-native | Language 6/18 | Performance | Could | Later |
| AI motion video | AI-native | Drives cost (Section 2) | Delighter | Won't for now | Once costs fall |
| Verified-audience badges | Deterministic | Needs many users taking part | Delighter | Won't for now | Later |
| Community notes | Deterministic | Needs many users taking part | Delighter | Won't for now | Later |
| Progress tracking | Deterministic | Progress 5/18 | Indifferent | Won't | Out |
| Quizzes, topic maps, leaderboards, ads | Mixed: quizzes and topic maps are AI; leaderboards and ads are deterministic | Killed (Appendix 7A) | Indifferent | Won't | Out |

**Exception:** fact-checking is a Kano basic feature and a safety measure, which our rule would make a Must-have. We hold it back from the MVP because it is a controlled test with recruited students who know the lessons are AI-made and unchecked, so the risk of a wrong lesson is contained; full fact-checking returns before any wider release.
