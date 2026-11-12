"""LangChain tools for the Lexio Rent API (car and van rental management software)."""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.utils import secret_from_env
from langchain_core.tools import BaseTool
from lexio_rent import Lexio
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, SecretStr

VEHICLE_TYPES = "CITY, COMPACT, CROSSOVER, SEDAN, BREAK, SUV, OFF_ROAD, PICKUP, MINIVAN, VAN, UTILITY, COUPE, CONVERTIBLE, SPORT, LUXURY, MOTORCYCLE, SCOOTER"
RENTAL_STATUSES = "PENDING_APPROVAL, RESERVED, IN_PROGRESS, COMPLETED, CANCELLED"
LOCAL_TIME = "Local date-time of the rental company, without offset, e.g. 2026-12-14T09:00:00."


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _pick(obj: Optional[dict], *keys: str) -> Optional[dict]:
    if not isinstance(obj, dict):
        return obj
    return {k: obj.get(k) for k in keys if k in obj}


class LexioBaseTool(BaseTool):
    """Shared settings: API key (``LEXIO_API_KEY``), base URL and client."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    api_key: Optional[SecretStr] = Field(
        default_factory=secret_from_env("LEXIO_API_KEY", default=None),
        description="Lexio API key (lck_...). Defaults to LEXIO_API_KEY.",
    )
    base_url: Optional[str] = Field(default=None, description="API base URL. Defaults to LEXIO_BASE_URL or production.")
    max_results: int = Field(default=20, description="Upper bound on items returned to the model.")
    client: Optional[Any] = Field(default=None, exclude=True, description="Optional shared lexio_rent.Lexio client.")
    _own_client: Optional[Lexio] = PrivateAttr(default=None)

    def _lexio(self) -> Lexio:
        if self.client is not None:
            return self.client
        if self._own_client is None:
            key = self.api_key.get_secret_value() if self.api_key else os.environ.get("LEXIO_API_KEY")
            self._own_client = Lexio(api_key=key, base_url=self.base_url)
        return self._own_client

    def _list(self, method: Any, limit: Optional[int], **filters: Any) -> list:
        cap = min(limit or self.max_results, self.max_results)
        out = []
        for item in self._lexio().paginate(method, limit=min(cap, 100), **filters):
            out.append(item)
            if len(out) >= cap:
                break
        return out


# --- search vehicles -------------------------------------------------------

class SearchVehiclesInput(BaseModel):
    category_id: Optional[str] = Field(default=None, description="Only vehicles of this category id.")
    vehicle_type: Optional[str] = Field(default=None, description="Vehicle type, one of: " + VEHICLE_TYPES + ".")
    status: Optional[str] = Field(default=None, description="OPERATIONAL or BREAKDOWN.")
    limit: Optional[int] = Field(default=None, description="Maximum number of vehicles to return.")


class LexioSearchVehiclesTool(LexioBaseTool):
    """List the active fleet of the rental company."""

    name: str = "lexio_search_vehicles"
    description: str = (
        "List vehicles of the rental company fleet (active, not archived) with plate, model, category, "
        "status and odometer. Use it to find a vehicle id."
    )
    args_schema: type[BaseModel] = SearchVehiclesInput

    def _run(
        self,
        category_id: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        items = self._list(
            self._lexio().vehicles.list,
            limit,
            is_archived=False,
            category_id=category_id,
            vehicle_type=vehicle_type,
            status=status,
        )
        keys = ("id", "plate", "name", "brand", "model", "vehicleType", "status", "odometerKm", "category")
        return _dump([_pick(v, *keys) for v in items])


# --- availability ----------------------------------------------------------

class CheckAvailabilityInput(BaseModel):
    start_at: str = Field(description="Pick-up. " + LOCAL_TIME)
    end_at: str = Field(description="Return. " + LOCAL_TIME)
    category_id: Optional[str] = Field(default=None, description="Only this category id.")
    vehicle_type: Optional[str] = Field(default=None, description="Vehicle type, one of: " + VEHICLE_TYPES + ".")
    only_available: bool = Field(default=True, description="True: bookable vehicles only. False: the others, with reasons.")
    limit: Optional[int] = Field(default=None, description="Maximum number of offers to return.")


class LexioCheckAvailabilityTool(LexioBaseTool):
    """Bookable vehicles and their price for a period."""

    name: str = "lexio_check_availability"
    description: str = (
        "Check which vehicles can be booked for a period and their total price (tax included, with the default "
        "mileage package, excess and deposit). Prices are indicative; only a quote fixes the price."
    )
    args_schema: type[BaseModel] = CheckAvailabilityInput

    def _run(
        self,
        start_at: str,
        end_at: str,
        category_id: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        only_available: bool = True,
        limit: Optional[int] = None,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        offers = self._list(
            self._lexio().availability.list,
            limit,
            start_at=start_at,
            end_at=end_at,
            category_id=category_id,
            vehicle_type=vehicle_type,
            is_available=only_available,
        )
        out = []
        for o in offers:
            out.append(
                {
                    "vehicle": _pick(o.get("vehicle"), "id", "name", "brand", "model", "plate", "vehicleType"),
                    "isAvailable": o.get("isAvailable"),
                    "unavailableReasons": o.get("unavailableReasons"),
                    "billedDays": (o.get("period") or {}).get("billedDays"),
                    "currency": o.get("currency"),
                    "totalTTC": o.get("totalTTC"),
                    "mileage": _pick(o.get("mileage"), "name", "isUnlimited", "includedKm"),
                }
            )
        return _dump(out)


# --- rentals ---------------------------------------------------------------

class ListRentalsInput(BaseModel):
    status: Optional[str] = Field(default=None, description=f"Comma-separated statuses: {RENTAL_STATUSES}.")
    from_date: Optional[str] = Field(default=None, description="First day (YYYY-MM-DD) of the window, included.")
    to_date: Optional[str] = Field(default=None, description="Last day (YYYY-MM-DD) of the window, included.")
    vehicle_id: Optional[str] = Field(default=None, description="Only rentals of this vehicle id.")
    customer_id: Optional[str] = Field(default=None, description="Only rentals of this customer id.")
    limit: Optional[int] = Field(default=None, description="Maximum number of rentals to return.")


class LexioListRentalsTool(LexioBaseTool):
    """Search rentals (bookings)."""

    name: str = "lexio_list_rentals"
    description: str = (
        "Search rentals (bookings) by status, date window, vehicle or customer. Returns number, status, period, "
        "vehicle, customer and totals. Without status, cancelled rentals are included."
    )
    args_schema: type[BaseModel] = ListRentalsInput

    def _run(
        self,
        status: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        vehicle_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        limit: Optional[int] = None,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        items = self._list(
            self._lexio().rentals.list,
            limit,
            status=status,
            from_=from_date,
            to=to_date,
            vehicle_id=vehicle_id,
            customer_id=customer_id,
        )
        return _dump([_compact_rental(r) for r in items])


def _compact_rental(r: dict) -> dict:
    return {
        "id": r.get("id"),
        "number": r.get("number"),
        "status": r.get("status"),
        "period": _pick(r.get("period"), "startAt", "endAt", "timezone"),
        "vehicle": _pick(r.get("vehicle"), "id", "name", "plate"),
        "customer": _pick(r.get("customer"), "id", "firstName", "lastName", "companyName", "email"),
        "currency": r.get("currency"),
        "totalTTC": r.get("totalTTC"),
        "balance": r.get("balance"),
    }


class GetRentalInput(BaseModel):
    rental_id: str = Field(description="Rental id (UUID).")


class LexioGetRentalTool(LexioBaseTool):
    """One rental with all its details."""

    name: str = "lexio_get_rental"
    description: str = (
        "Get one rental by id with all details: period, actual pick-up and return, vehicle, customer, locations, "
        "mileage package, excess, deposit, options, price lines, balance and notes."
    )
    args_schema: type[BaseModel] = GetRentalInput

    def _run(self, rental_id: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        return _dump(self._lexio().rentals.get(rental_id)["data"])


# --- customers -------------------------------------------------------------

class FindCustomerInput(BaseModel):
    email: Optional[str] = Field(default=None, description="Exact email address of the customer.")
    company_registration_number: Optional[str] = Field(default=None, description="Company registration number (business customers).")
    limit: Optional[int] = Field(default=None, description="Maximum number of customers to return.")


class LexioFindCustomerTool(LexioBaseTool):
    """Find customers by email or company registration number."""

    name: str = "lexio_find_customer"
    description: str = "Find customers of the rental company by exact email or company registration number."
    args_schema: type[BaseModel] = FindCustomerInput

    def _run(
        self,
        email: Optional[str] = None,
        company_registration_number: Optional[str] = None,
        limit: Optional[int] = None,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        items = self._list(
            self._lexio().customers.list, limit, email=email, company_registration_number=company_registration_number
        )
        return _dump(items)


# --- catalogue -------------------------------------------------------------

class ListCategoriesInput(BaseModel):
    limit: Optional[int] = Field(default=None, description="Maximum number of categories to return.")


class LexioListCategoriesTool(LexioBaseTool):
    """Vehicle categories (pricing classes)."""

    name: str = "lexio_list_categories"
    description: str = "List the vehicle categories (pricing classes) of the rental company, with their ids."
    args_schema: type[BaseModel] = ListCategoriesInput

    def _run(self, limit: Optional[int] = None, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        return _dump(self._list(self._lexio().categories.list, limit))


# --- quote (write, opt-in) -------------------------------------------------

class CreateQuoteInput(BaseModel):
    vehicle_id: str = Field(description="Vehicle id, from lexio_check_availability.")
    start_at: str = Field(description="Pick-up. " + LOCAL_TIME)
    end_at: str = Field(description="Return. " + LOCAL_TIME)
    mileage_package_id: Optional[str] = Field(default=None, description="Mileage package id; default package if omitted.")
    deductible_id: Optional[str] = Field(default=None, description="Excess (deductible) id; default if omitted.")
    deposit_id: Optional[str] = Field(default=None, description="Deposit id; default if omitted.")
    promo_code: Optional[str] = Field(default=None, description="Promo code, if the customer has one.")


class LexioCreateQuoteTool(LexioBaseTool):
    """Create a priced quote (writes to Lexio, books nothing)."""

    name: str = "lexio_create_quote"
    description: str = (
        "Create a quote that fixes the price of a vehicle for a period. It writes a quote record in Lexio but does "
        "not book the vehicle. Returns the quote id, total and expiry."
    )
    args_schema: type[BaseModel] = CreateQuoteInput

    def _run(
        self,
        vehicle_id: str,
        start_at: str,
        end_at: str,
        mileage_package_id: Optional[str] = None,
        deductible_id: Optional[str] = None,
        deposit_id: Optional[str] = None,
        promo_code: Optional[str] = None,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        body = {"vehicleId": vehicle_id, "startAt": start_at, "endAt": end_at}
        optional = {
            "mileagePackageId": mileage_package_id,
            "deductibleId": deductible_id,
            "depositId": deposit_id,
            "promoCode": promo_code,
        }
        body.update({k: v for k, v in optional.items() if v is not None})
        return _dump(self._lexio().quotes.create(body)["data"])
