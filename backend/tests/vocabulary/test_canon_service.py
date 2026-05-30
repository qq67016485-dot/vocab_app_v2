"""Tests for vocabulary.services.canon_service."""
import os
from unittest.mock import patch, mock_open

import pytest

from vocabulary.services.canon_service import (
    load_character_sheet,
    load_character_prompt_injection,
    load_vault_script_context,
    load_vault_image_prompt,
    load_rulebook,
    load_learning_behavior_plan,
    load_pairing_dynamics,
    load_style_lock,
    _parse_pairing_dynamics,
    _read_file,
    CANON_BASE,
    STYLE_LOCK,
)


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear lru_cache between tests."""
    _read_file.cache_clear()
    _parse_pairing_dynamics.cache_clear()
    yield
    _read_file.cache_clear()
    _parse_pairing_dynamics.cache_clear()


class TestLoadCharacterSheet:
    @patch('vocabulary.services.canon_service._read_file')
    def test_loads_9yo_sheet(self, mock_read):
        mock_read.return_value = '# Amara 9yo sheet'
        result = load_character_sheet('Amara', '9yo')
        expected_path = os.path.join(CANON_BASE, 'cast', 'amara', '9_years_old_Amara.md')
        mock_read.assert_called_once_with(expected_path)
        assert result == '# Amara 9yo sheet'

    @patch('vocabulary.services.canon_service._read_file')
    def test_loads_12yo_sheet(self, mock_read):
        mock_read.return_value = '# Leo 12yo sheet'
        result = load_character_sheet('leo', '12yo')
        expected_path = os.path.join(CANON_BASE, 'cast', 'leo', '12_years_old_Leo.md')
        mock_read.assert_called_once_with(expected_path)
        assert result == '# Leo 12yo sheet'

class TestLoadCharacterPromptInjection:
    @patch('vocabulary.services.canon_service._read_file')
    def test_loads_prompt_injection(self, mock_read):
        mock_read.return_value = 'CHARACTER_DESIGN_LOCK: Mei'
        result = load_character_prompt_injection('Mei', '9yo')
        expected_path = os.path.join(
            CANON_BASE, 'cast', 'mei', '9_years_old_Mei_prompt_injection.txt'
        )
        mock_read.assert_called_once_with(expected_path)
        assert result == 'CHARACTER_DESIGN_LOCK: Mei'

    @patch('vocabulary.services.canon_service._read_file')
    def test_returns_empty_on_missing_file(self, mock_read):
        mock_read.return_value = ''
        result = load_character_prompt_injection('Unknown', '9yo')
        assert result == ''


class TestLoadVaultScriptContext:
    @patch('vocabulary.services.canon_service._read_file')
    def test_returns_empty_when_no_vault_framing(self, mock_read):
        result = load_vault_script_context(False)
        assert result == ''
        mock_read.assert_not_called()

    @patch('vocabulary.services.canon_service._read_file')
    def test_loads_both_vault_files(self, mock_read):
        mock_read.side_effect = ['vault script content', 'vault zones content']
        result = load_vault_script_context(True)
        assert 'vault script content' in result
        assert 'vault zones content' in result
        assert mock_read.call_count == 2


class TestLoadVaultImagePrompt:
    @patch('vocabulary.services.canon_service._read_file')
    def test_loads_base_prompt_without_zone(self, mock_read):
        mock_read.return_value = 'SETTING: The Vault'
        result = load_vault_image_prompt('')
        assert result == 'SETTING: The Vault'

    @patch('vocabulary.services.canon_service._read_file')
    def test_loads_base_and_zone_prompt(self, mock_read):
        mock_read.side_effect = ['SETTING: The Vault', 'SETTING: Map Platform']
        result = load_vault_image_prompt('map_platform')
        assert 'SETTING: The Vault' in result
        assert 'SETTING: Map Platform' in result

    @patch('vocabulary.services.canon_service._read_file')
    def test_normalizes_zone_slug(self, mock_read):
        mock_read.side_effect = ['base', 'zone']
        load_vault_image_prompt('map_platform')
        zone_call = mock_read.call_args_list[1]
        assert 'vault-zone-map-platform-image-prompt.txt' in zone_call[0][0]


class TestLoadPairingDynamics:
    @patch('vocabulary.services.canon_service._read_file')
    def test_returns_all_pairs_when_none(self, mock_read):
        mock_read.return_value = (
            "## Pairing Dynamics\n\n"
            "### Leo + Amara\n\nDynamic: Improvisation meets research.\n\n"
            "### Mei + Hugo\n\nDynamic: Speed meets steadiness.\n\n"
            "## Story-Specific Characters\n"
        )
        result = load_pairing_dynamics(None)
        assert 'Leo + Amara' in result
        assert 'Mei + Hugo' in result

    @patch('vocabulary.services.canon_service._read_file')
    def test_returns_specific_pair(self, mock_read):
        mock_read.return_value = (
            "## Pairing Dynamics\n\n"
            "### Leo + Amara\n\nDynamic: Improvisation meets research.\n\n"
            "### Mei + Hugo\n\nDynamic: Speed meets steadiness.\n\n"
            "## Story-Specific Characters\n"
        )
        result = load_pairing_dynamics(['Amara', 'Leo'])
        assert 'Leo + Amara' in result
        assert 'Mei + Hugo' not in result

    @patch('vocabulary.services.canon_service._read_file')
    def test_returns_empty_for_solo_team(self, mock_read):
        mock_read.return_value = (
            "## Pairing Dynamics\n\n"
            "### Leo + Amara\n\nDynamic: test.\n\n"
            "## End\n"
        )
        result = load_pairing_dynamics(['Leo'])
        assert result == ''


class TestLoadStyleLock:
    def test_returns_style_lock_string(self):
        result = load_style_lock()
        assert result == STYLE_LOCK
        assert 'No photorealism' in result


class TestReadFileIntegration:
    def test_reads_real_canon_file(self):
        _read_file.cache_clear()
        path = os.path.join(CANON_BASE, 'rulebook.md')
        if os.path.exists(path):
            result = _read_file(path)
            assert '# Lexi Legends Runtime Canon Rulebook' in result

    def test_returns_empty_for_missing_file(self):
        _read_file.cache_clear()
        result = _read_file('/nonexistent/path/file.md')
        assert result == ''
