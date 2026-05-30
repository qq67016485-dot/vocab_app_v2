"""LLM Configuration views — Admin-only endpoints for managing API sites and step configs."""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import LLMSite, LLMStepConfig
from ..permissions import IsAdmin
from vocabulary.services.generation.llm_config_service import invalidate_cache


# Pipeline order for step configs — mirrors the LLMStepConfig.StepKey enum
# declaration order so the admin UI lists steps in execution order rather than
# alphabetically. Index lookup; unknown keys sort last.
_STEP_KEY_ORDER = {key: idx for idx, key in enumerate(LLMStepConfig.StepKey.values)}


def _step_configs_in_pipeline_order():
    configs = LLMStepConfig.objects.select_related('primary_site', 'fallback_site')
    return sorted(configs, key=lambda cfg: _STEP_KEY_ORDER.get(cfg.step_key, len(_STEP_KEY_ORDER)))


class LLMSitesView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        sites = LLMSite.objects.order_by('name')
        data = [_serialize_site(site) for site in sites]
        return Response(data)

    def post(self, request):
        name = (request.data.get('name') or '').strip()
        base_url = (request.data.get('base_url') or '').strip()
        api_key_env_var = (request.data.get('api_key_env_var') or '').strip()
        provider_type = (request.data.get('provider_type') or '').strip()

        if not name or not api_key_env_var or not provider_type:
            return Response(
                {'error': 'name, api_key_env_var, and provider_type are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if provider_type not in LLMSite.ProviderType.values:
            return Response(
                {'error': f'Invalid provider_type. Must be one of: {list(LLMSite.ProviderType.values)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if LLMSite.objects.filter(name=name).exists():
            return Response(
                {'error': f'A site named "{name}" already exists.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        site = LLMSite.objects.create(
            name=name,
            base_url=base_url,
            api_key_env_var=api_key_env_var,
            provider_type=provider_type,
        )
        invalidate_cache()
        return Response(_serialize_site(site), status=status.HTTP_201_CREATED)


class LLMSiteDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def put(self, request, pk):
        try:
            site = LLMSite.objects.get(pk=pk)
        except LLMSite.DoesNotExist:
            return Response({'error': 'Site not found.'}, status=status.HTTP_404_NOT_FOUND)

        name = (request.data.get('name') or '').strip()
        base_url = (request.data.get('base_url') or '').strip()
        api_key_env_var = (request.data.get('api_key_env_var') or '').strip()
        provider_type = (request.data.get('provider_type') or '').strip()

        if not name or not api_key_env_var or not provider_type:
            return Response(
                {'error': 'name, api_key_env_var, and provider_type are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if provider_type not in LLMSite.ProviderType.values:
            return Response(
                {'error': f'Invalid provider_type. Must be one of: {list(LLMSite.ProviderType.values)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if LLMSite.objects.filter(name=name).exclude(pk=pk).exists():
            return Response(
                {'error': f'A site named "{name}" already exists.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        site.name = name
        site.base_url = base_url
        site.api_key_env_var = api_key_env_var
        site.provider_type = provider_type
        site.save()
        invalidate_cache()
        return Response(_serialize_site(site))

    def delete(self, request, pk):
        try:
            site = LLMSite.objects.get(pk=pk)
        except LLMSite.DoesNotExist:
            return Response({'error': 'Site not found.'}, status=status.HTTP_404_NOT_FOUND)

        primary_refs = LLMStepConfig.objects.filter(primary_site=site).count()
        fallback_refs = LLMStepConfig.objects.filter(fallback_site=site).count()
        if primary_refs or fallback_refs:
            return Response(
                {'error': f'Cannot delete: site is referenced by {primary_refs + fallback_refs} step config(s). Reassign them first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        site.delete()
        invalidate_cache()
        return Response(status=status.HTTP_204_NO_CONTENT)


class LLMStepConfigsView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        configs = _step_configs_in_pipeline_order()
        data = [_serialize_step_config(cfg) for cfg in configs]
        return Response(data)

    def put(self, request):
        configs_data = request.data
        if not isinstance(configs_data, list):
            return Response(
                {'error': 'Expected a list of step config objects.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_step_keys = set(LLMStepConfig.StepKey.values)
        site_ids = set(LLMSite.objects.values_list('id', flat=True))
        errors = []

        for item in configs_data:
            step_key = item.get('step_key', '')
            if step_key not in valid_step_keys:
                errors.append(f'Invalid step_key: {step_key}')
                continue
            if item.get('primary_site') not in site_ids:
                errors.append(f'{step_key}: invalid primary_site id')
            if item.get('fallback_site') not in site_ids:
                errors.append(f'{step_key}: invalid fallback_site id')
            if not (item.get('primary_model') or '').strip():
                errors.append(f'{step_key}: primary_model is required')
            if not (item.get('fallback_model') or '').strip():
                errors.append(f'{step_key}: fallback_model is required')

        if errors:
            return Response({'errors': errors}, status=status.HTTP_400_BAD_REQUEST)

        for item in configs_data:
            LLMStepConfig.objects.filter(step_key=item['step_key']).update(
                primary_site_id=item['primary_site'],
                primary_model=item['primary_model'].strip(),
                fallback_site_id=item['fallback_site'],
                fallback_model=item['fallback_model'].strip(),
            )

        invalidate_cache()
        configs = _step_configs_in_pipeline_order()
        return Response([_serialize_step_config(cfg) for cfg in configs])


def _serialize_site(site: LLMSite) -> dict:
    return {
        'id': site.id,
        'name': site.name,
        'base_url': site.base_url,
        'api_key_env_var': site.api_key_env_var,
        'provider_type': site.provider_type,
        'has_api_key': bool(site.resolve_api_key()),
    }


def _serialize_step_config(cfg: LLMStepConfig) -> dict:
    return {
        'step_key': cfg.step_key,
        'step_display': cfg.get_step_key_display(),
        'primary_site': cfg.primary_site_id,
        'primary_site_name': cfg.primary_site.name,
        'primary_model': cfg.primary_model,
        'fallback_site': cfg.fallback_site_id,
        'fallback_site_name': cfg.fallback_site.name,
        'fallback_model': cfg.fallback_model,
    }
