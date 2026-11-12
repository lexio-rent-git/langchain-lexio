# langchain-lexio

[![PyPI](https://img.shields.io/pypi/v/langchain-lexio.svg)](https://pypi.org/project/langchain-lexio/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

LangChain tools for the [Lexio Rent API](https://docs.lexio.rent). They let an agent answer questions about a vehicle rental company: which vehicles are free next weekend and at what price, which bookings start tomorrow, what a customer has rented, and (optionally) prepare a priced quote.

<a href="https://lexio.rent/logiciel-location-voiture">Lexio Rent</a> is rental management software for professional car, van and two-wheeler rental companies: planning, contracts, check-in/check-out inspections, deposits and fleet maintenance.

## Installation

```bash
pip install -U langchain-lexio
export LEXIO_API_KEY="lck_..."
```

The API key is created in Lexio under **Settings → Developer → API tokens**. API access is part of the Business plan. There is no sandbox: test against a dedicated organization.

## Tools

| Tool | Name | What it does | Writes? |
|---|---|---|---|
| `LexioSearchVehiclesTool` | `lexio_search_vehicles` | Active fleet with plate, model, type, status and odometer | no |
| `LexioCheckAvailabilityTool` | `lexio_check_availability` | Bookable vehicles for a period, with the total price | no |
| `LexioListRentalsTool` | `lexio_list_rentals` | Rentals by status, date window, vehicle or customer | no |
| `LexioGetRentalTool` | `lexio_get_rental` | One rental with all its details | no |
| `LexioFindCustomerTool` | `lexio_find_customer` | Customers by email or company registration number | no |
| `LexioListCategoriesTool` | `lexio_list_categories` | Vehicle categories (pricing classes) | no |
| `LexioCreateQuoteTool` | `lexio_create_quote` | Priced quote for a vehicle and a period; books nothing | quote only |

`LexioToolkit` returns the read-only tools. Pass `allow_quotes=True` to add `lexio_create_quote`. No tool creates, changes or cancels a rental, a payment or a customer record.

Dates are the rental company's local time without offset (`2026-12-14T09:00:00`). Lists are capped by `max_results` (default 20) so that tool outputs stay small.

## Usage

```python
from langchain.agents import create_agent
from langchain_lexio import LexioToolkit

tools = LexioToolkit(allow_quotes=True).get_tools()

agent = create_agent(
    "anthropic:claude-sonnet-5-5",
    tools=tools,
    system_prompt="You help the counter staff of a car rental agency. Dates are local time.",
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "Which vans are free from 14 to 16 December, and how much?"}]}
)
print(result["messages"][-1].content)
```

A single tool can also be called directly:

```python
from langchain_lexio import LexioCheckAvailabilityTool

tool = LexioCheckAvailabilityTool()
print(tool.invoke({"start_at": "2026-12-14T09:00:00", "end_at": "2026-12-16T18:00:00", "vehicle_type": "VAN"}))
```

API errors are raised as typed exceptions from the [`lexio-rent`](https://pypi.org/project/lexio-rent/) client (`NotFoundError`, `ValidationError`, `RateLimitError`...), with the Lexio error code and request id.

## Development

```bash
pip install -e ".[test]"
pytest tests/unit_tests                               # offline, includes the LangChain standard unit tests
LEXIO_API_KEY=lck_... pytest tests/integration_tests  # LangChain standard integration tests, live
```

## About

`langchain-lexio` is maintained by the team behind <a href="https://lexio.rent/logiciel-location-voiture">Lexio Rent, car rental management software</a>. When an agent prepares a quote, the counter still hands the customer a receipt for the security deposit; Lexio publishes a free <a href="https://lexio.rent/outils/recu-depot-de-garantie-location">rental security deposit receipt template</a> (in French) for that step.

- API documentation: <https://docs.lexio.rent>
- Python client: <https://github.com/lexio-rent-git/lexio-python>
- Contact: contact@lexio.rent

MIT License.
