import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_api_endpoint_repo, get_api_registry_service, get_api_service_repo, require_roles
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.models.api_service import ApiService
from app.db.models.enums import UserRole
from app.db.models.user import User
from app.repositories.api_endpoint_repo import ApiEndpointRepo
from app.repositories.api_service_repo import ApiServiceRepo
from app.schemas.api_service import (
    ApiEndpointCreate,
    ApiEndpointOut,
    ApiEndpointUpdate,
    ApiServiceCreate,
    ApiServiceOut,
    ApiServiceUpdate,
)
from app.services.api_registry.api_registry_service import ApiRegistryService

logger = get_logger(__name__)

router = APIRouter(prefix="/mcp/api-services", tags=["api_registry"])


@router.get("", response_model=list[ApiServiceOut])
async def list_api_services(
    user: User = Depends(require_roles(UserRole.admin)), repo: ApiServiceRepo = Depends(get_api_service_repo)
) -> list[ApiServiceOut]:
    services = await repo.list_with_endpoint_counts()
    logger.info("listing API services", user_id=user.id, count=len(services))
    return [ApiServiceOut.from_model(service, count) for service, count in services]


@router.post("", response_model=ApiServiceOut, status_code=201)
async def create_api_service(
    body: ApiServiceCreate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: ApiServiceRepo = Depends(get_api_service_repo),
) -> ApiServiceOut:
    logger.info("creating API service", user_id=user.id, name=body.name, base_url=body.base_url)
    service = await repo.add(
        ApiService(
            name=body.name,
            description=body.description,
            base_url=body.base_url,
            authentication_type=body.authentication_type,
            auth_config=body.auth_config,
            headers=body.headers,
            timeout_seconds=body.timeout_seconds,
            retry_policy=body.retry_policy,
            rate_limit_per_window=body.rate_limit_per_window,
            status=body.status,
            extra_metadata=body.metadata,
        )
    )
    logger.info("api_service_created", api_service_id=str(service.id), name=service.name)
    return ApiServiceOut.from_model(service)


@router.put("/{service_id}", response_model=ApiServiceOut)
async def update_api_service(
    service_id: uuid.UUID,
    body: ApiServiceUpdate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: ApiServiceRepo = Depends(get_api_service_repo),
) -> ApiServiceOut:
    logger.info("updating API service", user_id=user.id, service_id=str(service_id), fields=list(body.model_dump(exclude_none=True)))
    service = await repo.get(service_id)
    if service is None:
        raise NotFoundError("API service not found")
    if body.description is not None:
        service.description = body.description
    if body.base_url is not None:
        service.base_url = body.base_url
    if body.authentication_type is not None:
        service.authentication_type = body.authentication_type
    if body.auth_config is not None:
        service.auth_config = body.auth_config
    if body.headers is not None:
        service.headers = body.headers
    if body.timeout_seconds is not None:
        service.timeout_seconds = body.timeout_seconds
    if body.retry_policy is not None:
        service.retry_policy = body.retry_policy
    if body.rate_limit_per_window is not None:
        service.rate_limit_per_window = body.rate_limit_per_window
    if body.status is not None:
        service.status = body.status
    if body.metadata is not None:
        service.extra_metadata = body.metadata
    await repo.db.flush()
    await repo.db.refresh(service)
    logger.info("api_service_updated", api_service_id=str(service_id))
    return ApiServiceOut.from_model(service)


@router.delete("/{service_id}", status_code=204)
async def delete_api_service(
    service_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: ApiServiceRepo = Depends(get_api_service_repo),
) -> None:
    logger.info("deleting API service", user_id=user.id, service_id=str(service_id))
    service = await repo.get(service_id)
    if service is None:
        raise NotFoundError("API service not found")
    # Cascades to api_endpoints, and from there to each endpoint's paired McpTool
    # row, via the FKs' ondelete=CASCADE -- same pattern as deleting an McpServer.
    await repo.delete(service)
    logger.info("api_service_deleted", api_service_id=str(service_id))


@router.get("/{service_id}/endpoints", response_model=list[ApiEndpointOut])
async def list_api_endpoints(
    service_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    endpoint_repo: ApiEndpointRepo = Depends(get_api_endpoint_repo),
) -> list[ApiEndpointOut]:
    endpoints = await endpoint_repo.list_by_service(service_id)
    logger.info("listing API endpoints", user_id=user.id, service_id=str(service_id), count=len(endpoints))
    return [ApiEndpointOut.from_model(e) for e in endpoints]


@router.post("/{service_id}/endpoints", response_model=ApiEndpointOut, status_code=201)
async def register_api_endpoint(
    service_id: uuid.UUID,
    body: ApiEndpointCreate,
    user: User = Depends(require_roles(UserRole.admin)),
    service_repo: ApiServiceRepo = Depends(get_api_service_repo),
    registry: ApiRegistryService = Depends(get_api_registry_service),
) -> ApiEndpointOut:
    logger.info("registering API endpoint", user_id=user.id, service_id=str(service_id), tool_name=body.tool_name, path=body.path)
    """The "REST endpoint automatically becomes an MCP Tool" step: registering an
    endpoint here immediately creates its paired, callable McpTool row -- no
    separate discovery/sync step, unlike MCP servers."""
    if await service_repo.get(service_id) is None:
        raise NotFoundError("API service not found")
    endpoint = await registry.register_endpoint(
        service_id,
        tool_name=body.tool_name,
        description=body.description,
        method=body.method,
        path=body.path,
        parameters={name: param.model_dump() for name, param in body.parameters.items()},
        enabled=body.enabled,
    )
    return ApiEndpointOut.from_model(endpoint)


@router.put("/{service_id}/endpoints/{endpoint_id}", response_model=ApiEndpointOut)
async def update_api_endpoint(
    service_id: uuid.UUID,
    endpoint_id: uuid.UUID,
    body: ApiEndpointUpdate,
    user: User = Depends(require_roles(UserRole.admin)),
    endpoint_repo: ApiEndpointRepo = Depends(get_api_endpoint_repo),
    registry: ApiRegistryService = Depends(get_api_registry_service),
) -> ApiEndpointOut:
    logger.info("updating API endpoint", user_id=user.id, service_id=str(service_id), endpoint_id=str(endpoint_id), fields=list((body.model_dump(exclude_none=True) or {}).keys()))
    endpoint = await endpoint_repo.get(endpoint_id)
    if endpoint is None or endpoint.api_service_id != service_id:
        raise NotFoundError("API endpoint not found")
    parameters = (
        {name: param.model_dump() for name, param in body.parameters.items()} if body.parameters is not None else None
    )
    endpoint = await registry.update_endpoint(
        endpoint,
        description=body.description,
        method=body.method,
        path=body.path,
        parameters=parameters,
        enabled=body.enabled,
    )
    return ApiEndpointOut.from_model(endpoint)


@router.delete("/{service_id}/endpoints/{endpoint_id}", status_code=204)
async def delete_api_endpoint(
    service_id: uuid.UUID,
    endpoint_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    endpoint_repo: ApiEndpointRepo = Depends(get_api_endpoint_repo),
    registry: ApiRegistryService = Depends(get_api_registry_service),
) -> None:
    logger.info("deleting API endpoint", user_id=user.id, service_id=str(service_id), endpoint_id=str(endpoint_id))
    endpoint = await endpoint_repo.get(endpoint_id)
    if endpoint is None or endpoint.api_service_id != service_id:
        raise NotFoundError("API endpoint not found")
    await registry.delete_endpoint(endpoint)
