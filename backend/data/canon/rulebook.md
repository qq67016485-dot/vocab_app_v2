# Lexi Legends Runtime Canon Rulebook

Runtime use: authoring rules for standalone sheets loaded into script, image, and audio generation payloads
Current focus: visual sheet standards learned from the edited Leo and Amara sheets

## Core Principle

Each runtime sheet must work alone. Assume the model receives only the selected sheet, not the full bible, not the 9 years old/12 years old companion sheet, and not the other cast sheets.

Write every visual sheet as a production spec for an image model and a graphic novel script writer. The sheet should remove guesswork, prevent character drift, and still leave room for story creativity.

## Rule 1: Make Age Presentation Direction Absolute

Do not describe a character by comparing them to another Age Presentation version.

Use:
- "Age 12, about 150 cm."
- "Lean, narrow-to-average shoulders, long-limbed and quick."
- "Head-to-body ratio about 1:6.2."

Avoid:
- "Older than 9 years old."
- "Taller and more mature."
- "More refined than the younger version."

Rationale: runtime loading may send only one sheet. Relative language gives the model no reference point and increases drift.

## Rule 2: Include Exact Physical Anchors

Every cast visual sheet needs concrete physical details:
- apparent age
- approximate height
- build
- skin tone
- face shape
- eye shape and color when useful
- eyebrows or other expression anchors
- nose, chin, cheeks, or jawline when useful
- hair color, texture, length, volume, and silhouette boundary
- posture and body language
- proportion guidance when drift risk is high

Rationale: image models invent missing anatomy. The more specific the body, face, and hair constraints are, the less likely the character changes between pages.

## Rule 3: Bound Hair And Silhouette

Hair should include a shape limit, not just a style label.

Use:
- "short curly hair with a loose asymmetrical top"
- "stays within about 1.5 cm of skull"
- "no wider than temples"
- "simple silhouette for small panels"

Rationale: hair is one of the fastest places for drift. A model may turn "curly" into a large silhouette, long hair, or a different age read unless the boundaries are stated.

## Rule 4: Specify Proportions When Age Read Matters

For recurring child characters, include enough proportion detail to keep them in the intended age range.

Useful details:
- head-to-body ratio
- arm length reference
- face length as a portion of head height
- jawline softness or angle
- shoulder width
- limb length impression

Rationale: "age 12" alone is not enough. Models may make the character too young, too old, or adult-proportioned. Proportion rules protect the IP age band.

## Rule 5: Make Outfit Construction Precise

Outfit sections should specify garment type, color, fit, length, texture, visible construction, and permitted accent details.

Use:
- "hem falls at upper thigh"
- "sleeves pushed to mid-forearm"
- "large front pocket"
- "hood bunched behind neck"
- "one cyan zipper pull, drawstring knot, or small tab allowed"

Rationale: signature clothing is a core continuity anchor. If garment length, fit, and details are vague, the model may redesign the character from page to page.

## Rule 6: Keep Signature Colors Dominant

Every sheet should identify the two or three highest-priority color reads and repeat which colors must dominate.

Example:
- "Crimson and cyan must be the two strongest color reads in any panel."

Rationale: models often add palette noise in genre settings. Dominant color instructions preserve character recognition in any Story Realm.

## Rule 7: Describe Prop Handling Only When It Affects Identity

The primary writing tool must be described clearly, but do not over-specify unnecessary handling if it adds noise.

Required:
- size
- color/material
- glow behavior
- no-logo rule
- what the tool emits
- tool as writing instrument, not weapon

Optional:
- grip or carry behavior, only if it protects the character read.

Rationale: the tool is a signature anchor. But excess handling direction can distract from cleaner visual instructions.

## Rule 8: Add Under-Pressure Behavior

Each recurring character should include a short "under pressure" behavior note, plus any bravery, flaw, or emotional-range notes that protect the character from flattening.

Use:
- what the character does when stressed
- how they recover from being wrong
- what they never do emotionally
- how bravery appears for this character
- a concise flaw that can create story tension without breaking the character
- 2-3 emotion-specific physical tells if they help the script/image model

Rationale: script generation needs visual/personality context, not only costume data. Under-pressure behavior gives the writer a reliable way to create conflict without breaking character.

## Rule 9: Keep Story Role Compact

Story role and personality should guide the writer, but visual sheets should not include solo-strength lists or pair dynamics.

Use:
- a compact role paragraph
- a compact personality paragraph
- what comedy or conflict should come from
- what the character must never become
- under-pressure behavior
- bravery, flaw, and emotional-range notes when useful

Avoid:
- pair-by-pair dynamics
- long scenario menus
- extensive story engine recommendations

Rationale: the LLM can generate stories from character personality. Too much strategic story guidance bloats the payload and can make stories formulaic.

## Rule 10: Include Catch Phrases For Voice, Not Mandatory Lines

Catch phrases should be examples of rhythm and personality.

Label them clearly:
- "Sample phrases (inspiration, not mandatory)"

Rationale: short phrases help the model hear the character's voice. Marking them as optional prevents repetitive dialogue.

## Rule 11: Define Panel Priority

Every visual sheet should include a priority list for crowded panels.

Example:
1. signature outfit silhouette
2. signature tool or Ink effect
3. face
4. body language
5. readable target word

Rationale: image generation often loses details in crowded scenes. A priority list tells the model what to preserve when composition gets complex.

Also include scale behavior when the character has a strong silhouette.

Use:
- close-up read
- mid-shot read
- wide/crowd read

Example:
- "Close-up shows Ink detail and expression. Mid-shot shows cloak shape, tool glow, hair. Wide/crowd reads as purple trapezoid + gold dot."

Rationale: image prompts often ask for different camera distances. Scale behavior tells the model what identity markers survive at each distance.

## Rule 12: Make Ink VFX Physical

Ink VFX should specify:
- color
- glow behavior
- shape language
- surface illumination
- lettering style
- failure state
- correct-use state

Rationale: Ink is both magic system and visual brand. It must look consistent and stay readable.

## Rule 13: Limit Realm Adaptation

Allow temporary genre accessories, but protect the core silhouette and tool.

Use:
- "Temporary accessories are fine as long as the signature outfit remains visible and the writing tool is not replaced."
- "The signature tool is for word-magic only. Characters may freely interact with ordinary world objects when the story requires it."

Rationale: Story Realms need genre flexibility, but recurring heroes must remain recognizable.

Do not accidentally forbid normal story action. A character can use keys, ropes, maps, computers, flashlights, lab tools, sports gear, or other realm objects. The rule is that these objects cannot replace the signature Ink tool as the character's vocabulary-magic identity.

## Rule 14: Ban Explicit Learning Narration

Do not let characters narrate the lesson in obvious educational language.

Avoid:
- "I learned that X means Y!"
- "This vocabulary word teaches us..."
- "Now I understand the definition."

Rationale: Lexi Legends should feel like story-first graphic novels. Learning is shown through plot action, word choice, and consequences, not textbook dialogue.

## Rule 15: Do-Not Lists Should Be Concrete

The final section should ban the highest-risk drift behaviors:
- wrong signature color
- replaced tool
- covered signature outfit
- unreadable target words
- adult proportions
- wrong age range
- destructive or mean characterization
- real-world brand logos
- explicit lesson narration

Rationale: negative constraints are most useful when they name specific failure modes the model is likely to produce.

## Rule 16: Separate Overlapping Shapes

When a character has hair, cloak, hood, collar, scarf, or another large shape near the head and shoulders, specify how those shapes stay visually separated.

Use:
- "Visible gap between puff base and cloak neckline."
- "Skin or shirt shows at the neck to separate hair from fabric."
- "Hood rests behind the neck and does not merge with hair."

Rationale: image models often merge dark hair, hoods, collars, and cloaks into one unreadable mass. Separation rules preserve face readability and silhouette.

## Rule 17: Use Simple Geometric Silhouette Labels

When possible, name the character's main silhouette using a simple shape.

Examples:
- "A-line trapezoid cloak."
- "Crimson hoodie block with pushed sleeves."
- "Rounded hair puff."

Rationale: shape labels help the model preserve character read in wide shots and crowded panels.

## Rule 18: Keep Pattern Detail Sparse For Small Panels

Patterned clothing should define density and scale.

Use:
- "Sparse embroidered star dots and short constellation stitches."
- "Keep simple for small panels."

Rationale: dense decorative patterns can become noise, fake text, or inconsistent symbols. Sparse pattern rules keep the design premium and reproducible.

## Visual Sheet Template

Use this structure for future cast visual sheets:

```md
# [Character] ([9 years old or 12 years old]) Visual Sheet

Runtime use: script generation and image generation
Age: [9 years old or 12 years old]
Payload rule: load this entire sheet when [Character] ([9 years old or 12 years old]) appears in a story

## Core Identity

## Story Role & Personality

## Dialogue Voice

## Physical Design

## Outfit

## [Signature Tool]

## Color Palette

## Panel Priority

## Ink VFX

## Realm Adaptation

## Do Not
```

Optional sections may be added only when they solve a real drift problem.
