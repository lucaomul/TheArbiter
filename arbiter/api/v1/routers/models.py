from fastapi import APIRouter, Depends

from arbiter.api.dependencies import require_api_key
from arbiter.infra.plugin_registry import get_plugin_registry

router = APIRouter(tags=["models"])


@router.get("/models", dependencies=[Depends(require_api_key)])
async def list_models() -> dict:
    registry = get_plugin_registry()
    models = []
    for model_id in registry.all_model_ids():
        plugin = registry.get(model_id)
        if plugin is None:
            continue
        models.append(
            {
                "model_id": plugin.model_id,
                "provider": plugin.provider,
                "roles": list(plugin.roles or []),
                "quality_tier": plugin.quality_tier,
                "cost": plugin.cost,
                "enabled": plugin.enabled,
                "availability": plugin.availability,
                "source": plugin.source,
                "display_name": plugin.display_name,
            }
        )
    return {
        "count": len(models),
        "models": models,
    }
