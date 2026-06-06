"""Tests for the LLM config-set feature: per-set step configs + active selection."""
import pytest
from rest_framework.test import APIClient

from vocabulary.models import LLMConfigSet, LLMSite, LLMStepConfig
from vocabulary.services.generation import llm_config_service
from tests.factories import AdminUserFactory, StudentUserFactory


def _make_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def admin_client():
    return _make_client(AdminUserFactory())


@pytest.fixture
def seeded(db):
    """Two sites and three sets, each with one step config (word_lookup).

    The data migration seeds 3 sets at DB setup; clear all LLM config rows so
    this fixture fully controls the state.
    """
    LLMStepConfig.objects.all().delete()
    LLMConfigSet.objects.all().delete()
    LLMSite.objects.all().delete()
    site_a = LLMSite.objects.create(
        name='Site A', base_url='', api_key_env_var='GEMINI_API_KEY',
        provider_type=LLMSite.ProviderType.GEMINI_NATIVE,
    )
    site_b = LLMSite.objects.create(
        name='Site B', base_url='https://b.example/v1', api_key_env_var='OPENAI_API_KEY',
        provider_type=LLMSite.ProviderType.OPENAI_COMPATIBLE,
    )
    sets = []
    for idx in range(1, 4):
        cs = LLMConfigSet.objects.create(name=f'Set {idx}', position=idx, is_active=(idx == 1))
        LLMStepConfig.objects.create(
            config_set=cs, step_key='word_lookup',
            primary_site=site_a, primary_model=f'model-{idx}-primary',
            fallback_site=site_a, fallback_model=f'model-{idx}-fallback',
        )
        sets.append(cs)
    llm_config_service.invalidate_cache()
    return {'sites': (site_a, site_b), 'sets': sets}


@pytest.mark.django_db
class TestConfigSetEndpoints:
    def test_list_sets_requires_admin(self, seeded):
        client = _make_client(StudentUserFactory())
        assert client.get('/api/admin/llm-config-sets/').status_code == 403

    def test_list_sets(self, admin_client, seeded):
        res = admin_client.get('/api/admin/llm-config-sets/')
        assert res.status_code == 200
        assert [s['name'] for s in res.data] == ['Set 1', 'Set 2', 'Set 3']
        assert [s['is_active'] for s in res.data] == [True, False, False]

    def test_activate_set_deactivates_others(self, admin_client, seeded):
        target = seeded['sets'][1]
        res = admin_client.put(f'/api/admin/llm-config-sets/{target.id}/', {'is_active': True}, format='json')
        assert res.status_code == 200
        active = LLMConfigSet.objects.filter(is_active=True)
        assert active.count() == 1
        assert active.first().id == target.id

    def test_cannot_deactivate_active_set(self, admin_client, seeded):
        active = seeded['sets'][0]
        res = admin_client.put(f'/api/admin/llm-config-sets/{active.id}/', {'is_active': False}, format='json')
        assert res.status_code == 400

    def test_rename_set(self, admin_client, seeded):
        target = seeded['sets'][2]
        res = admin_client.put(f'/api/admin/llm-config-sets/{target.id}/', {'name': 'Production'}, format='json')
        assert res.status_code == 200
        target.refresh_from_db()
        assert target.name == 'Production'


@pytest.mark.django_db
class TestStepConfigSetScoping:
    def test_get_defaults_to_active_set(self, admin_client, seeded):
        res = admin_client.get('/api/admin/llm-step-configs/')
        assert res.status_code == 200
        assert res.data['set']['name'] == 'Set 1'
        assert res.data['configs'][0]['primary_model'] == 'model-1-primary'

    def test_get_specific_set(self, admin_client, seeded):
        set3 = seeded['sets'][2]
        res = admin_client.get(f'/api/admin/llm-step-configs/?set={set3.id}')
        assert res.data['set']['name'] == 'Set 3'
        assert res.data['configs'][0]['primary_model'] == 'model-3-primary'

    def test_put_updates_only_target_set(self, admin_client, seeded):
        site_b = seeded['sites'][1]
        set2 = seeded['sets'][1]
        payload = [{
            'step_key': 'word_lookup',
            'primary_site': site_b.id, 'primary_model': 'edited-primary',
            'fallback_site': site_b.id, 'fallback_model': 'edited-fallback',
        }]
        res = admin_client.put(f'/api/admin/llm-step-configs/?set={set2.id}', payload, format='json')
        assert res.status_code == 200
        # Set 2 changed; Set 1 untouched.
        s2 = LLMStepConfig.objects.get(config_set=set2, step_key='word_lookup')
        s1 = LLMStepConfig.objects.get(config_set=seeded['sets'][0], step_key='word_lookup')
        assert s2.primary_model == 'edited-primary'
        assert s1.primary_model == 'model-1-primary'

    def test_put_rejects_unknown_site(self, admin_client, seeded):
        payload = [{
            'step_key': 'word_lookup',
            'primary_site': 99999, 'primary_model': 'x',
            'fallback_site': 99999, 'fallback_model': 'y',
        }]
        res = admin_client.put('/api/admin/llm-step-configs/', payload, format='json')
        assert res.status_code == 400


@pytest.mark.django_db
class TestServiceReadsActiveSet:
    def test_get_step_config_reads_active_set(self, seeded):
        cfg = llm_config_service.get_step_config('word_lookup')
        assert cfg['primary']['model'] == 'model-1-primary'

    def test_get_step_config_follows_activation(self, seeded):
        seeded['sets'][2].is_active = True
        seeded['sets'][2].save()
        LLMConfigSet.objects.exclude(pk=seeded['sets'][2].pk).update(is_active=False)
        llm_config_service.invalidate_cache()
        cfg = llm_config_service.get_step_config('word_lookup')
        assert cfg['primary']['model'] == 'model-3-primary'
