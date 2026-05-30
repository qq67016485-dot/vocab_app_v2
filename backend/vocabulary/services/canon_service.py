"""
Canon file loading service for Lexi Legends graphic novel generation.

Loads character sheets, Vault specs, rulebook, and pairing dynamics from
backend/data/canon/ for injection into LLM prompts.
"""
import logging
import os
import random
import re
from functools import lru_cache
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

CANON_BASE = os.path.normpath(os.path.join(
    settings.BASE_DIR, 'data', 'canon',
))

CAST_BIBLE_PATH = os.path.normpath(os.path.join(
    CANON_BASE, 'lexi-legends-cast-bible.md',
))

TEAM_SELECTOR_SUMMARIES_PATH = os.path.normpath(os.path.join(
    CANON_BASE, 'team-selector-summaries.md',
))

SCRIPT_CHARACTER_SHEETS_PATH = os.path.normpath(os.path.join(
    CANON_BASE, 'script-character-sheets.md',
))

STYLE_LOCK = (
    "STYLE_LOCK: Consistent digital comic art. Clean ink outlines, flat color fills with "
    "soft cel-shading, warm lighting. No photorealism, no watercolor, no 3D rendering. "
    "Line weight: medium. Color saturation: high. Expressive faces, clear silhouettes."
)

ALL_TEAM_OPTIONS = [
    ['Leo'], ['Amara'], ['Mei'], ['Hugo'],
    ['Leo', 'Amara'], ['Leo', 'Mei'], ['Leo', 'Hugo'],
    ['Amara', 'Mei'], ['Amara', 'Hugo'], ['Mei', 'Hugo'],
]

SOLO_TEAMS = [t for t in ALL_TEAM_OPTIONS if len(t) == 1]
DUAL_TEAMS = [t for t in ALL_TEAM_OPTIONS if len(t) == 2]

LEXI_CHARACTERS = {'leo', 'amara', 'mei', 'hugo'}


def sample_team_options() -> list[list[str]]:
    """Pick 2 team options — all solo or all dual based on a coin flip.

    This forces a 50/50 split between solo and dual hero stories
    across generations, removing LLM bias toward dual teams.
    """
    if random.random() < 0.5:
        options = random.sample(SOLO_TEAMS, 2)
    else:
        options = random.sample(DUAL_TEAMS, 2)
    return options


def collapse_markdown(text: str) -> str:
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{2,}', ' | ', text)
    text = re.sub(r'\n', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()

@lru_cache(maxsize=32)
def _read_file(path: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except (FileNotFoundError, OSError) as exc:
        logger.warning("Canon file not found: %s (%s)", path, exc)
        return ''


def _age_prefix(age_band: str) -> str:
    return '9' if age_band == '9yo' else '12'


def _character_dir(name: str) -> str:
    safe = name.lower()
    if safe not in LEXI_CHARACTERS:
        logger.warning("Unknown character name requested: %r", name)
        return os.path.join(CANON_BASE, 'cast', '_invalid_')
    return os.path.join(CANON_BASE, 'cast', safe)


def load_character_sheet(name: str, age_band: str) -> str:
    prefix = _age_prefix(age_band)
    filename = f"{prefix}_years_old_{name.title()}.md"
    return _read_file(os.path.join(_character_dir(name), filename))


def load_character_prompt_injection(name: str, age_band: str) -> str:
    prefix = _age_prefix(age_band)
    filename = f"{prefix}_years_old_{name.title()}_prompt_injection.txt"
    return _read_file(os.path.join(_character_dir(name), filename))


def load_vault_script_context(vault_framing: bool) -> str:
    if not vault_framing:
        return ''
    vault_script = _read_file(os.path.join(CANON_BASE, 'settings', 'the-vault-script.md'))
    vault_zones = _read_file(os.path.join(CANON_BASE, 'settings', 'vault-zones-script.md'))
    parts = [p for p in (vault_script, vault_zones) if p]
    return '\n\n'.join(parts)


def load_vault_summary_premises(vault_framing: bool) -> str:
    if not vault_framing:
        return ''
    return collapse_markdown(_read_file(os.path.join(CANON_BASE, 'vault-summary-premises.md')))


KNOWN_VAULT_ZONES = {
    'reading-stacks', 'map-platform', 'ink-well', 'field-desk', 'quiet-nook',
}


def load_vault_image_prompt(vault_zone: str = '') -> str:
    base_prompt = _read_file(os.path.join(CANON_BASE, 'settings', 'the-vault-image-prompt.txt'))
    if not vault_zone:
        return base_prompt
    zone_slug = vault_zone.strip().replace(' ', '-').replace('_', '-').lower()
    if zone_slug not in KNOWN_VAULT_ZONES:
        logger.warning("Unknown vault zone requested: %r", vault_zone)
        return base_prompt
    zone_prompt = _read_file(
        os.path.join(CANON_BASE, 'settings', f'vault-zone-{zone_slug}-image-prompt.txt')
    )
    if zone_prompt:
        return f"{base_prompt}\n\n{zone_prompt}"
    return base_prompt


def load_rulebook() -> str:
    return _read_file(os.path.join(CANON_BASE, 'rulebook.md'))


def load_learning_behavior_plan() -> str:
    return _read_file(os.path.join(CANON_BASE, 'script-learning-behavior-plan.md'))


def load_style_lock() -> str:
    return STYLE_LOCK


@lru_cache(maxsize=1)
def _parse_pairing_dynamics() -> dict[str, str]:
    content = _read_file(CAST_BIBLE_PATH)
    if not content:
        return {}
    dynamics_match = re.search(r'^## Pairing Dynamics\s*\n', content, re.MULTILINE)
    if not dynamics_match:
        return {}
    dynamics_section = content[dynamics_match.end():]
    next_h2 = re.search(r'^## ', dynamics_section, re.MULTILINE)
    if next_h2:
        dynamics_section = dynamics_section[:next_h2.start()]
    pairs: dict[str, str] = {}
    pair_blocks = re.split(r'^### ', dynamics_section, flags=re.MULTILINE)
    for block in pair_blocks:
        if not block.strip():
            continue
        lines = block.strip().split('\n', 1)
        heading = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ''
        name_match = re.match(r'(\w+)\s*\+\s*(\w+)', heading)
        if name_match:
            key = _pair_key(name_match.group(1), name_match.group(2))
            pairs[key] = f"### {heading}\n\n{body}"
    return pairs


def _pair_key(a: str, b: str) -> str:
    return '+'.join(sorted([a.lower(), b.lower()]))


def load_pairing_dynamics(team: Optional[list[str]] = None) -> str:
    all_dynamics = _parse_pairing_dynamics()
    if not all_dynamics:
        return ''
    if team is None:
        return '\n\n'.join(all_dynamics.values())
    if len(team) != 2:
        return ''
    key = _pair_key(team[0], team[1])
    return all_dynamics.get(key, '')


@lru_cache(maxsize=1)
def _parse_team_selector_summaries() -> tuple[dict[str, str], dict[str, str]]:
    content = _read_file(TEAM_SELECTOR_SUMMARIES_PATH)
    if not content:
        return {}, {}

    hero_summaries: dict[str, str] = {}
    pairing_dynamics: dict[str, str] = {}

    hero_match = re.search(r'^## Hero Summaries\s*\n', content, re.MULTILINE)
    pairing_match = re.search(r'^## Pairing Dynamics\s*\n', content, re.MULTILINE)

    if hero_match:
        hero_section_end = pairing_match.start() if pairing_match else len(content)
        hero_section = content[hero_match.end():hero_section_end]
        for block in re.split(r'^### ', hero_section, flags=re.MULTILINE):
            if not block.strip():
                continue
            lines = block.strip().split('\n', 1)
            name = lines[0].strip().lower()
            body = lines[1].strip() if len(lines) > 1 else ''
            if name and body:
                hero_summaries[name] = body

    if pairing_match:
        next_h2 = re.search(r'^## ', content[pairing_match.end():], re.MULTILINE)
        pairing_section = content[pairing_match.end():]
        if next_h2:
            pairing_section = pairing_section[:next_h2.start()]
        for block in re.split(r'^### ', pairing_section, flags=re.MULTILINE):
            if not block.strip():
                continue
            lines = block.strip().split('\n', 1)
            heading = lines[0].strip()
            body = lines[1].strip() if len(lines) > 1 else ''
            name_match = re.match(r'(\w+)\s*\+\s*(\w+)', heading)
            if name_match and body:
                key = _pair_key(name_match.group(1), name_match.group(2))
                pairing_dynamics[key] = body

    return hero_summaries, pairing_dynamics


def load_team_selector_heroes(names: list[str]) -> dict[str, str]:
    hero_summaries, _ = _parse_team_selector_summaries()
    return {
        name: collapse_markdown(hero_summaries[name.lower()])
        for name in names
        if name.lower() in hero_summaries
    }


def load_team_selector_dynamics(team_options: list[list[str]]) -> list[dict[str, str]]:
    _, pairing_dynamics = _parse_team_selector_summaries()
    results = []
    for team in team_options:
        if len(team) != 2:
            continue
        key = _pair_key(team[0], team[1])
        body = pairing_dynamics.get(key, '')
        if body:
            results.append({
                'pair': f"{team[0]} + {team[1]}",
                'description': collapse_markdown(body),
            })
    return results


@lru_cache(maxsize=1)
def _parse_script_character_sheets() -> dict[str, str]:
    content = _read_file(SCRIPT_CHARACTER_SHEETS_PATH)
    if not content:
        return {}
    characters: dict[str, str] = {}
    for block in re.split(r'^## ', content, flags=re.MULTILINE):
        if not block.strip():
            continue
        lines = block.strip().split('\n', 1)
        name = lines[0].strip().lower()
        body = lines[1].strip() if len(lines) > 1 else ''
        if name and body and name in LEXI_CHARACTERS:
            characters[name] = body
    return characters


def load_script_character_sheets(names: list[str]) -> dict[str, str]:
    all_sheets = _parse_script_character_sheets()
    return {
        name: collapse_markdown(all_sheets[name.lower()])
        for name in names
        if name.lower() in all_sheets
    }
