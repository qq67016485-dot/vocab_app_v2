# Book-Neutral Wordset Discovery: Product Design

> **Status:** draft v2 for review (2026-07-31). Not yet implemented. v2 incorporates the owner review discussion: the two-tier catalog model (platform packs vs. teacher sets), catalog sizing math, input-hygiene filters (proper nouns), the refined program-reader legal analysis, and the conservative launch-sequencing option. Sections 1–2 are the motivation and legal design principles; sections 3–8 are the architecture; sections 9–12 are cost, rejected alternatives, open decisions, and rollout.

## How to read this doc

- **Section 1** — what the system does today and why it is legally exposed.
- **Section 2** — the legal design principles every subsequent decision follows from.
- **Section 3** — target architecture: the generic word library, the **two-tier wordset model**, and catalog sizing math.
- **Section 4** — teacher-facing UX: the two search entry paths, input hygiene, and result presentation.
- **Section 5** — the book lookup service (grounded retrieval + JSON extraction).
- **Section 6** — matching lookup results against the word library (sense disambiguation).
- **Section 7** — anonymized metadata ("search documents") for curated wordsets.
- **Section 8** — the data-minimization plan for existing and future data.
- **Sections 9–12** — cost model, rejected alternatives (with reasons), open decisions, phased rollout.

**Disclaimer.** Section 2 and the legal reasoning throughout are engineering risk analysis, not legal advice. One review of this exact design by an IP attorney is a launch gate (section 12).

---

## 1. Background: the current system is book-coupled

Today the book is the *identity* of a wordset, and the association is stored in several places:

- `WordSet.title` **is** the book title (`backend/vocabulary/models.py:358` — help text: "The title of the book, article, or unit").
- `WordSet.source_text` stores the actual book passage used as LLM generation context (`models.py:361`).
- `WordSet.input_source_title` / `input_source_chapter` record the book (`models.py:370-371`) and are exposed in teacher-facing serializers (`backend/vocabulary/serializers.py:238,281`).
- `GenerationJob.input_source_title/chapter/input_source_text` duplicate the book identity on every job row (`models.py:873-875`).
- Every word is stamped `Word.source_context = "From {book}, {chapter}"` at generation time (`backend/vocabulary/services/generation/step_word_lookup.py:268-281`); the book title is also interpolated into generation prompts (`step_word_lookup.py:144`) and therefore lives in LLM logs.
- Teachers browse wordsets by these titles and assign them to students.

The product goal stated by the owner: pre-generate a large catalog, hide book identities from teachers, and let teachers find suitable wordsets by search — motivated by copyright/trademark exposure.

## 2. Legal design principles

Everything in this doc follows from five principles, established during design discussion:

1. **Content cleanliness is the primary defense.** Copyright protects expression (sentences, scenes, characters), not facts. Individual words, word lists, titles, and "which hard words appear in book X" are facts (*Feist*). The real infringement risk lives in generated artifacts that reproduce book text — not in any label. Therefore: no book passage text is stored or fed to generation in the target architecture, and all instructional content is generated for generic words with no book context.
2. **No derivation ledger.** The production database must be unable to answer "which book produced which content." No mapping tables, no book titles on wordset rows, no persistent query strings. Partial measures that merely *encode* the mapping (e.g., title embeddings) are rejected — see section 10.
3. **Trademarks exist only inside the teacher's own search box.** A teacher typing "Harry Potter" and seeing generic results is nominative, private use. Publicly labeling sets with marks, or merchandising them ("Popular: Harry Potter wordsets!"), is trademark/endorsement exposure. There is a **who-is-speaking gradient**: platform-created labels are the worst case; a platform *feature* built around marks is the middle; teacher-supplied labels on their own content are the mildest tier (user-generated nominative use — the Quizlet/TpT market norm — though the shield thins with scale and platform benefit; section 4.4). **Highest-sensitivity category: program readers whose publisher sells adjacent vocabulary products** (Learning A-Z sells Raz-Plus lesson materials and Vocabulary A-Z). There the injury is concrete market substitution — your feature substitutes for *their* vocabulary products, indexed by *their* catalog structure — which stacks claims (trademark, unfair competition, and a thin compilation argument if their curated word *selections* are reproduced wholesale at scale). The LLM-in-the-middle is legally invisible: liability attaches to what the service does for the teacher, not the implementation.
4. **Query-time factual lookup is clean.** Asking an LLM (with web grounding) "what vocabulary does an ESL reader at Lexile X need for book Y" retrieves *facts*; the answer (a word list) contains no protected expression. The association exists for the duration of one API call and is not persisted.
5. **Data minimization as hygiene.** Anything the product no longer needs (source passages, book titles on completed jobs, old LLM logs) is scrubbed on a defined lifecycle — decided *before* the data accumulates (section 8).

## 3. Target architecture

### 3.1 The generic word library (content substrate)

- Pre-generate word-level instructional content for **~8,000 English words × up to 3 Lexile tiers each** (tiers chosen per word — only levels appropriate to that word). Corpus linguistics supports the coverage claim: ~8,000 word families covers ~98% of general-text tokens; the residual is proper nouns and trademarked coinages, which we are legally better off not serving anyway.
- Content per word×tier: choice questions, sentence-write items, primer cards, translations — exactly the word-level steps the pipeline already has (QUESTION_GEN, SENTENCE_WRITE_GEN, PRIMER_GEN, TRANSLATION).
- This is `content_reuse.py` taken to its conclusion: word-level content is generated **once** and reused everywhere within the existing Lexile-window mechanism; the library makes reuse the default rather than the exception.

### 3.2 Two tiers of wordsets

The economics are driven by one fact: pack-level content (graphic novel / infographic) is expensive and per-word-combination, so it can only exist for word combinations the platform chose to invest in. Hence two tiers:

- **Tier 1 — Platform packs (the catalog).** Thousands of pre-generated, anonymized packs, each with its pack-level content already produced. Shared, browsable, searchable. Generation cost is amortized across every teacher who ever assigns the pack — this is what makes the economics work. Packs are **immutable**; an assignment is a *view* over a pack. A teacher may subset the words they practice — **subset the practice, not the pack**: questions serve only the selected words, while the infographic/GN is shown whole (two extra words on a poster is pedagogically harmless; regenerating or redacting images is economically absurd).
- **Tier 2 — Teacher sets (free-form but cheap).** A teacher who composes their own word list gets **word-level content only** — questions, primers, sentence-write — all reused from the library at zero marginal generation cost. **Private by default.** No infographic, no GN: an economic law of the system, not a legal restriction. The product presents platform packs as the premium tier rather than teacher sets as a crippled one.

### 3.3 Discovery = matching, never teacher-initiated generation

Teachers find sets through two entry paths that both terminate in library matching (sections 4–6):

1. **"Search by book, program, or topic"** — free text; routed to the book lookup service (section 5).
2. **"Paste the words you need to teach"** — min 5 words; intersected directly with the library and the pack catalog.

"Never initiate generation" means *never synchronously, never per-teacher* — not never at all. When no pack covers a query well: show best-coverage packs honestly ("covers 7 of your 9 words"), log the miss as **coverage-gap telemetry** (bare word lists only — never book titles), and let the back-office generation queue fill gaps on the platform's schedule; the new pack joins the shared catalog and the teacher is notified. The teacher never waits and never triggers a cost event; the catalog compounds.

Pack word selections come from generic sources first — curriculum word lists (NGSL, Fry, Dolch), textbook corpora, thematic curricula — plus some book-informed selections via the grounded lookup. **Source diversity is both good pedagogy and good legal posture**: a catalog organized around generic curricula that happens to cover popular books well is a very different artifact from a catalog indexed to one publisher's book list.

### 3.4 Catalog sizing: how many packs?

The answer depends on the coverage definition, and the three candidates give wildly different numbers:

- **Every word appears once** (trivial partition): 8,000 ÷ 6 = **~1,334 packs**. Cheap and useless for matching — a teacher's 9-word glossary scatters across ~9 packs.
- **Arbitrary combinations covered**: mathematically impossible. Guaranteeing every *pair* co-occurs needs C(8000,2)/C(6,2) ≈ **2.1M packs**; all 4-subsets need ~10^13. Do not chase this.
- **Real teacher queries covered decently** (the operating point): real queries share a Lexile band and usually a topic. Cluster the library by topic × level (~25 words/cluster → ~320 clusters) and generate overlapping packs *within* clusters, each word appearing in r = 2–4 packs:

| Pack size | Replication r | Total packs |
|---|---|---|
| 6 | 2 | ~2,700 |
| 6 | 3 | **~4,000 (working number)** |
| 6 | 4 | ~5,300 |
| 4 | 3 | ~6,000 |

Two multipliers make this work: **2-pack union answers** ("Pack A covers 5, Pack B adds 3" — set cover with two packs is far more forgiving than one pack doing the whole job) and the **word-level fallback** for the remainder.

**6 vs. 4 words per pack:** an infographic render costs essentially the same whether it carries 4 or 6 words — image, design call, and cloze step are per-pack fixed costs — so 4-word packs cost **+50% renders for the same replication** while buying finer match granularity (a 4-word pack needs only 4 query words to be a *perfect* match). Recommendation: **6 as the default**; the binding constraint is clustering quality, not pack size. Shrink pack size only in the highest-demand clusters if telemetry shows fragmentation. (The GN pipeline already handles ≤4-word packs with a 5-page script.)

**This number must be simulated before it is spent** (section 12, gate 1): take ~50 real book glossaries via the grounded lookup, build a candidate clustering, run the matcher, and inspect the coverage distribution (best pack / best 2-pack union / remainder). A few dollars of LLM calls sizes a 4,000-render investment. Post-launch, real teacher query word-lists drive periodic re-clustering and targeted new packs.

## 4. Teacher-facing UX

### 4.1 Entry points

Two explicit options on the search page (an auto-detecting single box was discussed and rejected for ambiguity — explicit modes are predictable):

- **Option A: "Have a book or topic in mind?"** — free-text box. Level/grade/Lexile tokens in the query ("level i", "grade 5", "Lexile 800") are extracted as structured filters on `target_lexile` by the LLM itself, from general knowledge — **no program-specific level lookup table**: a RAZ-level→Lexile table in the codebase is precisely the artifact that evidences systematic reliance on one publisher's catalog (section 2, principle 3).
- **Option B: "Paste your target words"** — textarea, minimum 5 words. Deterministic: exact coverage, no LLM involved. This is also **the legally cleanest path in the product**, by three layers: (1) the teacher's act — transcribing words from materials they are typically licensed to use in their own classroom — is ordinary teaching practice; (2) a generic "paste words, get matches" tool has overwhelming non-infringing uses (*Sony/Betamax*; Quizlet has operated on this basis for years); (3) the content returned is our own original, generic material. **One rule: never market the synergy** ("works with Reading A-Z glossaries!") — the feature stays generic; teachers discover what it works with on their own.

**Input hygiene — proper-noun filter (both options, and assembly generally).** Reject or flag capitalized proper nouns and coined words ("Wilbur", "Zuckerman", "Quidditch") with a friendly message ("names and made-up words can't be practiced"). Without this, a pasted list containing a book's characters would lead the GN generator to write a story *featuring that character* — reproducing protected expression — and names make terrible vocabulary-practice words anyway. This is the same scrubbing principle as the search-document validator (section 7), applied at the input boundary.

### 4.2 Result presentation

Result cards show **only** book-neutral information: generic title, Lexile band, theme tags, word count, and the word list itself (expandable). Recognition substitutes for recall: the teacher spots "barnyard friendship, spider, farm animals, grades 3–4" and knows it's the set they wanted.

- Coverage is stated honestly per card: "covers 7 of your 9 words"; 2-pack unions are presented as combined answers (section 3.4).
- The teacher's own query may be echoed ("Results for 'charlotte's web'") — nominative, private. It is **never** attached to the wordset.
- Multi-part sets (a novel split into chapter sets) are **grouped by series** in results, not scattered as weak individual matches.
- No merchandising of marks anywhere: no "popular books" tiles, no autocomplete on book titles.

### 4.3 Fallback behavior

- Lookup returns `found=false` or low confidence → the UI says so honestly ("We couldn't find reliable vocabulary data for this title") and switches to Option B with guidance ("paste the words from the book's lesson page — most programs print them").
- Words that fail to match the library are reported as a short "not covered" list, so the teacher sees exactly what was dropped.
- **Conservative launch sequencing** (decision #5): the product can ship with only Option B + curated browsing, adding the grounded book lookup after the attorney review. The architecture supports that order with no rework.

### 4.4 Teacher-named sets

Tier-2 teacher sets are private by default, so a teacher naming their set "The Spelling Bee — RAZ Level I" stays inside their own classroom organization — lawful nominative use of a non-copyrightable title by a licensed user, and the platform never publishes marks. A public gallery of teacher-labeled sets would be *lawful but off-message* (the Quizlet model: user-generated nominative use, defensible — but it recreates browse-by-book, contradicts the neutrality posture, and the UGC shield thins as the platform scales and benefits). If sharing is ever added, it is link-based and **unindexed** — no gallery, no title search, no merchandising.

## 5. The book lookup service

New backend service (suggested: `vocabulary/services/book_lookup/`), exposed as an async teacher endpoint following the edit-image pattern (POST → 202 + poll status; 4–7s uncached latency is normal).

### 5.1 Pipeline

```
teacher query
  → normalize (lowercase; LLM extracts level/grade/Lexile tokens → lexile band)
  → cache check (section 5.4)
  → CALL 1: grounded retrieval
  → CALL 2: JSON extraction + normalization
  → library matching (section 6)
  → assemble wordset (generic identity only)
  → respond
```

### 5.2 Call 1 — grounded retrieval

- Native `google-genai` client with the **Google Search grounding tool**. This does **not** work through an OpenAI-compatible proxy (same constraint as audiobook TTS) — add a separate `GEMINI_SEARCH_API_KEY` / `GEMINI_SEARCH_BASE_URL` config mirroring the existing `GEMINI_TTS_*` native-client pattern.
- Prompt shape: "List the vocabulary words an ESL reader at Lexile {band} needs for the book '{title}' ({program/level if given}). If the book has an official vocabulary / 'Words to Know' list, use exactly those words. For each word give its part of speech and a short sense definition **paraphrased in your own words — never quote the book's glossary verbatim**. Words and senses only; no plot summaries, no sentences from the book."
- **Glosses are matching context, never content** (section 6). The book's glossary is the publisher's instructional material; a paraphrased sense used transiently for disambiguation is the safe posture. Publisher glossary text is never stored or displayed.
- **Google's grounding attribution requirement**: grounded responses carry `groundingMetadata` including a search entry point, and Google's terms require rendering search suggestions in the UI. This is a product-visible obligation — check the current clause before launch.
- Two registered LLM-config step keys (per the existing `LLMStepConfig` pattern): `book_lookup_retrieve` (native site) and `book_lookup_extract` (proxy site).

### 5.3 Call 2 — JSON extraction

Ungrounded, forced-JSON through the existing `call_gemini` (cheap model — extraction, not reasoning; disable thinking). Input is call 1's raw prose (citation markers and all). Call 2 does three jobs:

1. **Extract** words/POS/glosses out of whatever format call 1 produced, stripping `[1]`-style citation artifacts.
2. **Normalize** — lemmatize ("soaked" → "soak"), lowercase, standardize POS to our enum.
3. **Judge** — whether call 1 actually found the book or hedged/confabulated (prose makes this obvious to an LLM reader).

Contract:

```json
{
  "found": true,
  "confidence": "high | medium | low",
  "has_official_word_list": true,
  "generic_title": "Classroom Celebration Project",
  "theme_tags": ["school", "projects", "counting", "celebration"],
  "words": [
    {"word": "brainstorm", "lemma": "brainstorm", "pos": "verb",
     "gloss": "to share ideas, often on how to solve a problem"}
  ]
}
```

A one-call grounded-JSON variant was rejected: grounding citation markers pollute fields intermittently, and `found=false` judgment is unreliable when the model must simultaneously retrieve and format (section 10).

**Official-list caution.** When call 1 returns a publisher's *official* word list, do not mirror that exact selection at scale — merge/diversify with level-appropriate alternatives where pedagogically reasonable. Serving one publisher's curated selections verbatim across their whole catalog is the worst version of the feature (section 2, principle 3).

### 5.4 Cache (and its legal posture)

- Key: normalized query + lexile band. Value: the call-2 JSON. **TTL of days, not permanent** — a permanent cache *is* a stored book→words mapping; a TTL cache is a performance optimization.
- Write-through: cache `found=false` results too, with a shorter TTL, so unfindable books don't get re-grounded on every retry.
- The assembled wordset persists, but carries only its generic identity — **the query string is never stored on the wordset row.**

### 5.5 Fallback chain

```
grounded lookup
  → found=false / low confidence
  → ungrounded LLM recall (self-reported confidence; famous books only)
  → still low
  → UI paste-words fallback (section 4.3)
```

Every book on earth is covered by some rung, including books published yesterday (grounding retrieves; recall is not required). Note the final rung is not a consolation prize — paste-words is the legally cleanest path in the product (section 4.1).

### 5.6 Verified behavior to date

- AI Studio manual tests (2 books, including the mid-tail Reading A-Z Level P title *The 100th Day Project*): grounding returned the book's **actual "Words to Know" list with glossary senses** — ground-truth-grade fidelity.
- An ungrounded recall test on a long-tail title (*Mike's Good Bad Day*, RAZ Level I) produced plausible-but-unverifiable confabulation (zero confirmed hits against web-verifiable words) — the result that motivated grounding + the paste fallback.

## 6. Matching against the word library (sense disambiguation)

Input: call 2's `words[]` (already proper-noun-screened, section 4.1). Per word, in order:

1. **Normalize** — lowercase; use the LLM-supplied lemma.
2. **Exact lookup** against the library. Not found → log as a **coverage-gap** signal (telemetry for library expansion), report to the teacher as "not covered"; v2 may queue on-demand generation.
3. **One stored definition** → attach. No further work.
4. **Multiple definitions** → filter by `pos` first (the gloss makes POS obvious; resolves many cases alone).
5. **Still ambiguous** → **one Qwen3 embedding call on the gloss** (never the bare word — a bare "bat" embeds to an averaged sense and matching is coin-flip), cosine against the candidate definitions' embeddings, **argmax**.
   - Library definition embeddings are **precomputed once at library build time** (~15–20k vectors); query time is one small embedding call + numpy argmax. Reuses `embedding_service.py`.
   - **Threshold semantics differ from dedup.** `find_duplicate_definition` uses cosine ≥ 0.90 as a precision bar for "same meaning, don't store twice." Sense matching is a best-of-N *choice*: argmax wins even at 0.65. Set a low **floor** (starting point ~0.55–0.65, calibrated — section 12): below floor means "the book's sense isn't in our library" (e.g., "fall" as autumn when we only store "fall" as drop) → default to the primary definition, flag, log.

Alternative rejected: sending candidate DB definitions into the LLM extraction call for direct selection — couples the retrieval call to the DB schema, adds tokens/latency, and gains little over deterministic embeddings (section 10).

## 7. Anonymized metadata ("search documents") for curated sets

Curated/admin-assembled sets (for browsing) get a search document, generated as one small LLM step:

- Input: the word list (+ optionally the source context, which the LLM may see at generation time — it already does today at `step_word_lookup.py:144`; only the **stored output** must be book-neutral).
- Output: `display_title` (3–6 words), 5–8 `theme_tags`, 1–2 sentence `description`.
- **Validation before persist** (the enforcement layer): normalized output must contain no token from the source title, no author name, no coined proper nouns from the word list (fantasy coinages — "Quidditch" — are both identifying and trademark-sensitive). Failure → regenerate once → fail the step.
- Assemble search text (`title + description + tags + neutral words`), embed with Qwen3, store the vector on the set. Re-run on word-list changes. Backfill existing sets with a management command (same pattern as `backfill_jpeg_images`).

Scale note: thousands of sets × one vector = brute-force cosine in numpy at millisecond cost. No vector DB.

## 8. Data-minimization plan

Scrub values, not schema (dropping columns is a migration headache; ensuring they never hold book-identifying data achieves the same).

| Data | Action |
|---|---|
| `Word.source_context` ("From {book}, {chapter}") | **Stop writing it** (nothing reads it except the Django admin list view, `admin.py:26`); wipe existing values |
| `WordSet.source_text` (actual book passages) | Null on successful pipeline completion — after the search document is generated and validated. **Not** earlier: resume/restart re-reads it |
| `WordSet.input_source_title/chapter`, `GenerationJob.input_source_*` | Null on successful completion, same timing |
| Permanently failed jobs | Sweeper command: scrub `input_source_*` on jobs failed > X days |
| Teacher-facing serializers | Remove `input_source_title/chapter` from payloads (`serializers.py:238,281`) |
| LLM logs (`temp/llm_logs/`) | Retention policy: rotate/delete after N days — prompts contain source titles/passages |
| Lookup cache | TTL per section 5.4; never persist query strings on wordsets |
| DB backups | Retention applies to dumps too, or the scrub is cosmetic |

One explicit allowance: teacher query **word lists** (bare words, no titles) may be retained indefinitely as catalog-clustering telemetry (section 3.4) — facts only, no book identity.

**Decision deferred to owner (section 11):** whether any offline, outside-the-product record of book→set mapping is kept for catalog curation. If kept: outside the production DB entirely.

## 9. Cost model

Per lookup, at the owner's stated rates ($1.5/M input, $7.5/M output tokens):

| Component | Tokens | Cost |
|---|---|---|
| Call 1 input (query + grounding-injected context) | ~650–1,650 | $0.001–0.0025 |
| Call 1 output (prose word list) | ~300 | $0.0023 |
| Call 2 input (call-1 output + prompt + schema) | ~600 | $0.0009 |
| Call 2 output (JSON, ~10 words) | ~200 | $0.0015 |
| **Token total** | | **~$0.005–0.007** |
| **Google grounding fee** (if billed natively; ~$35/1k after free daily allowance) | | **~$0.035** |

The grounding fee, not tokens, is the dominant per-lookup line item — verify how the proxy/provider bills grounding before assuming token-only rates. With the TTL cache, cost is per *unique* query, not per search. Example: 5,000 teacher searches/month hitting 500 unique books ≈ **$21/month** ($17.50 grounding + $3.50 tokens).

The dominant *one-time* cost is the catalog itself: ~4,000 packs × per-pack generation cost (design + cloze calls + one image render each). The simulation gate (section 12) exists precisely to size this before committing.

## 10. Rejected alternatives (and why)

| Alternative | Why rejected |
|---|---|
| Public "derived from X" labels on wordsets | Invites rights-holder attention; becomes evidence of access/intent if any content overlap is found; trademark exposure on famous marks |
| Book→set mapping table in the DB | A derivation ledger: evidence of systematic, intentional derivation (willfulness multiplier); discoverable |
| **Storing title embeddings instead of titles** | Security-through-obscurity only. Title space is small and fully public (RAZ publishes its complete book list); embedding all known titles and cosine-comparing reconstructs the mapping in an afternoon. Changes no legal fundamentals — exposure lives in public behavior and content, not storage format |
| Pure LLM recall for book vocab | Fails the long tail: the *Mike's Good Bad Day* test produced confabulation with zero verified hits. Fine for famous books; unacceptable as the only path |
| One-call grounded JSON | Grounding citation markers (`[1]`) pollute fields intermittently; `found=false` judgment unreliable when retrieval and formatting are fused |
| LLM selects among candidate definitions directly | Couples retrieval to DB schema; more tokens/latency; no gain over deterministic embedding argmax |
| Search-only discovery (no browsing) | Teachers can't search for what they don't know exists; browsing by generic facets (grade/theme/Lexile) is label-free |
| Public gallery of teacher-labeled sets (Quizlet model) | Lawful (user-generated nominative use) but off-message: recreates browse-by-book, contradicts the neutrality posture, UGC shield thins with scale and platform benefit (section 4.4) |
| Teacher sets with on-demand pack-level content | Economically impossible: GN/infographic cost can't be spent on arbitrary per-teacher word combinations (section 3.2) |
| Uniform combinatorial pack coverage | ~2.1M packs just to cover all word pairs (section 3.4) |
| Program-level→Lexile lookup tables | Evidences systematic reliance on one publisher's catalog; generic LLM level extraction is simpler and cleaner (section 4.1) |

## 11. Open decisions (for owner review)

1. **Two explicit search modes** (this doc's choice) vs single auto-detecting box.
2. **Offline book→set record**: keep one outside the product for curation, or keep nothing.
3. ~~Teacher-created wordsets~~ → **Resolved in direction** by the two-tier model: teacher sets are private-by-default, word-level-only (section 3.2/4.4). Remaining sub-question: link-based unindexed sharing — add later or never?
4. **Grounding billing path**: native Google (per-query fee, attribution obligation) vs proxy passthrough pricing.
5. **Launch shape**: full design at once, or conservative sequencing — Tier-1 catalog + paste-words + curated browsing first, grounded book lookup added after the attorney review (section 4.3). Both are supported with no rework.
6. **Program-reader stance** (RAZ etc.): given the market-substitution analysis (section 2, principle 3) — include, exclude, or de-emphasize program-name queries? For counsel.
7. **Lexile tier boundaries** for the 3 per-word tiers.
8. **Student-surface audit**: confirm no `source_context`/book remnants reach student payloads.

## 12. Phased rollout & validation gates

- **P0 — Legal hygiene** (independent of search): section 8 scrubbing + serializer cleanup. Ship first.
- **P1 — Catalog simulation** (cheap, decisive): ~50 real glossaries via grounded lookup → candidate clustering → coverage distribution → confirm/adjust the ~4,000-pack plan and 6-word default before any render spend.
- **P2 — Book lookup service**: calls 1+2, cache, step configs, async endpoint. Admin-only test harness page.
- **P3 — Library matching**: precompute definition embeddings; matching pipeline; coverage-gap telemetry.
- **P4 — Teacher UX**: search page (both modes), result cards with coverage display, paste-words flow, two-tier assignment (pack views + teacher sets).
- **P5 — Curated catalog generation**: search-document step + backfill command; cluster-driven pack generation via the existing queue.

**Validation gates before launch:**

1. **Catalog coverage simulation** (P1): median words covered by best pack and best 2-pack union across ~50 real glossaries meets target (suggested: ≥60% single-pack, ≥85% two-pack) — else revisit cluster count, r, or pack size.
2. Sense-disambiguation calibration: 50 genuinely ambiguous words from real grounded lookups; verify argmax picks the right sense; set the floor from data.
3. No-web-presence test: fake/obscure titles must return `found=false`, not confabulation. If grounding still hallucinates, call 2's judgment prompt needs strengthening.
4. Non-English/translated title test (ESL teachers search whatever the local school uses).
5. Proper-noun filter test: pasted lists containing character names / coinages are rejected cleanly, and the GN generator provably never receives them.
6. Grounding attribution rendering verified against Google's current terms.
7. **IP attorney review of this exact design** — one session, before the catalog scales.
