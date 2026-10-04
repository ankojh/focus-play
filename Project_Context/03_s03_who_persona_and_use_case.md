---
document: "Focus Play: Product Plan (MRD) - Ship Happens! Group 2, 49-751 Product Management, CMU-SV, October 2026"
section_id: "3"
section_title: "3. Who: Persona and Use Case"
file_order: 3 of 13
previous_file: "02_s02_business_case.md"
tables: 0
contains_image: false
subsections: []
cross_references_sections: ["2"]
cross_references_ids: []
source_citation_numbers_used: ["1", "2", "28"]
next_file: "04_s04_customer_problem_statement.md"
---

# 3. Who: Persona and Use Case

**Primary persona: Katy, a time-crunched graduate student.** Our job sentence: *Katy, a time-crunched graduate student, wants to review topics she struggles with during her Caltrain ride to her final exam, but cannot quickly identify video explanations that are trustworthy or do last-minute revision for specific concepts relevant to her course within her remaining travel time* [2].

**Target audience for the first release:** US college students studying under deadline pressure, starting at San José State University, where we expect about 5,330 users [2].

**MVP use case.** On the train, Katy opens Focus Play inside YouTube and types what she wants to learn and how much time she has. Focus Play finds relevant creator videos and the most useful moment in each, then uses those moments as material for a new lesson with original still-frame visuals and an AI voice, labelled as AI-generated [28]. The lesson plays as a vertical feed of short parts that together fit her time. Each part replays until she swipes to the next, links to the exact moment in the creator video it came from, and can be liked or disliked. After the last part, she rates how helpful the lesson was and whether it saved her time. If Focus Play cannot build a reliable lesson, it says so and shows her the best creator moments instead.

**How the persona evolved.** We started with three Assignment 1 personas: Penny, a low-income undergraduate working 15–20 hours a week; Tariq, an international graduate student studying in his second language; and Eric, a career-changing graduate student in technical courses [1]. Our 18 interviews changed this:

- **Urgency mattered more than who the student was.** All 18 students named deadline pressure [1], so we centered the product on the time-constrained student and sharpened Penny's situation into Katy.
- **Students pick tools by task.** All 18 use AI for speed and YouTube to see a concept explained or demonstrated [1].
- **Budget did not drive behavior, but it is still a money risk.** All three personas stay on YouTube's free plan [1], which feeds directly into Section 2.
- **Tariq's and Eric's traits did not hold broadly.** Language problems affected 6 of 18 and quitting mid-video only 2 of 18 [1], so neither shapes the first release.

**Pivot:** in Assignment 1, our top three needs were progress tracking, trust in content and finishing what students start [1]. Interviews weakened progress tracking (5 of 18), strengthened trust (14 of 18) and showed students switch resources rather than give up (only 2 of 18 quit), while deadline pressure (18 of 18) became the main need [1]. So we moved away from progress tracking and a full study workspace toward getting one good explanation fast. The Stitcher went from shortening long videos, to finding the useful moments across creators (13 of 18 said finding the right section is the real problem [1]), to generating new lessons from those moments in Assignment 5, so YouTube would not reuse creator footage or copy creators' voices [2].

**Evidence twist (Assignment 5).** The new evidence showed us that the time-constrained student was the overarching persona: lack of time sat underneath the other pain points we had found across all three personas, and it was the major one. We rewrote our job sentence around Katy's limited time, and fitting a lesson into the time she has became a must-have feature [2].
