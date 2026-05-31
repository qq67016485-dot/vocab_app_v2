from datetime import datetime, time

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone


def get_definition_translations(word, language, fields=('definition_text',)):
    """Look up translated text for a word's first definition.

    Returns a dict mapping each requested field name to its translated string
    (empty string when no translation exists). Centralizes the Translation
    lookup shared by the dashboard, practice, and instructional services.
    """
    from vocabulary.models import Translation, WordDefinition

    result = {field: '' for field in fields}
    defn = word.definitions.first()
    if not defn:
        return result

    ct = ContentType.objects.get_for_model(WordDefinition)
    translations = Translation.objects.filter(
        content_type=ct,
        object_id=defn.id,
        language=language,
        field_name__in=fields,
    )
    for t in translations:
        if t.field_name in result:
            result[t.field_name] = t.translated_text
    return result


def get_definition_translation(word, language):
    """Convenience wrapper returning just the definition_text translation."""
    return get_definition_translations(word, language, fields=('definition_text',))['definition_text']


def end_of_local_day(day=None):
    """Return the final instant of a local calendar day."""
    target_day = day or timezone.localdate()
    return timezone.make_aware(
        datetime.combine(target_day, time.max),
        timezone.get_current_timezone(),
    )


def get_tier_info(level):
    """Returns tier data dict for the given level, or None."""
    for tier_name, tier_data in settings.TIER_CONFIG.items():
        if tier_data['min_level'] <= level <= tier_data['max_level']:
            tier_data_copy = tier_data.copy()
            tier_data_copy['name'] = tier_name.capitalize()
            return tier_data_copy
    return None


def calculate_xp_in_current_level(xp_points, level):
    """Calculates XP progress within the current level."""
    tier_info = get_tier_info(level)
    if not tier_info:
        return 0

    total_xp_for_prior_tiers = 0
    for tier in settings.TIER_CONFIG.values():
        if tier['min_level'] < tier_info['min_level']:
            levels_in_tier = tier['max_level'] - tier['min_level'] + 1
            total_xp_for_prior_tiers += levels_in_tier * tier['xp_per_level']

    levels_completed_in_tier = level - tier_info['min_level']
    xp_for_levels_within_tier = levels_completed_in_tier * tier_info['xp_per_level']

    start_xp_of_current_level = total_xp_for_prior_tiers + xp_for_levels_within_tier

    return xp_points - start_xp_of_current_level
