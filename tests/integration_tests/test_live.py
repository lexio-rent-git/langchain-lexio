"""LangChain standard integration tests against a real Lexio organization (needs LEXIO_API_KEY)."""
from __future__ import annotations

import json
import os

import pytest
from langchain_tests.integration_tests import ToolsIntegrationTests

from langchain_lexio import LexioCheckAvailabilityTool, LexioListRentalsTool, LexioSearchVehiclesTool, LexioToolkit

pytestmark = pytest.mark.skipif(not os.environ.get("LEXIO_API_KEY"), reason="set LEXIO_API_KEY to run live tests")


class TestSearchVehiclesLive(ToolsIntegrationTests):
    @property
    def tool_constructor(self):
        return LexioSearchVehiclesTool

    @property
    def tool_invoke_params_example(self) -> dict:
        return {"limit": 3}


class TestCheckAvailabilityLive(ToolsIntegrationTests):
    @property
    def tool_constructor(self):
        return LexioCheckAvailabilityTool

    @property
    def tool_invoke_params_example(self) -> dict:
        return {"start_at": "2027-03-01T09:00:00", "end_at": "2027-03-03T18:00:00", "limit": 3}


class TestListRentalsLive(ToolsIntegrationTests):
    @property
    def tool_constructor(self):
        return LexioListRentalsTool

    @property
    def tool_invoke_params_example(self) -> dict:
        return {"status": "RESERVED,IN_PROGRESS", "limit": 3}


def test_toolkit_end_to_end():
    tools = {t.name: t for t in LexioToolkit().get_tools()}
    vehicles = json.loads(tools["lexio_search_vehicles"].invoke({"limit": 2}))
    assert vehicles and vehicles[0]["id"]
    rentals = json.loads(tools["lexio_list_rentals"].invoke({"limit": 1}))
    if rentals:
        full = json.loads(tools["lexio_get_rental"].invoke({"rental_id": rentals[0]["id"]}))
        assert full["id"] == rentals[0]["id"]
