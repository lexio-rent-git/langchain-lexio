"""Toolkit bundling the Lexio Rent tools."""
from __future__ import annotations

import os
from typing import Any, Optional

from langchain_core.utils import secret_from_env
from langchain_core.tools import BaseTool, BaseToolkit
from lexio_rent import Lexio
from pydantic import ConfigDict, Field, SecretStr

from langchain_lexio.tools import (
    LexioCheckAvailabilityTool,
    LexioCreateQuoteTool,
    LexioFindCustomerTool,
    LexioGetRentalTool,
    LexioListCategoriesTool,
    LexioListRentalsTool,
    LexioSearchVehiclesTool,
)

READ_TOOLS = (
    LexioSearchVehiclesTool,
    LexioCheckAvailabilityTool,
    LexioListRentalsTool,
    LexioGetRentalTool,
    LexioFindCustomerTool,
    LexioListCategoriesTool,
)


class LexioToolkit(BaseToolkit):
    """Lexio Rent tools for agents.

    Read-only by default: fleet, availability and prices, rentals, customers and
    categories. ``allow_quotes=True`` adds ``lexio_create_quote``, which writes a
    quote record but books nothing. Rentals, payments and customer records are
    never created or changed by this toolkit.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    api_key: Optional[SecretStr] = Field(
        default_factory=secret_from_env("LEXIO_API_KEY", default=None),
        description="Lexio API key (lck_...). Defaults to LEXIO_API_KEY.",
    )
    base_url: Optional[str] = None
    max_results: int = 20
    allow_quotes: bool = False
    client: Optional[Any] = Field(default=None, exclude=True)

    def _client(self) -> Lexio:
        if self.client is None:
            key = self.api_key.get_secret_value() if self.api_key else os.environ.get("LEXIO_API_KEY")
            self.client = Lexio(api_key=key, base_url=self.base_url)
        return self.client

    def get_tools(self) -> list[BaseTool]:
        client = self._client()
        classes = list(READ_TOOLS) + ([LexioCreateQuoteTool] if self.allow_quotes else [])
        return [cls(client=client, max_results=self.max_results) for cls in classes]
