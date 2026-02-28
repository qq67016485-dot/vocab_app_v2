from django.conf import settings


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
