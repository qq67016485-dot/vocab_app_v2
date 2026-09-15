# Family & Trial Self-Serve Learning — Product Proposal

> **Status:** proposal for product-team review. Part 1 is the business case and the reasoning
> behind every product decision. Part 2 is the technical implementation plan (approved in
> principle, execution pending this review).
>
> **Deployment assumption: clean slate.** The family features ship together with a full data
> reset — no existing accounts or content need to be preserved. The plan therefore contains no
> backfill migrations and no legacy-behavior compatibility shims.

---

# Part 1 — Business Case

## 1. Executive summary

Today the app can only be used one way: a teacher creates student accounts and assigns word sets.
That makes our growth entirely dependent on institutional sales — the slowest, most expensive
channel in edtech. This proposal adds a second channel: **parents sign up for a free trial on
their own, find word sets matching their child's textbook, and start their child learning within
minutes — no teacher involved.** The same mechanism also makes school usage and home usage
reinforce each other instead of competing: a student has **one portable account** that can be
linked to a classroom and unlinked again, keeping the account (and its history, streaks, and
progress) for life.

The build is deliberately small: no parent role, no payment system, no new content pipeline. It
reuses the existing student account, the existing word-set library, and the existing assignment
machinery, adding only a signup page, a PIN-gated "Learning Management" area, a trial quota,
and a student code for classroom linking.

## 2. The problem: a single, slow growth channel

Selling to teachers and schools means procurement cycles, budget approvals, pilots, and training
— months from first demo to first student. Every student on the platform today arrived through
that funnel. Three consequences:

- **Slow feedback.** We learn what families actually value only after a school adopts us.
- **High cost per student.** Each new cohort requires a new institutional sale.
- **Fragility.** Losing one school means losing every student attached to it — the student
  accounts effectively die when the class ends.

Meanwhile, the people with the strongest motivation and the shortest decision cycle — parents who
want their child to learn vocabulary *this week* — have no way in at all.

## 3. The opportunity: parent-led trials

Parents are demo-able directly: show them a graphic novel built from their child's actual
textbook words and the value is self-evident. What they need is a way to act on that demo
immediately. This proposal gives them:

1. **Self-serve signup** — a trial account in under two minutes: one password, plus an optional
   reading-level calibration (§5.10).
2. **A catalog they can search by textbook/unit** — the content already exists; teachers have
   been creating and publishing word sets all along.
3. **A management area gated by a Parent PIN** — the parent's supervision and control point:
   progress (with concrete praise prompts, §5.12), settings, and veto power over word-set
   choice (§5.9).
4. **A trial quota** (2,000 words, lifetime) that makes the trial genuinely useful for months
   while capping our exposure, ready to become the paywall boundary later.
5. **Student self-assignment, on by default** — children can choose word sets from the catalog
   from day one, so a busy parent's silence never stalls a child's momentum, with pacing and
   difficulty guardrails standing in for the teacher's judgment (§5.9, §5.11).

## 4. The deeper win: school and home stop competing and start compounding

The strategic move in this proposal is not the trial itself — it is that **the account is the
asset, and it is portable**.

- **Home → School.** A family-trial student tells their teacher their student code; the teacher
  adds the existing account to the class in seconds. Every parent-channel signup is a Trojan
  horse into a classroom: the teacher inherits a student who already has history and momentum,
  and the shortest path to a school sale is a teacher who sees it working on their own roster.
- **School → Home.** When a student leaves a school, their account doesn't die — it reverts to a
  family/trial account. Every school cohort becomes a pool of family prospects who already know
  the product. Today, churn is total; with this, institutional churn becomes consumer leads.

While linked to a school, the account is treated as school-paid (no trial quota; teacher
assignments never consume the family's quota). While unlinked, normal trial rules apply. One
account, two channels, each feeding the other.

## 5. Key decisions and the logic behind them

Each decision below was stress-tested against alternatives. The rejected alternatives are listed
because the product team should know what we are explicitly *not* doing, and why.

### 5.1 One portable student account — no parent role

**Decision:** The account a parent creates at signup IS the student's practice account
(`role=STUDENT`). There is no separate parent login.

**Logic:** A parent role doubles the account system (two logins per child, a linking flow, a
parent UI) to solve a problem that is really about *authorization, not identity*: who is allowed
to assign word sets and see progress. A Parent PIN on the same account solves authorization
at a fraction of the build cost. It also makes the portability story (§4) possible — a parent
login can't follow a child into a classroom, but a student account can.

**Rejected:** a PARENT role with linked child accounts (more machinery, breaks portability);
student self-registration with no parent gate (no buyer in the loop, COPPA optics, weak retention
lever).

### 5.2 The management area is gated by a Parent PIN — created on first entry, required on every entry

**Decision:** Parent and child share one login (the child uses it daily). The "Learning
Management" area — progress, settings, credential changes, the autonomy toggle, and dropping
word sets — is gated by a **Parent PIN** (6 digits). Three rules define the PIN's lifecycle:

1. **Not collected at signup.** Signup collects exactly one password. The PIN is created the
   first time anyone enters the management area, with parent-directed copy ("Parents: create a
   private PIN — your child uses this app daily; this keeps word-set choices and settings in
   your hands").
2. **Required on every entry.** There is no "remembered for this session" state: navigating
   away from the management area locks it, and a 15-minute idle timeout is the server-side
   backstop. A parent who checks progress on the family tablet and walks away never leaves the
   gate open — and kids never log out, so session-length unlock would be no lock at all.
3. **Parent-controlled sharing.** The parent may keep the PIN private or share it with the
   child — and can revoke that sharing by changing the PIN.

**Logic:**

- *Why a gate at all:* parent and child share the login credentials, so the PIN is the only
  thing that distinguishes "parent" from "child" inside the app. Without it the child can
  change the daily limit, change the email, and change the login password — locking the parent
  out of their own account. "Re-enter your password for sensitive actions" is no substitute:
  the child knows that password.
- *Why not at signup:* a signup form with two password fields ("whose is each one?") is
  confusing and adds drop-off friction to the trial funnel's first step. Moving PIN creation to
  first management-area entry puts it in context — the parent is looking at the thing the PIN
  protects when they create it.
- *Why the setup race is acceptable:* right after signup, the parent is the one holding the
  session — the child doesn't have credentials yet — and the post-signup redirect walks the
  parent straight into PIN setup before the child ever logs in. For school-created accounts
  the child could theoretically set the PIN before the parent; that is inherent to any
  setup-on-first-use model and is mitigated by copy and teacher communication, not machinery.
- *Why every-entry rather than session unlock:* the device this gate protects against is the
  shared family tablet, and children never log out. A session flag would leave the area open
  indefinitely after the parent's first visit. Per-entry PIN costs the parent ~2 seconds per
  visit — they are in the area to do minutes of work anyway — and it makes the gate real.
- *Why a PIN rather than a second password:* it is form-distinct from the login password, which
  kills the mix-up risk ("Parent PIN" vs "password" reads differently, gets typed differently,
  gets written down differently), and it matches the parental-control mental model parents
  already know from Netflix profiles and device lock screens. A 6-digit PIN behind the planned
  10/minute per-user unlock throttle takes ~2 months of continuous attempts to brute force
  against a single account — adequate for what it protects.

**Rejected:** no gate (child can lock the parent out of credentials/settings); session-length
unlock (no lock at all on shared devices — see above); two passwords at signup (the confusion
this section is designed to eliminate); age-based autonomy rules (arbitrary, unverifiable); a
separate parent app (build cost, and most parents of this age group manage alongside the child
on one device anyway).

**Upgrade path (not this build):** once an email backend exists (needed for password reset
anyway), the parent's email becomes the identity anchor — forgotten PIN resets via email, and
email-verified unlock could eventually replace the PIN. Nothing in this design precludes that.

### 5.3 Self-serve trial signup, email required

**Decision:** Public signup; the parent provides username, email, one login password, the
child's native language, and an optional reading-level calibration (§5.10). No management
credential is collected at signup — the Parent PIN is created on first entry to the management
area (§5.2).

**Logic:** A trial motion lives or dies on friction. Manual provisioning ("contact us for a
demo account") caps trials at our personal bandwidth and kills the after-hours impulse signup.
Email is required for two business reasons, not technical ones: it is the recovery path for a
forgotten PIN or password (a locked-out parent is otherwise a lost account and a support
ticket), and it is the channel for converting trial users when the paywall arrives.

**Rejected:** provisioned demo accounts (doesn't scale); optional/no email (no recovery, no
conversion channel).

### 5.4 Trial quota: 2,000 words, lifetime, no refund

**Decision:** A trial account may self-assign word sets totaling 2,000 words (counted as all
words in the set at assign time, once per unique set, never refunded on drop). It is a settings
constant, designed to be tightened when the paywall lands.

**Logic:** Three candidate currencies were considered — wordsets, time, words. **Words** win
because wordsets vary in size (typically 8–20 words), so a per-set cap is arbitrary, and because
words map to learning value: a parent can see "2,000 words learned" as a real outcome.
**Lifetime** wins over concurrent slots because it is trivially explainable, requires no refund
bookkeeping when partially-completed sets are dropped, and — most importantly — its exhaustion
is a *natural conversion moment*: the family has demonstrably gotten 2,000 words of value when
we ask them to pay. At 8–20 words per set, 2,000 words is ~100–250 sets — effectively uncapped
for any realistic trial. That is deliberate while no paywall exists (an exhausted trial with
nowhere to upgrade is a dead end); the number is a settings constant precisely so it can be
tightened to a real boundary when payments ship.

**Cost side:** serving pre-generated word sets costs essentially nothing (content is already
generated and reviewed). The real marginal cost of a trial user is the per-answer LLM judge for
sentence-writing questions, bounded by the existing daily question limit. The quota caps
long-term exposure; the daily cap bounds the burn rate.

**Rejected:** concurrent-slot wordset caps (refund bookkeeping, weaker conversion moment);
time-limited trial (a 14-day fuse with no payment backend ready strands engaged users — the
classic mistake of starting a countdown before the store is open).

### 5.5 Catalog = public word sets with published content

**Decision:** Family accounts browse and assign from existing `is_public=True` word sets that
have published (admin-selected) instructional content. No request-a-set form, no self-serve
generation in this build.

**Logic:** The fastest catalog is the one that already exists. Teachers have been building word
sets against real curricula ("Wonders Reading", grade levels, units); the published-content gate
(selected graphic novel or infographic) is a hard quality floor, so nothing half-built is ever
visible. This turns teacher-created content into acquisition inventory at zero marginal curation
cost. The accepted risk — a teacher's "public" set becomes visible to families, and some titles
are cryptic ("Unit 4 Week 2") — is mitigated by the quality gate and by the fact that public
already meant "visible to other teachers"; we are widening the audience, not the content.

**Rejected:** a new curated `listed_in_catalog` flag (right answer at scale, wrong answer at
launch — an empty curated catalog is worse than an imperfect full one, and the flag can be added
later without migration pain); exposing all generated sets (no quality floor).

### 5.6 Unique student code + teacher claim-by-code

**Decision:** Every student gets an auto-generated, human-readable `student_code`
(8 unambiguous characters). A teacher can claim an existing account by code; possession of the
code is consent (same model as a class code).

**Logic:** This is the mechanism that makes §4 work. Without it, "a family student joins a
class" means a second account (split history, dead streaks) or manual admin intervention. With
it, it is a 10-second teacher action. The code — not the username/password — is the sharing
surface, so a teacher never touches the family's credentials. Removing a student from a roster
only unlinks; a school can never delete a family-owned account (see engineering note E1 in
Part 2: roster removal today *deletes the student account* — that must change before
claim-by-code ships).

**Rejected:** teacher search by name/email (privacy leak, duplicates); student-approval flow
(adds a round-trip for no real consent gain — the code is only ever shared deliberately).

### 5.7 School-linked accounts keep family self-management

**Decision:** While linked to a teacher, the quota is suspended and teacher assignments don't
consume it — but the family management area stays fully functional (progress visibility always;
family self-assign allowed).

**Logic:** The parent of a school student is precisely the parent most likely to pay: they have
seen the product work. Cutting them off from progress visibility the moment a school adopts
their child would hide our best evidence of value from our best prospects. Authority stays
clean: the teacher controls classroom assignments; the family controls the account itself
(credentials, language, daily limit) and may add home sets on top.

**Rejected:** "school takes over" mode (breaks the conversion story for our warmest audience).

### 5.8 One account = one child

**Decision:** A parent with two children signs up twice (same email allowed).

**Logic:** Every piece of learning state — SRS scheduling, streaks, XP, question history — is
per-account today. Multi-child profiles would fork all of it for an edge case that two signups
cover adequately. Revisit only if multi-kid families prove to be the core segment.

### 5.9 Student self-assignment, on by default — parents supervise and veto

**Decision:** Accounts are created with **self-assignment enabled**: from day one, the
student portal has a "Choose Word Sets" page where the child can assign sets from the same
quality-gated catalog, no PIN required — subject to the learning guardrails in §5.11. The
parent retains override levers, all visible in the management area: a prominent **autonomy
toggle** (one tap, PIN-gated, turns kid self-assignment off), **unassign** (drop any
self-assigned set — parent-only, even while autonomy is on), and the quota banner showing
consumption. An "Autonomy on" badge makes the state impossible to miss. The toggle defaults
to ON for all accounts (clean-slate deployment: there are no legacy accounts whose
teacher-led behavior needs preserving).

**Logic:**

- *The problem it solves:* a typical set is 8–20 words, which a practicing child finishes in
  days, not weeks. Assignment is therefore a genuinely routine task — and the parents this
  channel targets are busy; they will not open the app every few days. A child who finishes a
  set and finds nothing new assigned stalls exactly when the habit is strongest; that stall is
  where streaks die and trial accounts quietly churn. Default-off would hide the fix behind a
  toggle that the busiest parents — the ones who need it most — would never find.
- *Why default-on is safe:* assigning work is close to harmless in this product. The catalog
  is quality-gated (§5.5), so there is no "bad" content to pick; the guardrails in §5.11 keep
  picks near the child's level and pace; and the lifetime quota caps total consumption
  regardless of who clicks assign — a child cannot exceed the family's boundary, only
  influence which sets fill it. The worst realistic outcome of a kid self-assigning is more
  learning in a different order.
- *What the parent keeps:* visibility (every self-assigned set appears in the management area
  with its progress) and veto (toggle off, unassign). The control story shifts from
  pre-approval to supervise-and-override — an opt-out, not an opt-in. The product team should
  accept that framing consciously: we believe it matches how busy families actually behave,
  and the alternative (opt-in) quietly kills the trial for exactly the parents it targets.
- *Settings and credentials are NOT part of the delegation.* Self-assignment is the only thing
  handed over. Daily limit, native language, email, passwords, PIN, and unassign all stay
  behind the PIN regardless of the toggle.
- *Paywall-time revisit:* the calculus changes when the quota tightens into a real spending
  boundary — kid-directed assignment then means kid-directed spending. Re-evaluate the default
  (or add parent confirmation above a threshold) when payments ship; the toggle infrastructure
  makes that a product decision, not a rebuild.

**Rejected:** opt-in autonomy toggle (the families most likely to churn never find it —
measured as the opt-out rate instead); assignment rights with no parent veto (irrevocable
delegation — parents of younger children rightly expect an override); kid-requests →
parent-approves (the busy parent is still the bottleneck, the child waits and loses momentum,
and there is no email backend to notify the parent with); assignment queue with auto-advance
(solves the same problem but adds a queue model, ordering UI, and a completion trigger — more
machinery for the same outcome; reconsider later if parents ask for planned sequences).

### 5.10 Level calibration at signup — Lexile if known, LLM-estimated from a description if not

**Decision:** Signup includes an optional, skippable calibration step: **"What is your child's
current Lexile level?"** (numeric field) with a **"Not sure? Describe your child's reading"**
free-text alternative (grade, school level, books they read, anything). A number is used
directly; a description is mapped to an estimated Lexile by a lightweight LLM call (a new
`lexile_estimator` step — e.g. "she's in 3rd grade and reads Magic Tree House fluently" →
~500L), with a static grade→Lexile reference table as fallback and the estimate **shown to the
parent** ("We estimate about 500L — you can adjust this anytime in settings"). From the chosen
value the account's band is derived as `lexile_min = max(0, L−200)`, `lexile_max = L+300`,
editable later in the management settings. If the parent skips, or estimation fails, the
account keeps today's permissive default (0–2000) — calibration never blocks signup.

**Logic:** this is the substitute for the leveling judgment a teacher silently provides. The
two things that make self-assignment pedagogically safe — showing questions at the right
difficulty (the existing `lexile_min/max` filter) and gating out-of-reach word sets (§5.11) —
both hang off this band, and without it every family account would run wide open at 0–2000.
Asking for a Lexile number costs almost nothing when the parent knows it (many schools report
it); the free-text path exists because most parents don't, and "what does your child read?"
is something any parent can answer. An LLM is the right tool for that mapping: it handles
exactly the messy inputs a grade dropdown can't ("reads Dog Man alone but struggles with
chapter books"), and the parent-visible estimate keeps a bad guess correctable rather than
invisible. The band is asymmetric (−200/+300) because below-level work is merely easy while
above-level work is *blocking* — a story the child can't read carries no vocabulary.

**Rejected:** no calibration (the 0–2000 status quo — leaves question difficulty and the §5.11
difficulty gate meaningless for family accounts); a grade-only dropdown (ESL learners' reading
levels routinely diverge from grade — exactly our audience); a mandatory diagnostic quiz
(industry standard, but a test as the very first screen is a signup-conversion killer, and the
SRS data refines difficulty implicitly from day one anyway — calibration only needs a rough
starting band, not a measurement).

### 5.11 Pacing and difficulty guardrails for self-assignment

**Decision:** Two guardrails stand in for the pacing a teacher provides, both evaluated at
assign time:

1. **Pacing gate (all family assigns, kid and parent):** a new family assignment is blocked
   when the account has **≥100 unlearned words** — *any* in-progress words (family or school)
   with mastery level below 4 — **or ≥50 backlogged review words** (READY words past their
   due date). Either condition means the learner is underwater; the fix is practice, not more
   sets. The block message says exactly that, with the counts ("You have 63 words waiting for
   review — practice those first!"). Teacher assignments are exempt (the teacher sets the pace
   in class). Thresholds are settings constants.
2. **Difficulty gate (kid assigns only):** a set whose `target_lexile` falls outside the
   child's `[lexile_min, lexile_max]` band (§5.10) cannot be self-assigned by the child — the
   catalog disables the card with a "too hard for now" / "too easy" badge. A
   management-verified parent can still assign it (the badge becomes a warning, not a block):
   parent judgment overrides the band.

**Logic:** the failure mode of default-on autonomy isn't a bad pick — the catalog has no bad
content — it's *novelty-collecting*: new sets deliver fresh stories and completion-XP, so a
child can rack up hundreds of half-learned words while retention quietly collapses (the SRS
"review tsunami": due reviews pile up faster than the daily cap can clear them, attention per
word drops, mastery turns fragile). Teachers prevent this by assigning one set at a time; a
self-directed child needs the constraint encoded. Crucially, the gate targets **learning
state, not set count**: a fast learner who masters words and clears reviews is never blocked,
while a stalled one can't dig the hole deeper. And it counts the learner's *total* load —
a school kid already juggling 80 teacher-assigned words shouldn't be able to pile on five
self-chosen sets. The difficulty gate exists because SRS can reschedule questions but cannot
fix a story the child can't read — above-band content fails at comprehension, before
vocabulary encoding even starts.

**Rejected:** a fixed concurrent-set cap (cruder — punishes fast finishers and permits slow
overload alike); a time-based drip (arbitrary, ignores actual learning); scoping the pacing
count to family-assigned words only (misses school load *and* needs a costlier query); no
guardrails (the review-tsunami failure mode is a retention killer that engagement metrics
would mistake for success).

### 5.12 The parent area prompts praise, not just monitoring

**Decision:** The management progress page leads with a **"Celebrate with your child"** card —
concrete, timely prompts derived from existing data: streak milestones ("5 days in a row —
mention it at dinner!"), words mastered this week ("She mastered 12 words this week — ask her
to teach you one"), and a short **"practice together" fragile-words list** (words the SRS
keeps marking fragile) with simple ideas ("quiz these three in the car"). Copy throughout the
parent area favors specific effort-praise over generic praise.

**Logic:** the pedagogically valuable things an involved adult provides are calibration
(§5.10) and *encouragement grounded in specifics* — not assignment clicks, which §5.9
deliberately made optional. But a busy parent can only encourage what they can see. Streaks
and XP are vanity metrics a parent can't act on; "these 4 words keep coming back wrong" is
something they can use tonight. This is also the parent's return-visit hook: progress framed
as moments-to-celebrate gives the parent a reason to come back weekly, which is the traffic
the eventual paywall conversion depends on.

**Rejected:** metrics-only progress (monitoring without a hook — parents check once and never
return); email digests (right idea, wrong time — needs the email backend; this card is the
in-product version of the same content).

## 6. What we will measure

Instrumentation is minimal in this build, but the trial funnel defines what we watch:

- **Signup → first assignment** (did they find a relevant set? — the catalog's real test)
- **First assignment → first practice session** (did the child actually start?)
- **Week-2+ retention of trial accounts** (is the product habit-forming outside a classroom?)
- **Autonomy opt-out rate** (share of parents who disable self-assignment) and — critically —
  **mastery retention of self-assigned words vs parent/teacher-assigned words** (engagement
  alone would make autonomy look like a win regardless of learning)
- **Calibration coverage** (share of signups providing a level or description) and how often
  parents adjust the estimated band
- **Guardrail hits** (pacing-block and difficulty-block counts) — if pacing blocks fire
  constantly the thresholds are wrong; if never, they may be decorative
- **Quota consumption distribution** (informs the paywall boundary and pricing)
- **Code claims** (home→school conversions) and **linked→unlinked transitions** (school→home
  leads) — the two loops in §4

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Trial users' LLM-judge usage costs money with no revenue | Existing daily question limit bounds burn; quota caps lifetime exposure; judge circuit breaker already degrades gracefully |
| Teacher-public sets have parent-unfriendly titles/metadata | Published-content gate is the floor; a curated catalog flag is a cheap later addition |
| Signup endpoint abuse (spam accounts) | Anon rate throttle; no email verification yet means we treat signups as unverified leads |
| Parent forgets PIN; no reset flow exists yet | Email collected from day one so reset can be built; interim: manual admin reset |
| Child sets the PIN before the parent (setup-on-first-use race) | Post-signup redirect drives the parent into PIN setup immediately, before the child has credentials; school onboarding copy tells parents to set it |
| Parent unlocks the area on a shared device and walks away | PIN is required on every entry (§5.2) — leaving the area locks it, with a 15-minute idle backstop; no persistent unlock state |
| Default-on self-assignment: novelty-collecting beats learning | Pacing + difficulty guardrails (§5.11); mastery-retention metrics (§6) rather than engagement; parent veto (§5.9) |
| LLM level estimate is wrong | Estimate shown to the parent, band editable in settings, band is a starting point the SRS implicitly refines; worst case is a difficulty gate that's slightly off, not a wrong curriculum |
| Guardrails frustrate a fast learner or a deliberately pushing parent | Pacing thresholds are settings constants; parent assigns bypass the difficulty gate; pacing gate never blocks teacher assigns |
| Teacher deletes a family account via roster removal | Engineering prerequisite E1 (Part 2): roster removal becomes unlink-only; account deletion is admin-only |
| Child privacy (COPPA optics) | Parent creates and owns the account; no child PII beyond first name; no child-facing signup (self-assignment is a learning activity on the child's own account, parent-vetoable) |
| Families game the quota with throwaway accounts | Quota is per-account lifetime; content value is cumulative per child, so a fresh account restarts the child's learning — self-defeating |

## 8. Deliberately out of scope (and why)

- **Paywall / plans** — the quota is engineered to become the paywall boundary (a settings
  change plus a payment provider), but building payments before validating the trial funnel is
  premature.
- **Password/PIN reset via email** — no email backend exists today; signup captures emails now
  so this is unblockable later.
- **Request-a-wordset / family-triggered generation** — generation stays admin-reviewed;
  self-serve generation is a separate project with real cost and quality implications.
- **Multi-child family profiles** — see §5.8.
- **Email verification** — signups are unverified leads; verification ships with the paywall.
- **Assignment queue with auto-advance** — default-on self-assignment (§5.9) solves the
  busy-parent problem with less machinery; revisit if parents ask for planned sequences.
- **Adaptive re-calibration from SRS data** — the band set at signup is static (parent-editable);
  auto-adjusting `lexile_min/max` from demonstrated performance is a clean later addition once
  trial data shows how the band is used.

---

# Part 2 — Technical Implementation Plan

## Product decisions (as settled — see Part 1 for rationale)

- No parent role; one account = one child, `role=STUDENT`, used for daily practice. A
  **PIN-gated "Learning Management" area** lives inside the student portal: progress (with
  praise prompts), settings, credentials, the autonomy toggle, and unassign. **The PIN is
  required on every entry into the area** — leaving the area locks it, with a 15-minute
  idle-timeout backstop; there is no session-length "remembered" state.
- Self-serve trial signup (public, email required, **one password only** — no management
  credential at signup). The Parent PIN (6 digits) is created on first entry to the management
  area, for trial and school accounts alike (one unified setup path).
- **Calibration at signup**: optional Lexile number or free-text reading description →
  LLM-estimated level (grade-table fallback) → band `L−200 / L+300` on the account's existing
  `lexile_min`/`lexile_max` fields; parent-visible, editable in settings; skip/failure →
  default 0–2000. The estimator call has a short timeout and never blocks signup.
- **Self-assignment on by default** (`self_assign_enabled`, default True for all accounts).
  While on, the student portal has a kid-facing "Choose Word Sets" page where the child
  self-assigns without the PIN, subject to the guardrails. The parent can toggle it off
  (PIN-gated) and can unassign any self-assigned set (PIN-gated, always). Kid assigns charge
  the same quota. Settings/credentials/unassign stay behind the PIN regardless of the toggle.
- **Guardrails at assign time** (family assigns): pacing gate — block when ≥100 unlearned
  words (*any* in-progress words below mastery L4, family or school) or ≥50 backlogged review
  words; difficulty gate — kid assigns blocked when the set's `target_lexile` is outside the
  account band (parent assigns: warning only). Teacher assigns exempt from both.
- Trial quota: 2,000 words, lifetime, charged as `word_set.words.count()` at self-assign time,
  once per unique (user, word_set), no refund on drop. Tunable setting.
- Catalog = `is_public=True` word sets with ≥1 pack that has a selected graphic novel or
  infographic.
- School link: unique `student_code`; teacher claims existing accounts by code. While linked to
  ≥1 teacher, quota is not enforced and teacher assignments never consume quota. Unlink restores
  the quota with lifetime consumption intact; already-assigned sets keep working. **Ownership
  rule:** a teacher assigning a set the family already self-assigned flips `assigned_by` to
  the teacher — school takes ownership of the set; the quota charge stands (lifetime).
- Management area contents: catalog/assign + autonomy toggle + progress (celebrate card,
  fragile words) + settings (email, native language, daily question limit, Lexile band,
  change login password, change Parent PIN, view student code).

## Backend

### 1. Model changes — `backend/users/models.py`, `backend/vocabulary/models.py` + one migration

- `CustomUser.management_pin` — `CharField(max_length=128, null=True, blank=True)`, stores a
  Django hash (`make_password`/`check_password`) of a 6-digit PIN. NULL = management area not
  yet activated — the state of every new account (trial or school-created) until first-entry
  setup.
- `CustomUser.self_assign_enabled` — `BooleanField(default=True)`. Autonomy mode (§5.9): while
  True, the student may call the catalog/assign endpoints without management verification.
  Settable only through the PIN-verified settings endpoint.
- `CustomUser.student_code` — `CharField(max_length=12, unique=True)`, auto-generated in
  `save()` when empty: 8 chars from an unambiguous alphabet (no 0/O/1/I/L), via
  `secrets.choice`, retry on collision. Clean-slate deployment: the migration runs on an
  empty users table, so no backfill is needed — new rows get codes from `save()`.
- `lexile_min`/`lexile_max` **already exist** on `CustomUser` — no schema change; calibration
  (§5.10) just writes them at signup.
- New model `SelfAssignQuotaCharge` in `vocabulary/models.py`: `user` FK
  (related_name `quota_charges`), `word_set` FK, `words_charged` int, `charged_at` auto_now_add;
  `unique_together('user','word_set')`. Lifetime consumption = `Sum(words_charged)`.
- New settings constants in `backend/config/settings.py`:
  `FAMILY_SELF_ASSIGN_WORD_QUOTA = 2000`,
  `LEXILE_BAND_MIN_OFFSET = 200`, `LEXILE_BAND_MAX_OFFSET = 300`,
  `SELF_ASSIGN_MAX_UNLEARNED_WORDS = 100`, `SELF_ASSIGN_MAX_BACKLOGGED_WORDS = 50`,
  `SELF_ASSIGN_UNLEARNED_LEVEL_THRESHOLD = 4` (mastery levels below this count as unlearned).

### 2. Signup + calibration — `views/user_views.py`, new `services/lexile_estimation_service.py`

- `POST /api/signup/` — `AllowAny`, throttled (`SignupRateThrottle(AnonRateThrottle)`, 10/hour).
  Body: `username, email, password, native_language` (required) + `lexile_level` (int,
  optional) + `reading_description` (text, optional). Validates: username unique, email
  required/format, `validate_password(password)`, native_language in `SUPPORTED_LANGUAGES`,
  `lexile_level` in 0–3000 if present. Creates `role=STUDENT` user with `management_pin=NULL`
  and `self_assign_enabled=True`, logs them in, returns `UserSerializer` plus a
  `calibration` block: `{band: [min, max], source: 'provided'|'estimated'|'default',
  estimate?: int}`. The signup serializer lives in `vocabulary/serializers.py` next to
  `StudentCreateUpdateSerializer`.
- Calibration logic: explicit `lexile_level` wins; else if `reading_description` is present,
  call `lexile_estimation_service.estimate_lexile(description) -> int | None`; else default.
  Apply band as `lexile_min = max(0, L − settings.LEXILE_BAND_MIN_OFFSET)`,
  `lexile_max = L + settings.LEXILE_BAND_MAX_OFFSET`.
- `services/lexile_estimation_service.py`: one LLM call through the existing per-step config
  infra — new step key **`lexile_estimator`** (seed a default `LLMStepConfig` row in each
  config set; see deploy checklist). Prompt takes the parent description + the grade table as
  reference and returns `{"lexile": int, "rationale": str}` (remember:
  `call_gemini`/`call_anthropic` return parsed JSON dicts — Hard Rules). Fallback chain:
  unparseable/out-of-range result → static grade→Lexile table (extract a grade mention from
  the text; table of standard Lexile Framework grade midpoints, ~G2≈450 … G8≈1050, tunable) →
  `None` (defaults apply). **The estimator runs with a short timeout and never fails or
  delays signup materially** — on any error/slowness the account is created with the default
  band. An LLM outage must not block account creation.
- The estimate is surfaced to the parent in the post-signup flow (frontend §7) and the band is
  editable in mgmt settings (§4).

### 3. Management-area gate — `backend/vocabulary/permissions.py` + new `views/management_views.py`

- New permission `IsStudentManagementVerified`: STUDENT role **and** a **fresh**
  `request.session['mgmt_verified_at']` timestamp (within a 15-minute sliding window —
  the idle-timeout backstop).
- **Autonomy exception:** the catalog (`GET student/mgmt/catalog/`) and assign
  (`POST student/mgmt/assign/`) endpoints additionally admit requests where
  `request.user.self_assign_enabled` is True (no verification needed) — this is what the
  kid-facing catalog page calls. All other mgmt endpoints (status excepted) always require
  verification — including unassign and settings, even for autonomy-enabled students.
- Endpoints (all under `path('student/mgmt/...')`, all STUDENT-role):
  - `GET student/mgmt/status/` (IsStudent only) → `{has_management_pin, verified,
    student_code, teacher_linked, self_assign_enabled, quota_used, quota_limit}`
    (`verified` reflects the fresh timestamp check above).
  - `POST student/mgmt/setup/` (IsStudent; 400 if `management_pin` already set) → **the
    universal activation path** for all accounts (trial and school-created alike): validates
    the PIN is exactly 6 digits, stores its hash, marks the session verified.
  - `POST student/mgmt/unlock/` (IsStudent) → `check_password` the submitted PIN against
    `management_pin`; on success stamps `request.session['mgmt_verified_at']`. Throttle 10/min
    per user (`UserRateThrottle` scoped) — a 6-digit PIN at 10 attempts/minute is a ~2-month
    brute-force job against one account.
  - `POST student/mgmt/lock/` → clears the timestamp. **The frontend gate calls this whenever
    the user leaves the management area**, so every entry re-prompts for the PIN; the
    15-minute freshness check covers abandonment without an explicit exit (tab closed,
    browser sleep).
- UX note: the PIN pad should support submit-on-complete (auto-submit when the 6th digit is
  entered) — per-entry unlock must cost the parent ~2 seconds, since they re-enter it on
  every visit.
- CSRF note: the app authenticates via `CsrfExemptSessionAuthentication`, so session POSTs are
  protected only by `SameSite=Lax` cookies — the new endpoints inherit this posture, matching
  the rest of the app (signup is `AllowAny`, so it is moot there).

### 4. Catalog + self-assign + guardrails — `views/management_views.py`, `services/assignment_service.py`

- `GET student/mgmt/catalog/` — queryset: `WordSet.objects.filter(is_public=True,
  generation_status='GENERATED')` restricted to sets where ≥1 pack has an `is_selected` GN or
  infographic. **One annotated queryset** (`Count('words')`; two `Exists` subqueries for
  selected GN/infographic; `Exists` for this user's assignment) **with server-side
  pagination** (`PageNumberPagination`, 20/page — the family catalog must not ship the whole
  table like the teacher list does). Extract the pack/content check from
  `teacher_views._available_content_types_for_word_set` into a shared helper and reuse it in
  both places. Query params: `q` (icontains on `title`, `unit_or_chapter`,
  `input_source_title`), `curriculum`, `level`. Response per set: id, title, unit_or_chapter,
  curriculum/level names, `target_lexile`, `word_count`, `available_content_types`,
  `already_assigned`, **`in_lexile_range`** (`lexile_min ≤ target_lexile ≤ lexile_max` for
  this user), plus `quota_used`/`quota_limit`/`teacher_linked` and **pacing state**
  (`unlearned_count`, `backlog_count`, `pacing_blocked`) in the envelope. (Accessible to
  verified parents and autonomy-enabled students; the kid page uses `in_lexile_range` to
  disable cards and ignores quota fields.)
- `POST student/mgmt/assign/` `{word_set_id, content_type?}` — caller is either
  management-verified or autonomy-enabled. The whole operation runs in **one transaction
  holding `select_for_update` on the user row** (same locking pattern as
  `PracticeService.process_answer`) — this closes the concurrent-assign quota race (two
  parallel assigns of different sets must not both pass the check). Validation order:
  1. Set passes the catalog gate (else 404); not already assigned (400).
  2. **Pacing gate** (all family assigns): unlearned count — **all** of the user's
     in-progress words (family or school sets) with progress level_id <
     `SELF_ASSIGN_UNLEARNED_LEVEL_THRESHOLD`, a plain filter on `UserWordProgress(user,
     level)`, no set joins — ≥ `SELF_ASSIGN_MAX_UNLEARNED_WORDS`, **or** backlog count (READY
     words with `next_review_at` ≤ today) ≥ `SELF_ASSIGN_MAX_BACKLOGGED_WORDS` → 403
     `{detail, unlearned_count, backlog_count, limits}`.
  3. **Difficulty gate** (non-verified/kid callers only): `word_set.target_lexile` outside
     `[user.lexile_min, user.lexile_max]` → 403 `{detail, target_lexile, band}`. Verified
     parents skip this check (the UI shows a warning badge instead).
  4. **Quota** unless `request.user.teachers.exists()`:
     `quota_used + word_set.words.count() > settings.FAMILY_SELF_ASSIGN_WORD_QUOTA` → 403
     `{detail, quota_used, quota_limit}` (kid page renders as "ask a parent").
  Content type: accept requested type if available, else default GN (serving already falls
  back across types). On success: create `StudentWordSetAssignment(
  assigned_by=request.user)` and `SelfAssignQuotaCharge` (get_or_create — re-assigning a
  dropped set never double-charges), then init progress rows.
- Refactor `AssignmentService`: extract the per-student body of `assign_word_set` (assignment
  get_or_create + completed-pack check + progress bulk_create) into
  `_assign_to_single_student(word_set, student, assigned_by, content_type)`; add
  `self_assign_word_set(user, word_set, content_type)` used by the endpoint. **Ownership rule
  (E2):** when `assign_word_set` finds an existing assignment row whose `assigned_by` is the
  student themself (a family self-assignment), it flips `assigned_by` to the teacher — school
  takes ownership; the quota charge stands (lifetime). Teacher path is otherwise unchanged
  (teacher assigns never hit the pacing/difficulty/quota gates).
- `GET student/mgmt/assignments/` — the user's assignments annotated `source: 'self'|'school'`
  (`assigned_by == user` → self) with per-set pack progress (reuse the serialization shape of
  `StudentAssignedSetsView`).
- `POST student/mgmt/unassign/` `{word_set_id}` — deletes the assignment **only if
  self-assigned** (403 for school-assigned rows). Management-verified only (kids cannot
  unassign, even in autonomy mode — §5.9). Leaves `UserWordProgress` rows alone (READY words
  stay in SRS; documented).
- `GET student/mgmt/progress/` — aggregates the data for the **celebrate card** (§5.12):
  current streak + recent milestone, words that reached mastery in the last 7 days (count +
  up to 5 examples), and **fragile words** (words whose recent answers were classified
  fragile/missed by the response-quality logic — reuse the learning-patterns data; up to 6,
  with kid-friendly definitions). Plus the existing dashboard numbers.
- `PUT student/mgmt/settings/` — `email`, `native_language`, `daily_question_limit` (clamp
  1–200), **`self_assign_enabled` (bool)**, **`lexile_min`/`lexile_max`** (clamp 0–3000,
  min < max — the parent's calibration override). `POST student/mgmt/change-password/`
  `{new_password}` (`validate_password`; verified session is sufficient — the parent owns the
  account). `POST student/mgmt/change-pin/` `{current, new}` (verify current PIN; new PIN
  must be 6 digits).

### 5. Teacher claim-by-code + roster semantics — `teacher_views.py` + `CommandCenter.jsx`

- **E1 (prerequisite): `TeacherStudentViewSet.destroy` currently deletes the student user**
  (default `ModelViewSet` behavior — verified: no override exists). Change it to
  **unlink-only**: `teacher.students.remove(student)` + remove the student from the teacher's
  groups; return 204. Actual account deletion becomes an admin-only action (Django admin).
  Without this, a teacher removing a claimed family student would delete the family's entire
  account. (Cascade note: `assigned_by` is `on_delete=CASCADE`, so deleting a *teacher*
  account wipes their assignment rows; family self-assignments survive because
  `assigned_by` is the student.)
- `POST /api/teacher/students/claim/` `{student_code}` (IsTeacherOrAdmin,
  **throttled** with a `UserRateThrottle`, 10/min — discourages code-guessing) → look up
  STUDENT user by code (404 if none); `teacher.students.add(student)`; return `{id, username,
  first_name, already_linked}` for confirmation. Link is detected dynamically via
  `user.teachers.exists()`.
- `CommandCenter.jsx`: add the "Add existing student by code" form + confirmation; **change
  the roster-removal copy** from delete semantics to "Remove from roster" (E1).

### 6. UserSerializer

- Add `student_code`, `has_management_pin` (bool method field), `teacher_linked` (bool),
  `self_assign_enabled` (bool) so the frontend can render gate state, the student-code display,
  and the kid-facing catalog entry point.

## Frontend (`frontend/src/`)

### 7. Signup

- `pages/Signup.jsx` (public): username, email, password, confirm password, native language
  dropdown — then the **calibration block** (§5.10): "What is your child's current Lexile
  level?" numeric input (optional) with a "Not sure? Describe your child's reading" toggle
  revealing a free-text textarea (placeholder: "e.g. 3rd grade, reads Magic Tree House
  fluently"). Skippable ("Skip for now"). Client-side validation, server error display. On
  success the context stores the user; if `calibration.source === 'estimated'` show the
  estimate confirmation card ("We estimate about 500L — you can adjust this anytime in
  settings") before continuing. Redirect to the management area (the just-signed-up user is
  the parent; their first task is PIN setup → catalog), not the kid-facing dashboard. Route
  `/signup` in `App.jsx` (public, next to `/login`); "Create account" link on `Login.jsx`.

### 8. Management area shell + kid catalog

- `pages/student/management/ManagementGate.jsx` — wraps all `/student/mgmt/*` routes: fetches
  `status/`; renders the **PIN setup form** (`has_management_pin` false — the universal state of
  every new account; copy is parent-directed: "Parents: create a private PIN…"), the PIN unlock
  prompt (set but not verified), or `<Outlet/>` (verified). **Every entry into the area
  re-prompts**: on unmount/route-exit the gate calls `lock/`, so navigating away and back
  requires the PIN again (the 15-minute server-side freshness check covers tab-closes). The PIN
  input auto-submits on the 6th digit and shows a numeric keypad on mobile. Handles wrong-PIN
  errors and the lock button.
- Routes in `App.jsx` under the STUDENT `ProtectedRoute` + `StudentLayout`: `mgmt` →
  `ManagementGate` with children: `catalog`, `sets`, `progress`, `settings` (index → catalog).
  Entry points: link in the student nav (`StudentLayout`/navbar) and a card on
  `StudentDashboard`.
- `pages/student/management/ManagementCatalog.jsx` — search box + curriculum/level dropdowns
  (data from `/api/curricula/`, `/api/levels/`, already role-open), set cards (title, unit,
  curriculum/level, **target_lexile**, word count, available formats, "Assigned" badge,
  **out-of-band warning badge** when `in_lexile_range` is false — parent may still assign),
  quota banner (`X / 2000 words used`, hidden when `teacher_linked`), **pacing-state banner**
  when `pacing_blocked` (with counts), assign button → `assign/` with inline error rendering
  (pacing / quota 403s show their counts and guidance).
- `pages/student/management/ManagementSets.jsx` — two groups: "Chosen by you" (drop button →
  `unassign/`) and "From school" (read-only, teacher name). Shows pack completion per set.
- `pages/student/management/ManagementProgress.jsx` — leads with the **"Celebrate with your
  child" card** (§5.12): streak milestone, words mastered this week (with examples), and the
  **fragile-words "practice together" list** from `mgmt/progress/`; then the reused
  `/api/student/dashboard/` + `/api/student/assigned-sets/` numbers (due words, per-set
  progress).
- `pages/student/management/ManagementSettings.jsx` — email, native language, daily question
  limit forms; **Lexile band fields** (`lexile_min`/`lexile_max`, with the §5.10 explanation
  copy); change login password; change Parent PIN; **student code display** ("Give this code
  to your teacher: XXXX-XXXX").
- **Autonomy toggle** — a prominent, always-visible switch in the management area (rendered in
  the area header on every mgmt page, mirrored in `ManagementSettings`): label "Let my child
  choose their own word sets" (**on by default**), helper text "They see a
  Choose Word Sets page and can pick books themselves. Settings and passwords stay locked."
  Writes `self_assign_enabled` via `settings/`; an "Autonomy on" badge in the area header
  keeps the state visible on every mgmt page.
- **Kid-facing catalog** — `pages/student/StudentCatalog.jsx`: shown when
  `self_assign_enabled` (from `UserSerializer`/`status` — the default for new accounts); entry
  point "Choose Word Sets" card on `StudentDashboard` + nav link. Kid-appropriate styling (the
  student theme system, unlike the parent-toned mgmt pages), large set cards, assign button
  per card. **Out-of-band cards are disabled** with a friendly badge ("too hard for now" /
  "too easy — ask a parent if you want it"); pacing-403 renders as "You have N words waiting
  for review — practice those first!"; quota-403 renders as "You've used all your trial
  words — ask a parent." No quota banner, no settings links.
- Styling: plain CSS in the existing student layer system (`styles/students/…`, imported through
  the cascade per AGENTS.md); no CSS-in-JS.

## Tests (`backend/tests/`)

- Signup: happy path creates STUDENT with `management_pin=NULL`, `self_assign_enabled=True` +
  logs in; duplicate username 400; weak password 400; missing email 400.
- Calibration: explicit `lexile_level` sets band `L−200/L+300` (clamped at 0); description →
  mocked `estimate_lexile` result sets band (`source='estimated'`); LLM failure / timeout / no
  input → 0–2000 default and signup still succeeds; out-of-range `lexile_level` 400.
- `student_code` auto-generated on create and unique.
- Gate: mgmt endpoints 403 without unlock; setup validates 6-digit format (rejects letters,
  wrong length) and 400s when already set; PIN stored hashed; unlock wrong PIN 403; unlock
  throttled; verified state expires after the idle window (stale `mgmt_verified_at` → 403)
  and `lock/` clears it — every entry re-prompts. Setup path is identical for trial-signed-up
  and teacher-created accounts.
- Autonomy mode: accounts default on; catalog/assign succeed for a non-verified student
  with the toggle on, 403 with it off; kid assign charges quota (and 403s at the limit);
  toggling requires a verified session (403 otherwise); unassign still 403 for a non-verified
  student even with the toggle on.
- Guardrails: pacing gate — kid **and** parent assigns 403 when unlearned ≥ threshold or
  backlog ≥ threshold; **school-assigned words count toward the pacing totals**; teacher
  assigns unaffected; difficulty gate — kid assign 403 for out-of-band `target_lexile`,
  verified parent assign succeeds, in-band kid assign succeeds; catalog `in_lexile_range`
  annotation correct; `estimate_lexile` falls back to the grade table, then None.
- Catalog: only `is_public` + `GENERATED` + has-selected-content sets listed;
  `q`/curriculum/level filters; `already_assigned`; pagination works.
- Assign/quota: charge row created once per set (drop + re-assign doesn't double-charge); blocked
  at limit (403); teacher-linked user bypasses quota; unlink restores enforcement; content-type
  default/fallback. Assign holds a row lock (regression: sequential duplicate submits stay
  consistent).
- Ownership rule: teacher assign on an existing self-assignment flips `assigned_by` to the
  teacher, keeps the quota charge, updates `content_type`.
- Unassign: self-assigned deleted; school-assigned 403; progress rows untouched.
- Progress: `mgmt/progress/` returns mastered-this-week and fragile words correctly.
- Claim: teacher claims by code (M2M added, idempotent); invalid code 404; claiming a TEACHER
  404; claim endpoint throttled. Roster delete on a claimed account **unlinks only — the user
  row and their assignments/progress survive** (E1).
- Use existing factories; `GraphicNovelFactory(is_selected=True)` for published-state catalog
  tests; honor conftest cache-clear/filesystem fixtures.

## Deploy checklist

1. **Clean-slate reset** (per the deployment assumption): recreate the database; no backfills.
2. Run migrations; `collectstatic` if needed; restart `vocab` service (gthread workers already
   suit the new synchronous estimator call).
3. **Seed/configure the `lexile_estimator` step** in the active `LLMConfigSet` (step configs
   are set-scoped; without a row the estimator silently degrades to the grade-table fallback).
4. Build frontend, `scp` `dist/` to the server per the production runbook.
5. Smoke-test: signup (both calibration paths) → PIN setup → catalog assign → kid catalog →
   practice; teacher claim-by-code; roster removal unlinks (does not delete).

## Docs

- `AGENTS.md`: new account model paragraph (Parent PIN, student_code, default-on
  self-assignment, calibration + guardrails, quota, catalog gate, claim-by-code) + Hard Rules:
  self-assign charges quota via `SelfAssignQuotaCharge`, teacher-linked bypass; kid assigns
  are difficulty-gated by the account Lexile band; roster removal unlinks, never deletes.
- `docs/architecture-decisions.md`: full section (signup, gate/session model, autonomy mode,
  calibration + lexile_estimator step, pacing/difficulty guardrails, quota semantics,
  ownership-flip rule, link lifecycle, destroy-only-unlinks rationale).
- `docs/changelog_after_July_20.md`: feature entry.
