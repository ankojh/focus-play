---
document: "Focus Play: Product Plan (MRD) - Ship Happens! Group 2, 49-751 Product Management, CMU-SV, October 2026"
section_id: "2"
section_title: "2. Business Case"
file_order: 2 of 13
previous_file: "01_s01_executive_summary.md"
tables: 6
contains_image: false
subsections: ["2.1 Why build it, why now, why YouTube", "2.2 Goals, company fit and market size", "2.3 What it costs, and what students would have to pay", "2.4 Can it make money?", "2.5 How sure we are", "2.6 Cost to serve, and what happens if the AI gets it wrong", "2.7 How the six factors line up", "2.8 What would make us reconsider"]
cross_references_sections: ["7"]
cross_references_ids: []
source_citation_numbers_used: ["1", "10", "11", "12", "13", "14, 3", "15", "16", "17", "18", "19", "2", "20", "21", "22", "23", "24", "3", "3, 8", "4", "5", "6", "7", "8", "9"]
next_file: "03_s03_who_persona_and_use_case.md"
---

# 2. Business Case

## 2.1 Why build it, why now, why YouTube

<!-- TABLE 1: 3 data rows x 3 columns; first row is the header row -->
| **Question** | **Answer** | **Why** |
|---|---|---|
| Why build it? | **Yes** | All 18 students we interviewed named deadline pressure; under pressure they turn to AI tools and summaries instead of searching YouTube harder [1]. One said they want "as much information as I can in as little time as possible" [2]. Our persona, Katy, has one train ride to review before an exam and can't find a good, trustworthy explanation in that time. |
| Why now? | **No** | Making AI videos is too expensive and too slow today. Every session needs a new set of videos, so costs grow with every student. Motion video costs about $6 a minute to make [3], compared with about $0.30 for slides with a voiceover. A 20-minute Medium lesson needs about 30 eight-second clips, each taking 11 seconds to 6 minutes to make [12], so students would wait minutes, or hours if clips are made one at a time, when they came to save time. |
| Why YouTube? | **Yes, with one risk** | YouTube has the biggest library of teaching videos, the students and the creators. Focus Play would also be different: it builds a series of short videos from creators' teaching, while NotebookLM makes one summary of documents you upload [2]. The risk: lessons built from creators' ideas could take views away from them, so creators must be paid fairly [4]. |

**The Trust Layer only works alongside the AI video feature.** Trust matters too: 14 of 18 students judge videos by views, comments and reputation, then double-check elsewhere [1]. But deadline pressure affected all 18, and trust ratings alone do not save time. On its own, the Trust Layer gives students no new reason to come back, so it is paused too.

## 2.2 Goals, company fit and market size

**Goals any future test must hit:** at least 70% of students rate the lesson 4 or 5 out of 5 for helpfulness; at least 70% say it saved them time compared with searching YouTube themselves; and students come back to study a week later 10% more often than with regular YouTube. Once trust information returns after the MVP, at least 70% should also rate it 4 or 5 out of 5.

**Fit with YouTube's main goal.** YouTube's main measure of success is how much time each person spends watching. Even if Focus Play reached every student we could serve, it would add less than 0.06% to YouTube's daily viewing [2]. So its value would be building a study habit, not adding watch time. The need also outlasts college: graduates still need quick explanations for workplace software and certifications [2], but even a graduate paying for full YouTube Premium would not cover Focus Play's cost. YouTube earns money from ads, Premium subscriptions and licensing [1]. Its parent company, Alphabet, keeps about 60 cents of every dollar of revenue as gross profit [5]; a new product should aim for the same.

**The market is large; size is not the problem.**

<!-- TABLE 2: 4 data rows x 3 columns; first row is the header row -->
| **Market** | **Who** | **Students** |
|---|---|---|
| Total (TAM) | US college students [2] | 18.6 million |
| Reachable (SAM) | Those who prefer learning from videos [2] | 12.1 million |
| First campus (SOM) | Expected users at San José State [2] | 5,330 |
| Year-one target | Students across the US who try Focus Play | 2.4 million |

## 2.3 What it costs, and what students would have to pay

We priced three versions using Google's published AI prices [3, 8], assuming Google pays half of those prices internally. Following the course's definition of cost to serve, we include AI spend, redoing failed attempts, fact-checks and human help such as expert reviewers and customer support [19].

<!-- TABLE 3: 10 data rows x 4 columns; first row is the header row -->
<!-- Visually highlighted (shaded) cells in the original, marking key/emphasis rows or cells: data row 1 (all cells); data row 5 (all cells); data row 6 (all cells); data row 9 (all cells) -->
| **Per paying student, per month** | **Cheapest: slides with an AI voice** | **Medium: slides + 20% AI motion video** | **High: slides + 50% AI motion video** |
|---|---|---|---|
| **AI: making the videos and checking sources** | **$14.52** | **$257.93** | **$650.43** |
| People and running costs: expert checks, support, delivery | $7.99 | $12.02 | $30.72 |
| Free trials for students who never pay | $21.66 | $259.77 | $655.46 |
| Team that builds and runs it | $3.85 | $5.13 | $6.41 |
| **Total cost** | **$48.02** | **$534.85** | **$1,343.02** |
| **Of which AI, including free trials** | **$28.49 (59%)** | **$506.13 (95%)** | **$1,276.32 (95%)** |
| Paid to creators (16.5% of the price) [7] | $9.83 | $109.49 | $274.94 |
| Card payment fees (2.9% of the price) [18] | $1.73 | $19.24 | $48.32 |
| **Price needed just to break even** | **$59.58** | **$663.58** | **$1,666.28** |
| Compared with the $7.99 student plan | 7.5 times | 83 times | 209 times |

**Why it costs so much:**

- **New videos every session.** A student watches about 260 minutes a month, but about 300 minutes must be made, because some is never watched or has to be redone.
- **Motion video is expensive.** It costs about $6 a minute to make, against about $0.09 to $0.30 for slides with a voice.
- **Free trials add up.** The first 5 sessions are free, but only about 1 in 20 students who try a product like this go on to pay [9]. Each paying student covers the free sessions of about 19 others.

Creators are paid fairly: watching the same lessons as normal videos would earn them only about $0.27 a month from ads [13]. To earn Alphabet's usual profit, even the cheapest version would need about **$229 a month**.

*Main assumptions (all adjustable in our cost model): 3 study sessions of 20 minutes a week; experts spot-check 5–10% of lessons [17]; a team of 12 to 20 people at Google's typical engineer pay [16].*

## 2.4 Can it make money?

No option we tested covers the cost:

<!-- TABLE 4: 4 data rows x 2 columns; first row is the header row -->
| **Option** | **What happens** |
|---|---|
| Charge students extra for it | It would need $60 to $1,666 a month. Students pay $7.99 for YouTube Premium [6] and $20 for ChatGPT Plus, US students can get Google AI Pro free [23], and few pay for AI tools at all [10]. |
| Include it in Premium Student ($7.99) | YouTube keeps $6.44 per student after fees and creators, so it loses about $42 per paying student every month: about **$40 million a year** for the cheapest version and **$511 million** for Medium. |
| Have universities pay | Unlikely today. Google already gives universities Gemini and NotebookLM free [20]. Cal State paid $16.9 million for 18 months of ChatGPT [21], and the deal drew pushback even though students already used ChatGPT [22]. Focus Play has no proof it improves grades or retention, which is what universities pay for. Worth testing later, with a pilot that measures results. |
| Pay for it with ads | Ads would bring in about $0.48 per student a month [13], and they would interrupt students who are short on time. |

**Why "price it low now, charge more later" does not work.** That strategy suits ordinary apps, where an extra user costs almost nothing. As our AI Economics lecture puts it, an AI feature that is profitable at 10,000 users can be unprofitable at a million [19]. Here, every session costs real money to make, so more students means bigger losses, not smaller ones. The price would later have to rise about 7.5 times, from $7.99 to about $60, and YouTube kept the Student plan at $7.99 even while raising other Premium prices in 2026 [6]. Even if AI became free, expert checks, free trials and the team would still cost about $19.50 per paying student, more than the $6.44 YouTube keeps. Over a typical 8-month subscription at $7.99, each paying student would lose YouTube about $333.

## 2.5 How sure we are

Our numbers rest on estimates, so we tested what happens if realistic things turn out differently. The cheapest version stays far above $7.99 unless several good things happen at once.

<!-- TABLE 5: 10 data rows x 4 columns; first row is the header row -->
<!-- Visually highlighted (shaded) cells in the original, marking key/emphasis rows or cells: data row 1 (all cells); data row 9 (all cells); data row 10 (all cells) -->
| **What could happen** | **Why it is realistic** | **Cheapest** | **Medium** |
|---|---|---|---|
| **Our base case** | **Google pays half of public AI prices; 1 in 20 pays; 8-month stay** | **$60** | **$664** |
| Google's own AI cost is 20% of public prices | Google runs AI on its own chips, though analysts put AI video computing near public prices [11] | $38 | $287 |
| 1 in 10 trial students pays | Possible if students love it; card-required trials reach 42.5% [9] | $44 | $499 |
| Automated fact-checking cuts expert checks to 1% | Fact-checking AI is improving quickly | $46 | $642 |
| Students pay through the phone app store | Many subscribe in the YouTube app; the store keeps about 15% | $70 | $781 |
| Paying students study 5 times a week, not 3 | Those most willing to pay likely use it most | $77 | $886 |
| Students leave after one semester (4 months) | Study needs peak around exams, then drop | $91 | $992 |
| Only about 1 in 50 trial students pays | Typical for free apps [9] | $103 | $1,117 |
| **Everything goes our way (first three better cases)** |  | **$17** | **$198** |
| **Everything goes against us (last four worse cases)** |  | **$229** | **$2,495** |

Even if everything goes our way, the cheapest version needs about $17 and Medium about $198. If AI prices also keep falling at today's pace for one more year, the cheapest version gets close to $10, but Medium still needs about $66. That is why we recommend pausing, not killing, and rechecking costs every six months (2.8).

## 2.6 Cost to serve, and what happens if the AI gets it wrong

Each study session costs about $0.28 to $0.94 in AI research and fact-checking at public prices [8]. With about 2 million sessions a month at national scale, that is $0.6 to $1.9 million a month before the far larger cost of making the video; customer support adds only about $0.10 per student a month. The worst case is a confident but wrong lesson the night before an exam, watched by a student with no time to double-check it. Students cramming have almost no tolerance for mistakes, so before any wider launch every lesson needs fact-checking and expert spot checks, which make up 29% of the cheapest version's cost. The MVP holds these back because it is a controlled test with recruited students (Section 7). As our AI Economics lecture warns, these costs grow with every session [19], so the more students use Focus Play, the more it loses.

## 2.7 How the six factors line up

We checked Focus Play against the six factors in "Successful PMs Align Multiple Factors" [19]. Students' pain and the size of the market line up. The four factors that decide whether YouTube should spend money now do not, and all four come back to the cost of making AI video.

<!-- TABLE 6: 6 data rows x 4 columns; first row is the header row -->
| **Factor** | **Key question** | **Our answer** | **Lines up?** |
|---|---|---|---|
| Corporate objectives | Will it add revenue? Does it fit the business model? | It loses money at any price students will pay: about $40 million a year for the cheapest version and $511 million for Medium if included in Premium Student. It would also make YouTube a maker of videos that compete with its own creators, while YouTube's model is to host creators and share revenue with them. | **No** |
| Market opportunity and competitive risks | How big is it, and is the window closing? | Big: 18.6 million US college students. AI video prices fell 4 times in 14 months [14, 3], so building now locks in today's high costs. Rivals pay the same prices for AI video, so waiting costs us little. | **Yes, and waiting is safer** |
| Customer pain points | Is the value strong enough to switch from what students do today? | All 18 students named deadline pressure. But today's option, YouTube search plus free AI tools, costs nothing, while Focus Play would need $60 or more a month. We have not shown students would switch at that price. | **Pain yes, switching no** |
| Stakeholder demands | What do executives, engineers and key partners need? | Executives expect about 60% gross profit; Focus Play loses money. Engineers would face slow video generation and fact-checking on every lesson. Creators, YouTube's most important partners, could lose views. Universities, the other possible buyer, are unlikely to pay for an unproven tool. | **No** |
| Technology benefits | Is it feasible at a price customers accept? Build, buy or partner? | Possible today, but too slow and too costly next to the $0 to $20 a month students pay for study and AI tools. Building is right for later, since only YouTube has the creator library. Buying AI from others or running our own changes the price per second of video, not the amount of video to make. | **Possible, not affordable** |
| Resources and budget | How much must we spend to reach the market in time? | Building is cheap: about $0.6 million for a prototype and pilot. Running it is not: unlike normal software, the cost per student does not fall as more students join, so losses grow with success. | **Build yes, run no** |

Product–market fit, at the center of the slide, needs all six to line up. Today the customer need is there but the price is not, so we pause and recheck the cost every six months (2.8).

## 2.8 What would make us reconsider

The main thing that has to change is the cost of making AI video. Without that, nothing else helps. We would look again when all of these are true:

1. **AI video gets much cheaper and faster.** For the cheapest version, which our MVP would test, to work at $19.99 a month, AI costs need to fall about 9 times; for the Medium version with motion video, about 95 times. AI video prices fell 4 times in 14 months, from $0.40 to $0.10 a second [14, 3]; at that pace this takes about 2 years for the cheapest version and 4 for Medium. If they fall 10 times a year, as text AI prices have [15], it takes about 1 and 2 years. A lesson must also be ready within two minutes, our target for how long a student should wait.
2. **At least 1 in 10 trial students pays,** proven by a real price test, or a university pilot shows better grades or retention that a university will pay for.
3. **Fact-checking gets cheaper,** so experts check fewer lessons by hand.
4. **Creators agree a fair payment deal** with YouTube.

We will re-run our cost model every six months, starting in April 2027. In the meantime, a small, cheap price test at San José State (5 free sessions, then a paid option, for 12 weeks, costing about $57,000) would show whether students will pay. A cheaper path also deserves its own evaluation: extending Ask YouTube, which already jumps to the right moment in a creator's video [24], into study sessions sized to a student's time.
