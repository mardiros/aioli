import pytest

from blacksmith.domain.exceptions import UnregisteredServiceException
from blacksmith.sd.adapters.consul import (
    ConsulDiscovery,
    Service,
    ServiceRequest,
    blacksmith_cli,
)
from blacksmith.sd.adapters.router import RouterDiscovery
from blacksmith.sd.adapters.static import StaticDiscovery


@pytest.mark.asyncio
async def test_static_discovery(static_sd: StaticDiscovery):
    endpoint = await static_sd.get_endpoint("dummy", "v1")
    assert endpoint == "https://dummy.v1/"


@pytest.mark.asyncio
async def test_static_discovery_raise(static_sd: StaticDiscovery):
    with pytest.raises(UnregisteredServiceException) as ctx:
        await static_sd.get_endpoint("dummy", "v2")
    assert str(ctx.value) == "Unregistered service 'dummy/v2'"


@pytest.mark.asyncio
async def test_consul_sd_cli():
    cli = blacksmith_cli("http://consul:8888", "abc")
    assert cli.registry.client_service == {"consul": ("consul", "v1")}
    assert (
        cli.registry.clients["consul"]["services"].collection.path
        == "/catalog/service/{name}"
    )
    assert cli.registry.clients["consul"]["services"].collection.contract == {
        "GET": (ServiceRequest, Service)
    }


@pytest.mark.asyncio
async def test_consul_discovery_get_service_name(consul_sd: ConsulDiscovery):
    name = consul_sd.format_service_name("dummy-name", None)
    assert name == "dummy-name"

    name = consul_sd.format_service_name("dummy-name", "v42")
    assert name == "dummy-name-v42"


@pytest.mark.asyncio
async def test_consul_discovery_format_endoint(consul_sd: ConsulDiscovery):
    endpoint = consul_sd.format_endoint(None, "1.2.3.4", 8080)
    assert endpoint == "http://1.2.3.4:8080"

    endpoint = consul_sd.format_endoint("v42", "1.2.3.4", 8080)
    assert endpoint == "http://1.2.3.4:8080/v42"


@pytest.mark.asyncio
async def test_consul_discovery_get_endpoint(consul_sd: ConsulDiscovery):
    endpoint = await consul_sd.get_endpoint("dummy", "v1")
    assert endpoint == "http://8.8.8.8:1234/v1"


@pytest.mark.asyncio
async def test_consul_discovery_resolve(consul_sd: ConsulDiscovery):
    service = await consul_sd.resolve("dummy", "v1")
    assert service == Service(ServiceAddress="8.8.8.8", ServicePort=1234)


@pytest.mark.asyncio
async def test_consul_discovery_resolve_unversionned_endpoint(
    consul_sd: ConsulDiscovery,
):
    service = await consul_sd.resolve("dummy", None)
    assert service == Service(ServiceAddress="8.8.8.8", ServicePort=1234)


@pytest.mark.asyncio
async def test_consul_discovery_resolve_unregistered(consul_sd: ConsulDiscovery):
    with pytest.raises(UnregisteredServiceException) as ctx:
        await consul_sd.resolve("dummy", "v2")
    assert str(ctx.value) == "Unregistered service 'dummy/v2'"


@pytest.mark.asyncio
async def test_consul_discovery_get_unversionned_endpoint(consul_sd: ConsulDiscovery):
    endpoint = await consul_sd.get_endpoint("dummy", None)
    assert endpoint == "http://8.8.8.8:1234"


@pytest.mark.asyncio
async def test_consul_discovery_get_endpoint_unregistered(consul_sd: ConsulDiscovery):
    with pytest.raises(UnregisteredServiceException) as ctx:
        await consul_sd.get_endpoint("dummy", "v2")
    assert str(ctx.value) == "Unregistered service 'dummy/v2'"


from blacksmith.sd.adapters.consul import ConsulApiError


@pytest.mark.asyncio
async def test_consul_resolve_consul_error(consul_sd: ConsulDiscovery):
    with pytest.raises(ConsulApiError) as ctx:
        await consul_sd.resolve("dummy", "v3")
    assert str(ctx.value) == "422 Unprocessable entity"


@pytest.mark.asyncio
async def test_router_sd_get_endpoint_versionned(router_sd: RouterDiscovery):
    endpoint = await router_sd.get_endpoint("dummy", "v1")
    assert endpoint == "http://router/dummy-v1/v1"


@pytest.mark.asyncio
async def test_router_sd_get_endpoint_unversionned(router_sd: RouterDiscovery):
    endpoint = await router_sd.get_endpoint("dummy", None)
    assert endpoint == "http://router/dummy"
