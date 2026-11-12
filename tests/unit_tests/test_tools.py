"""Offline tests: LangChain standard unit tests + behaviour against a mocked API."""
from __future__ import annotations

import json

import httpx
import pytest
from langchain_tests.unit_tests import ToolsUnitTests
from lexio_rent import Lexio

from langchain_lexio import (
    LexioCheckAvailabilityTool,
    LexioCreateQuoteTool,
    LexioGetRentalTool,
    LexioListRentalsTool,
    LexioSearchVehiclesTool,
    LexioToolkit,
)


def fake_client(handler, seen):
    def wrapped(req):
        seen.append(req)
        return handler(req)

    return Lexio("lck_test", http_client=httpx.Client(transport=httpx.MockTransport(wrapped)), max_retries=0)


class _Std(ToolsUnitTests):
    @property
    def tool_constructor_params(self) -> dict:
        return {"api_key": "lck_test"}

    @property
    def init_from_env_params(self):
        return ({"LEXIO_API_KEY": "lck_env"}, {}, {"api_key": "lck_env"})


class TestSearchVehiclesStandard(_Std):
    @property
    def tool_constructor(self):
        return LexioSearchVehiclesTool

    @property
    def tool_invoke_params_example(self) -> dict:
        return {"vehicle_type": "SUV", "limit": 5}


class TestCheckAvailabilityStandard(_Std):
    @property
    def tool_constructor(self):
        return LexioCheckAvailabilityTool

    @property
    def tool_invoke_params_example(self) -> dict:
        return {"start_at": "2026-12-14T09:00:00", "end_at": "2026-12-16T18:00:00"}


class TestGetRentalStandard(_Std):
    @property
    def tool_constructor(self):
        return LexioGetRentalTool

    @property
    def tool_invoke_params_example(self) -> dict:
        return {"rental_id": "9c2d7e4a-5b1f-4d3c-8a6e-0f1b2c3d4e5f"}


def test_toolkit_is_read_only_by_default():
    names = [t.name for t in LexioToolkit(api_key="lck_test").get_tools()]
    assert "lexio_create_quote" not in names
    assert names == [
        "lexio_search_vehicles",
        "lexio_check_availability",
        "lexio_list_rentals",
        "lexio_get_rental",
        "lexio_find_customer",
        "lexio_list_categories",
    ]
    assert "lexio_create_quote" in [t.name for t in LexioToolkit(api_key="lck_test", allow_quotes=True).get_tools()]


def test_toolkit_shares_one_client():
    tools = LexioToolkit(api_key="lck_test").get_tools()
    assert len({id(t.client) for t in tools}) == 1


def test_search_vehicles_filters_and_compacts():
    seen = []

    def handler(req):
        return httpx.Response(200, json={"data": [{"id": "v1", "plate": "AB-123-CD", "vin": "secret-ish", "status": "AVAILABLE"}], "nextCursor": None})

    tool = LexioSearchVehiclesTool(client=fake_client(handler, seen))
    out = json.loads(tool.invoke({"vehicle_type": "VAN"}))
    assert out == [{"id": "v1", "plate": "AB-123-CD", "status": "AVAILABLE"}]
    url = str(seen[0].url)
    assert "isArchived=false" in url and "vehicleType=VAN" in url
    assert seen[0].headers["authorization"] == "Bearer lck_test"


def test_max_results_caps_pagination():
    seen = []
    pages = {None: {"data": [{"id": i} for i in range(3)], "nextCursor": "c2"}, "c2": {"data": [{"id": 9}], "nextCursor": None}}

    def handler(req):
        return httpx.Response(200, json=pages[req.url.params.get("cursor")])

    tool = LexioSearchVehiclesTool(client=fake_client(handler, seen), max_results=2)
    assert len(json.loads(tool.invoke({}))) == 2
    assert len(seen) == 1


def test_check_availability_params():
    seen = []

    def handler(req):
        return httpx.Response(200, json={"data": [{"vehicle": {"id": "v1", "name": "Clio"}, "isAvailable": True, "totalTTC": 120.5, "currency": "EUR", "period": {"billedDays": 3}}], "nextCursor": None})

    tool = LexioCheckAvailabilityTool(client=fake_client(handler, seen))
    out = json.loads(tool.invoke({"start_at": "2026-12-14T09:00:00", "end_at": "2026-12-16T18:00:00"}))
    assert out[0]["totalTTC"] == 120.5 and out[0]["billedDays"] == 3
    params = seen[0].url.params
    assert params["startAt"] == "2026-12-14T09:00:00" and params["isAvailable"] == "true"


def test_list_rentals_maps_date_window():
    seen = []
    tool = LexioListRentalsTool(client=fake_client(lambda r: httpx.Response(200, json={"data": [], "nextCursor": None}), seen))
    assert json.loads(tool.invoke({"status": "RESERVED", "from_date": "2026-12-01", "to_date": "2026-12-31"})) == []
    params = seen[0].url.params
    assert params["from"] == "2026-12-01" and params["to"] == "2026-12-31" and params["status"] == "RESERVED"


def test_create_quote_body_and_idempotency():
    seen = []

    def handler(req):
        return httpx.Response(201, json={"data": {"id": "q1", "totalTTC": 99}})

    tool = LexioCreateQuoteTool(client=fake_client(handler, seen))
    out = json.loads(tool.invoke({"vehicle_id": "v1", "start_at": "2026-12-14T09:00:00", "end_at": "2026-12-16T18:00:00"}))
    assert out["id"] == "q1"
    assert json.loads(seen[0].content) == {"vehicleId": "v1", "startAt": "2026-12-14T09:00:00", "endAt": "2026-12-16T18:00:00"}
    assert seen[0].method == "POST"


def test_api_errors_surface():
    from lexio_rent import NotFoundError

    tool = LexioGetRentalTool(client=fake_client(lambda r: httpx.Response(404, json={"code": "NOT_FOUND", "detail": "x"}), []))
    with pytest.raises(NotFoundError):
        tool.invoke({"rental_id": "nope"})
