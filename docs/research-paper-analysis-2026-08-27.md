# Research Paper Analysis — Improvement Opportunities for vocab_app_v2

Date: 2026-08-27 (revised same day — second pass added the recent high-citation literature)
Scope: analysis only — no code changes were made.

## Evidence base and method

Two rounds of analysis:

1. **Foundational set (full-text)**: 5 user-supplied papers, read in full.
2. **Recent high-citation corpus (2020+, ≥50 citations)**: 35 papers found via OpenAlex
   (39 title/abstract-scoped queries, 303 unique hits screened). Most are paywalled and
   were analyzed at **abstract level**; beyond-abstract detail was obtained for Nakata &
   Elgort 2020, Xiao et al. 2023, Lee et al. 2023, Hao et al. 2021, Furenes et al. 2021,
   Tai & Chen 2024, and Thompson & von Gillern 2020. Where a claim rests on an abstract
   only, it is marked *[abstract]*; papers with no recoverable abstract are marked
   *[title-grounded]*. Claims below cite effect sizes only where the source reports them.

**Population caveat (applies throughout):** the retrieval/AI/app literature is dominated
by adult university EFL learners. The child-evidence base (Furenes, Savva, Jing,
Silverman, Jeon, Fan, Hao) mostly covers ages 0–8 L1 emergent readers or K–5, and our
band is ages 7–14 ESL. Directions generally travel; magnitudes do not. Anything that
changes learning mechanics should be validated with in-app telemetry before being
treated as established.

---

## Part 1 — Foundational papers (full-text)

### Hiebert & Kamil (2005) — Teaching and Learning of Vocabulary: Perspectives and Persistent Issues
Synthesis chapter anchored on the National Reading Panel vocabulary review (50 studies,
73% grades 3–8 — our demographic). NRP conclusions: direct instruction works; repetition
and multiple exposures matter; rich context beats isolation; task restructuring helps
at-risk students most; active engagement is required; computers work; **no single method
is optimal**. Receptive/productive and oral/print vocabulary distinctions; ~88,500 word
families in grades 3–9 texts; word-selection criteria (mid-frequency band, utility,
instructional potential); wide-reading causality unproven. No effect sizes.

### Huang (2024) — Research on the Influence of Retrieval Practice on ESL Vocabulary Memory
*Communications in Humanities Research*. Pilot RCT, N=10 adult Chinese English majors.
Cue-card self-tested recall vs rote re-study: 1-week delayed gains +16.2 vs +2.2 points
(p=.018). Sloppy stats reporting (means swapped in text, wrong df), images confounded
with retrieval — direction matches the larger testing-effect literature; treat as
confirmatory, not load-bearing.

### Susanti et al. (2017) — Evaluation of automatically generated English vocabulary questions
*RPTEL* 12:11. N=79 Japanese undergrads + 8 teacher judges. Machine-generated MC items
correlate with human-made ones (r=0.63–0.71) and with commercial tests comparably, **but
26% of machine items failed the discrimination bar** (≥0.2). Defect taxonomy: Multiple
Correct Answers, Unfamiliar Word Sense, Collocationally Odd Word, More Reasonable Word
(COW+MRW = 38% of defects — students answer "what best substitutes in context" whatever
the stem says). Response-data item analytics agreed with expert judgment → analytics are
a legitimate automated QA proxy. Over-hard wording in the correct answer inverted
discrimination.

### Yu (2026) — Optimizing EFL vocabulary acquisition: AI-driven incidental, contextual, and multimodal strategies
*Education and Information Technologies*. RCT, N=383 adult Chinese EFL learners, 4 arms.
Multimodal ≫ contextual > incidental ≫ control, durable at 6-week delay (robust
d=1.24–1.89; headline η² self-admittedly inflated). Boundary conditions: **sensory
overload** (61% of multimodal users; retention β=−0.53; inverted-U optimum at 3–4
channels); **post-mastery stagnation** (HR=1.8 when content is recycled); **transfer
gap** (52% couldn't use words in unfamiliar contexts); error-specific feedback most
valued but "too brief"; progress visibility ("word bank") drove engagement (β=.59); 68%
flagged Western-centric examples. Internal inconsistencies — treat exact numbers
cautiously.

### Terai, Yamashita & Pasich (2021) — Effects of learning direction in retrieval practice
*Studies in Second Language Acquisition*. N=28 Japanese university EFL learners, GLMM
with effect sizes. No overall direction advantage; meaning recall ≫ form recall
(d=1.20/0.75); **proficiency × direction interaction (p=.009)**: L2→L1 better for
lower-proficiency, L1→2 better for higher-proficiency learners (crossover ≈5,400-word
vocab size). Mechanism: retrieval must be "difficult but successful." For
mixed-proficiency classrooms, recognition direction is the recommended safe default. No
delayed posttest.

---

## Part 2 — Recent high-citation corpus (2020+, ≥50 citations)

Grouped by theme; numbers are the papers' own.

### Retrieval practice, spacing & deliberate study
- **Webb, Yanagisawa & Uchihara (2020, MLJ)** — 122 cites. 22 studies/100 effect sizes:
  deliberate word-focused activities give ~60% immediate gains, collapsing to **39%
  meaning-recall / 25% form-recall delayed**; 4× variability across activity types
  ("learning through word-focused tasks is far from guaranteed"). *[abstract]*
- **Kim & Webb (2022, Language Learning)** — 106 cites. 48 experiments, N=3,411: spacing
  has a medium-to-large effect; **longer intervals beat shorter on delayed tests**;
  **equal ≈ expanding schedules**; number of sessions and feedback timing moderate.
  *[abstract]*
- **Nakata & Elgort (2020, Second Language Research)** — 60 cites. Spaced > massed for
  **explicit** knowledge of contextually-met words, but tacit semantic knowledge
  (priming) developed equally under massing. *[full-text]*
- **Yüksel et al. (2020, CALL)** — 60 cites. N=57: digital flashcards beat wordlists;
  **perceived usefulness predicted success**. No effect sizes; weakest paper in the set.
  *[abstract]*

### Incidental & contextual learning from input
- **Schmitt & Schmitt (2020, CUP)** — 884 cites. Standard reference; incidental and
  intentional learning as complementary strands; formulaic language as core knowledge.
- **Webb, Uchihara & Yanagisawa (2023, Language Teaching)** — 92 cites. 24 studies,
  N=2,771: incidental pickup is only **9–18% of target words per exposure** (6–17%
  delayed). Reading-while-listening is the best delayed condition (17%); viewing alone
  weakest (7%/5%). *[abstract]*
- **Yanagisawa, Webb & Uchihara (2020, SSLA)** — 83 cites. 42 studies, N=3,802: glossed
  beats non-glossed reading (45% vs 27% immediate); **multiple-choice glosses most
  effective, in-text/glossary popups least**; **L1 glosses beat L2 at all proficiencies**;
  gloss *mode* (text/picture/audio) makes no difference. *[abstract]*
- **Yanagisawa & Webb (2021, Language Learning)** — 72 cites. 42 studies, N=4,628:
  involvement load predicts learning but explains only 15%/5.1% of variance;
  **evaluation contributes most, then need; search (lookup) contributes nothing**.
  *[abstract]*
- **Montero Perez (2022, Language Teaching)** — 113 cites. Review: captions (L2
  on-screen text) vs subtitles (L1) support vocabulary, listening, comprehension.
  *[abstract]*

### Receptive vs productive
- **Li & Hafner (2021, ReCALL)** — 78 cites. N=85: mobile word cards beat identical
  paper cards; deliberate card study improved **productive (collocation)** knowledge too.
  No effect sizes. *[abstract]*
- **Teng (2022, ILLT)** — 70 cites. N=125 RCT: additive richness gradient — definition +
  word info + **video** best on learning and 2-week retention. No effect sizes.
  *[abstract]*

### AI / LLM language learning
- **Song & Song (2023, Front. Psych.)** — 623 cites. N=50: ChatGPT-assisted instruction
  improved EFL writing and motivation; flagged over-reliance and contextual-accuracy
  concerns. No effect sizes. *[abstract]*
- **Wei (2023, Front. Psych.)** — 468 cites. N=60: AI instruction raised achievement
  (incl. vocabulary), motivation, and self-regulated learning. No effect sizes.
  *[abstract]*
- **Tai & Chen (2024, Computers & Education)** — 194 cites. **N=85 elementary EFL
  learners**: GenAI voice chatbot practice beat conventional instruction on speaking;
  solo ≈ paired. *[beyond-abstract via institutional page]*
- **Jeon (2021, CALL)** — 186 cites. **N=53 Korean primary-school EFL**: chatbot
  **dynamic assessment with graduated hints beat definition-giving** on immediate and
  delayed tests, receptive *and* productive; interaction logs yielded diagnostic ability
  estimates. *[abstract]*
- **Zhang & Huang (2024, Heliyon)** — 92 cites. N=52, 8 weeks: LLM chatbot beat control
  on receptive and productive vocabulary; strongest on **long-term productive
  retention**. *[abstract]*
- **Wu (2024, System)** — 60 cites. Meta-analysis of AI-in-L2 moderators.
  *[title-grounded — no abstract recovered]*

### Automatic question & item generation
- **Lee et al. (2023, Edu & IT)** — 206 cites. Few-shot ChatGPT AQG with teacher
  validation: overall CVI 0.89 but **validity varies per question-type×format cell down
  to unacceptable (CVI 0.50)** — pooled averages hide defective types; authors recommend
  collaborative AI–teacher generation. *[beyond-abstract]*
- **Mulla & Gharpure (2023, Progress in AI)** — 125 cites. AQG review: **no reliable
  automatic quality metric exists**; human/response-data evaluation remains the
  standard. *[abstract via Semantic Scholar]*
- **Xiao et al. (2023, BEA @ ACL)** — 121 cites. ChatGPT passages for Chinese
  middle-schoolers rated **above human-written textbook passages** (preferred 0.87 vs
  0.13), **but generated questions lagged** ("too straightforward, obvious patterns") —
  deployment pattern was generate-a-pool + teacher-select, plus an automated toxicity
  screen. *[full-text]*
- **Rodriguez-Torrealba et al. (2022, ESWA)** — 112 cites. T5 MCQ pipeline decomposed
  into question generation / **answer validation** / distractor generation; embedding
  cosine similarity proposed for distractor screening; expert review found items
  measure "retention more than comprehension." *[abstract]*
- **Attali et al. (2022, Frontiers in AI)** — 79 cites. ETS/Duolingo: passage+item
  co-generation at operational scale, validated by **human review plus psychometric
  analysis of live response data**. *[abstract]*

### Games, gamification & multimodal
- **Shortt et al. (2021, CALL)** — 315 cites. Duolingo literature review: rich *design*
  literature, thin *outcome* evidence. *[abstract]*
- **Divekar et al. (2021, CALL)** — 228 cites. AI+XR immersive conversation, N=10
  adults: retained vocabulary gains. Directional only. *[abstract]*
- **Fan, Antle & Warren (2020, JECR)** — 119 cites. 53 papers on AR for early language
  learning: effective combo is **multimedia + advance organizers**; game mechanics +
  discovery boost **motivation** specifically. *[abstract]*
- **Zhang & Hasim (2023, Front. Psych.)** — 99 cites. 40 studies: **feedback is the #1
  gamification element**; documented drawbacks include **short-lived novelty effects and
  negative effects of competition**. *[abstract]*
- **Thompson & von Gillern (2020, Educ. Research Review)** — 89 cites. Bayesian
  meta-analysis (19 studies): video-game-based instruction gives **moderately large ELL
  vocabulary gains** with low publication bias but high heterogeneity. *[abstract via
  Semantic Scholar]*
- **Ramezanali, Uchihara & Faez (2020, TESOL Quarterly)** — 58 cites. 22 studies: adding
  one gloss mode gives **g=0.46 immediate decaying to g=0.28 delayed**; **more than two
  modes adds nothing**. *[abstract]*

### Apps & technology-assisted learning
- **Loewen, Isbell & Sporn (2020, FLA)** — 126 cites. N=54 Babbel, 12 weeks:
  vocabulary/grammar/oral gains; **study time was the strongest predictor of gains**
  (dose-response). *[abstract]*
- **Hao, Wang & Ardasheva (2021, JREE)** — 92 cites. 45 studies, N=2,374,
  preschool-to-college: tech-assisted vocabulary instruction beats traditional by
  **g=.845** [.625, 1.064], with durable delayed retention; moderators: **mobile >
  computer, game condition, on-the-move setting**; **educational level NOT a significant
  moderator** (tech doesn't work worse for young learners). *[beyond-abstract]*
- **Kessler, Loewen & Gönülal (2023, CALL)** — 55 cites. Babbel ≈ Duolingo on learning
  gains (N=59, 8 weeks); dose-response replicates. *[abstract]*

### Children's vocabulary & literacy
- **Furenes, Kucirkova & Bus (2021, RER)** — 287 cites. 39 studies, n=1,812 ages 1–8:
  plain digitization *hurts* comprehension vs paper, but **story-congruent enhancements
  flip the result**; embedded dictionaries help vocabulary but can cost comprehension;
  **adult mediation still beats independent digital reading**. *[beyond-abstract]*
- **Silverman et al. (2020, RRQ)** — 85 cites. 43 K–5 interventions: vocabulary g=0.85,
  **morphology outcomes g=1.14**, morphology-inclusive interventions → vocabulary g=0.66;
  **English learners benefited more than monolingual students**; effects concentrated on
  researcher-designed measures. *[abstract + verified secondary]*
- **Jing et al. (2023, Child Development)** — 77 cites. 63 studies, N=11,413 ages 0–6:
  designed educational media → vocabulary r=.30 (**e-books strongest category**);
  naturalistic screen exposure r=.07 ≈ null. *[abstract]*
- **Savva, Higgins & Beckmann (2021, JCAL)** — 53 cites. N=2,317 ages 3–8: e-storybooks
  give g=0.25 overall, **vocabulary g=0.40, expressive vocabulary g=0.54** (largest
  effect); digital features + adult scaffolding = best combination. *[abstract]*

---

## Cross-cutting themes (updated)

1. **Retrieval beats re-exposure — and delayed retention is the only honest metric.**
   Huang, Terai, NRP, Webb 2020 (immediate gains collapse 20–33 points by delayed test),
   Ramezanali (g halves at delay), Hao (in-app/researcher measures inflate effects).
2. **Production must be earned per learner.** Terai's interaction; Webb 2023's
   proficiency moderation of incidental pickup; Savva's expressive-vocabulary result
   (g=0.54) as the payoff side.
3. **Generated questions are the weak artifact of LLM pipelines.** Susanti (26% fail
   discrimination), Xiao ("too straightforward"), Rodriguez-Torrealba ("retention not
   comprehension"), Lee (per-type validity variance) — four independent sources converge.
   Passages/stories are at or above human quality; questions need QA.
4. **Multimodal wins within a strict load budget.** Yu (overload β=−0.53), Ramezanali
   (≤2 modes), Furenes (incongruence hurts; congruence flips screen inferiority), Fan
   (multimedia + organizer, not multimedia alone). The bundle must be coordinated, not
   stacked.
5. **Exposure is an accumulation game with a quality weighting.** Webb 2023 (9–18% per
   exposure) mandates exposure counting; Jing (naturalistic r=.07) says raw counts are
   weak — designed learning moments are the unit that matters.
6. **Motivation has documented failure modes** — post-mastery stagnation (Yu),
   short-lived novelty (Zhang & Hasim), competition downsides (Zhang & Hasim) — while
   dose-response (Loewen, Kessler) makes daily habit the outcome that pays.
7. **Evaluation beats lookup at every grain size.** Involvement-load meta (search
   contributes nothing), glossing meta (MC glosses best, popups worst), Jeon (graduated
   hints beat answer-giving at primary age). This is the strongest *new* through-line.

---

## Improvement opportunities

Re-tiered against the full 40-paper evidence base. Each item cites its support;
*[extrapolation]* marks adult→child leaps.

### Tier 1 — strongest evidence, direct fit

**T1. Shift the practice mix toward recall/production as words progress.**
Support: Huang; Terai; NRP #5; Webb 2020 (activity choice drives 4× outcome spread);
Savva (expressive vocabulary is the biggest e-book effect, g=0.54); Li & Hafner (cards
move productive knowledge); Zhang & Huang (productive retention is the LLM-chatbot
standout); Hao (game interventions show larger effects on productive tests, d=.839 vs
.332). Make per-word receptive/productive coverage a tracked metric; weight mid/high
mastery words toward TERM_ANSWER and sentence-write. *Touches: NextPracticeWordView mix,
SRS, teacher dashboard.*

**T2. Gate productive question types per learner, not just per content.**
Terai (retrieval must be difficult *but successful*; production pays off only above a
proficiency threshold) + Webb 2023 (proficiency moderates incidental pickup) + Thompson
& von Gillern (grade/proficiency moderators). Our only gate is content-side (guided-only
floor at Lexile ≤ 600). Add a learner-side gate: TERM_ANSWER / OPEN sentence-write
unlock after demonstrated receptive success. Sequence recognition → form recall (Terai's
d=1.20 gap). *[extrapolation]* *Touches: serve logic, question-type policy, mastery.*

**T3. Build item analytics over `UserAnswer` data — stratified per question type.**
Susanti (26% defective even from a mature generator; analytics agree with expert
judgment) + Mulla & Gharpure (no reliable automatic quality metric — response data is
the standard) + Attali (ETS/Duolingo run exactly this loop operationally) + Lee
(**stratify per question type — pooled averages hide defective cells**, CVI 0.89 overall
vs 0.50 worst cell). Compute per-question difficulty and upper/lower-27% discrimination
(by mastery level); flag discrimination < 0.2, p < 0.2 / > 0.9; add the "distractor whose
pick rate *rises* with mastery" alarm. Also mine sentence-write revision logs as
diagnostics (Jeon: hint-needed vs unassisted-correct is ability signal; we already
classify `productive_correct`/`productive_recovered`). *Touches: analytics, admin
review, question generation feedback loop.*

**T4. Add semantic distractor checks to generation validation.**
Susanti's defect taxonomy + Rodriguez-Torrealba (embedding cosine screening is the
literature's own proposed fix — we already own Qwen3 embeddings). Reject distractors too
close to the keyed answer; reject suffix/stem-only collisions ("plainly"/"immeasurably");
prompt rule: correct answer must survive the **substitution test** (closest in meaning
AND natural in context; no distractor a better contextual fit — COW+MRW were 38% of
defects); keep answer wording ≤ the question's difficulty band (Susanti's inverted-
discrimination case). *Touches: step_questions.py validation + prompts.*

**T5. Enforce a cognitive-load budget in the student UI.**
Yu (retention β=−0.53 per SD of overload; optimum 3–4 channels) + Ramezanali (**more
than two modes per word encounter adds nothing**) + Furenes (incongruent interactivity
*causes* the screen inferiority effect) + Fan (multimedia alone wasn't the effective
unit — the pairing with an organizer was). Concrete rules: ≤2 coordinated modes per word
encounter; no decorative hotspots/mini-games in the GN reader; hints on demand;
`prefers-reduced-motion` honored; pronunciation manual. *Touches: practice UI, GN
reader, audiobook autoplay.*

**T6. Coordinate the multimodal bundle — GN + TTS read-along + cloze as one experience.**
This is now the best-supported bet in the report: Teng (additive richness gradient);
Webb 2023 (**reading-while-listening = best delayed retention, 17%**; viewing alone
weakest 7%/5%); Montero Perez (captions literature); Hao (dual-coding grounding);
Furenes (story-congruent enhancement makes digital beat paper); Jing (e-books strongest
experimental category, r=.30); Savva (vocabulary g=0.40); Fan (multimedia + advance
organizer — our primers are the organizer; keep them coupled to the reading path).
Caveats: coordinate, don't stack (T5); the art is engagement scaffolding — text + TTS +
practice do the measurable learning (Webb 2023 viewing data). Default Auto-read ON for
lower grades; keep cloze linked to the selected GN. *Touches: narrative content,
audiobook, cloze staging, primer coupling.*

**N1 (new). Multiple-choice glosses in the reader — evaluation, not lookup.**
Two converging metas: MC glosses are the *most* effective gloss type and in-text/glossary
popups the *least* (Yanagisawa 2020, +19pp for any gloss); within involvement load,
**search contributes nothing while evaluation contributes most** (Yanagisawa & Webb
2021). Turn word-tap in the GN/infographic reader into a 3-option "which meaning fits
here?" micro-retrieval (reusing primer definitions + generated distractors), and do not
invest in dictionary-style popups. Furenes adds the child-side caveat: embedded
dictionaries help vocabulary but can cost comprehension — so on-demand tap, never
interruptive auto-popup. *[extrapolation: adult reading studies; Furenes is child
evidence]* *Touches: GN/Infographic reader word-tap UX.*

### Tier 2 — well-supported, needs design or calibration

**T7. Vary contexts per word across the pack.**
Yu (52% transfer failure) + Nakata & Elgort (spacing + varied sentences build explicit
knowledge; the effective condition is literally "same word, 3 different contexts, guess
+ feedback each time"). Extend the existing guided→open "different angle" principle to
cloze/question scenarios; at serve time prefer unseen scenarios. *Touches: generation
prompts (cloze/questions/sentence-write), serve logic.*

**T8. Fight post-mastery stagnation and novelty decay.**
Yu (HR=1.8 stagnation) + Zhang & Hasim ("short-lived positive effect" is a documented
gamification pattern). Interleave next-set previews when the queue is mastery-dominated;
resurface mastered words with *new* challenge scenarios; milestone variety over more
points. *Touches: SRS serve logic, gamification.*

**T9. Gate top mastery on delayed, repeated, productive evidence.**
Webb 2020 (same-session success overstates learning by 20–33 points; form recall decays
worst) + Kim & Webb (number of *sessions* moderates spacing effects) + Nakata (cited in
Terai: ~5 feedback-coupled retrievals) + Zhang & Huang (productive retention) +
Silverman/Hao (researcher-developed measures inflate effects — in-app MC success ≠
transferable knowledge). Require ~5 successful retrievals distributed across sessions,
with mastery 6–7 additionally requiring a `productive_correct` verdict. *Touches:
mastery promotion logic.*

**T10. Add a flip-card self-test mode.**
Huang's literal intervention; Yüksel (digital flashcards > wordlists — teacher-prepared
cards, so ship with reviewed content); Li & Hafner (mobile cards > paper). Caveat:
self-check honesty at age 7; Yüksel is the weakest source here (N=57, no effect sizes).
*Touches: practice UI, primers/translations, media reuse.*

**T11. Keep graduated, error-specific feedback with a re-retrieval loop — hints, never
rewrites.**
Jeon is the strongest single support: **graduated hints beat definition-giving at
primary-school age**, immediate and delayed, receptive and productive. Plus: Terai
(feedback after every attempt), Yu (error-specific feedback most valued; "too brief"
complaint → optional deeper tier), Zhang & Hasim (feedback is the #1 gamification
element), Song & Song (over-reliance concern → judge hints, doesn't rewrite). Add an
on-demand "tell me more" tier (escalating hint granularity within the existing revision
caps), don't lengthen defaults (T5). Kessler nuance: don't over-invest feedback
complexity into the receptive MC flow — the value-add is on production. *Touches:
sentence-write judge, PracticeView feedback components.*

**T12. Verify the L1–L5 ladder as a *delayed* difficulty gradient.**
Susanti + Xiao ("too straightforward" generated questions) + Rodriguez-Torrealba
(retention-not-comprehension bias) + Webb 2020 (use delayed/next-session accuracy, not
within-session accuracy — otherwise the check measures test format, not learning). LLM
MC generation naturally fills the easy/recognition end; the gradient check should expect
exactly that failure mode. *Touches: analytics, question generation.*

**N2 (new). Give L1 translations first-class status in the reader and item pool.**
Yanagisawa 2020: **L1 glosses beat L2 at all proficiency levels**; Montero Perez:
subtitles (L1) and captions (L2) are distinct, separately-useful supports. Surface the
L1 translation prominently alongside the kid-friendly definition in the reader (and as
an option in N1's MC glosses); consider a toggleable L1 aid per page for
comprehension-blocked students. *[extrapolation]* *Touches: reader UX, translation
display.*

**N3 (new). Independent answer-verification pass on generated questions.**
Rodriguez-Torrealba's generator–evaluator decomposition: re-solve each generated item
independently and reject items where the independent answer ≠ keyed answer — a cheap
second LLM call that catches mis-keyed items structural validation can't. *Touches:
step_questions.py.*

**N4 (new). Generate-and-select for questions, plus an automated safety screen.**
Xiao's deployment pattern (pool + teacher-select; toxicity check before release) and
Lee's collaborative-generation conclusion mirror our 3-candidate admin-select model for
narrative content — but questions currently ship with no per-item human review and no
automated safety pass on generated text (cloze, GN scripts, questions). Add a question
review surface (or candidate pools for high-stakes items) and a cheap safety screen
before admin review. *Touches: generation pipeline, GenerationReview.*

**N5 (new). Delayed-retention metric in dashboards.**
Webb 2020 (immediate→delayed collapse) + Hao (delayed retention is where tech advantage
persists). Surface per-word-set delayed retention (accuracy on first SRS review ≥24h
after last correct answer) so "completed pack" isn't read as "learned." *Touches:
dashboards, analytics.*

**N6 (new). Instrument time-on-task as a first-class KPI; soften the daily cap into a
goal.**
Loewen + Kessler (dose-response replicates across apps and languages: minutes practiced
is the strongest outcome predictor). Show weekly active minutes in teacher dashboards;
keep the daily limit as burnout/gaming protection but add a clearly separated optional
"extra practice" mode so it doesn't silently throttle a motivated student. Kim & Webb
cuts the other way (distribution across days matters), so extra practice should favor
new-content preview over re-drilling today's words. *Touches: PracticeService cap logic,
dashboards, streak/goal design.*

**N7 (new). Mobile-first student experience.**
Hao's significant moderators: mobile > computer, on-the-move > classroom-restricted.
Verify the student shell (practice view, readers, audio player) is genuinely
mobile-responsive; assume short, anywhere sessions. *Touches: frontend student shell.*

**N8 (new). Word support must be on-demand and story-embedded; keep the teacher in the
loop.**
Furenes + Savva: story-congruent, on-demand word support helps vocabulary; interruptive
features cost comprehension; **adult scaffolding beats independent digital reading**
everywhere tested. Position teacher assignment/dashboards as pedagogically load-bearing,
not admin chrome. *Touches: reader UX, teacher portal, product positioning.*

### Tier 3 — promising extrapolations / weaker evidence

**T13. L1-translation recall as a question type for low-proficiency students.**
Terai's recommended safe direction; Huang's measured outcome; now supported by the
glossing meta's L1>L2 result. Requires per-student L1 data and distractor care.
*[extrapolation]*

**T14. Track exposures per word across contexts — weighted by quality.**
Webb 2023 (9–18% per exposure) makes counting evidence-mandated; Jing (naturalistic
r=.07) says weight designed learning moments (questions, cloze, production) over raw
views when the metric feeds scheduling. *Touches: progress model, dashboard.*

**T15. Word-frequency-band metadata at WORD_LOOKUP** (Hiebert & Kamil; Schmitt &
Schmitt's word-list treatment).

**T16. Word-family/morphology content in primers — upgraded.**
Silverman: morphology outcomes **g=1.14**, morphology-inclusive interventions →
vocabulary g=0.66, in exactly the K–5 band — the largest single effect in this review.
Add root + transparent derivatives + one affix note to primers; optionally a
word-family question variant. Schmitt & Schmitt add **formulaic language** (collocations)
as a distinct target — a collocation-completion item type or collocation checks in judge
hints covers a productive dimension we currently miss (Li & Hafner operationalized
productive knowledge *as* collocation knowledge). *Touches: primer/question generation,
judge prompts.*

**T17. Student-facing "word bank" growth widget.**
Yu (β=.59); Fan (game mechanics + discovery/collection boost motivation specifically);
Yüksel (perceived usefulness predicts success); Kessler (felt-progress lever).

**T18. Cultural-diversity check in admin review** (Yu, qualitative; Xiao's educator-loop
pattern).

**T19. Sanity-check early SRS intervals — descoped.**
Kim & Webb: longer intervals beat shorter on delayed tests, but **equal ≈ expanding
schedules** — interval *shape* is not the high-stakes parameter. Scope T19 to a coarse
check that early reviews aren't clustered within a day; do not invest in expanding-
interval optimization. Ramezanali's g=0.46→0.28 decay is the retention curve the
schedule exists to defend.

**T20. Cognate highlighting in translations** — Spanish-L1 only; verify population
first.

**N9 (new). Avoid competitive ranking mechanics for ages 7–14.**
Zhang & Hasim: negative effects of gamified competition are a named drawback. Our
personal-progress surfaces (streaks, mastery, XP, word bank) are the safer set; if
leaderboards are ever requested, prefer class-scoped cooperative framing. *Touches:
gamification design.*

### Explicitly de-prioritized

- **Free-reading library for vocabulary gains**: NRP found no experimental support;
  Webb 2023 quantifies why (9–18% per exposure — passive exposure without retrieval
  practice abandons >80% of target words); Jing: naturalistic exposure r≈.07.
- **General-purpose chatbot/free-chat mode**: Tai & Chen and Divekar are positive but
  off-outcome (speaking; N=10 adults); child-safety constraints bind. Voice/pronunciation
  practice is the adjacent, better-supported future mode.
- **Expanding-interval SRS math** (see T19 descope).

---

## Suggested first experiments (no new infrastructure needed)

1. **Item analytics report** (T3/T4/T12): SQL/analysis over existing `UserAnswer` rows —
   per-question difficulty + discrimination **stratified by question type** (Lee's
   lesson), MI-distractor alarms, L1–L5 gradient checked on *delayed* accuracy. Highest
   information value per effort; also tests whether the AQG psychometrics transfer to
   our item types.
2. **Recall-vs-recognition mix A/B** (T1): randomize mid-mastery words per student into
   recall-heavy vs recognition-heavy practice; outcome = **7-day delayed retention**
   (Webb 2020's collapse is the effect we're trying to beat).
3. **Productive-gate simulation** (T2/T9): offline analysis of how mastery distributions
   would change if TERM_ANSWER/OPEN required prior receptive success.
4. **Gloss interaction prototype** (N1): A/B tap-to-reveal definition vs 3-option MC
   gloss in the reader; outcome = next-day retention of tapped words. Directly tests the
   two convergent metas on our own population.

## What the papers say is already right

The full corpus strongly supports the app's core bets: multi-method instruction (NRP #8);
spaced retrieval (Kim & Webb); story + practice pairing (Webb 2023's 9–18% makes practice
non-optional; Schmitt & Schmitt's dual strands); the GN + TTS + cloze bundle (T6's nine
sources); production tasks with graduated feedback (Jeon, Savva); technology delivery
(Hao g=.845, with **educational level not a significant moderator** — tech works for
young learners); teacher-mediated deployment (Furenes, Savva); and the target population
itself (Silverman: **English learners benefit most** from explicit language-comprehension
instruction). The opportunities above are tuning, gating, QA, and instrumentation — not
re-architecture. The clearest gaps the literature exposes: no psychometric QA loop on
generated questions (T3/T4/N3/N4), lookup-style word support instead of evaluative
micro-retrieval in the reader (N1), and no delayed-retention or dose instrumentation
(N5/N6).
