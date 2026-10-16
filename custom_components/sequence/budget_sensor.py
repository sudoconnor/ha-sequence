"""Household spend sensors computed from Sequence.

Object ids use the ``hs2_`` prefix so these entities can run beside the
existing MQTT household-spend sensors.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .budget import (
    STATUS_THRESHOLDS,
    WeeklyBudgetSnapshot,
    balance_attributes,
    breakdown_attributes,
    transactions_attributes,
    weekly_spend_attributes,
)
from .budget_coordinator import WeeklyBudgetDataUpdateCoordinator
from .const import DOMAIN
from .coordinator import SequenceDataUpdateCoordinator


@dataclass(frozen=True, slots=True)
class _SensorSpec:
    """Static description of one weekly-budget sensor."""

    object_id: str
    name: str
    icon: str
    value: Callable[[WeeklyBudgetSnapshot], Any]
    attributes: Callable[[WeeklyBudgetSnapshot], dict[str, Any]] | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    unit: str | None = None
    precision: int | None = None
    options: list[str] | None = None
    unrecorded: frozenset[str] = frozenset()


def _money(field: str) -> Callable[[WeeklyBudgetSnapshot], Any]:
    def _read(snapshot: WeeklyBudgetSnapshot) -> Any:
        return getattr(snapshot, field)

    return _read


_SPECS: tuple[_SensorSpec, ...] = (
    _SensorSpec(
        object_id="hs2_balance",
        name="HS2 Balance",
        icon="mdi:wallet",
        value=_money("balance"),
        attributes=balance_attributes,
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        unit="USD",
        precision=2,
    ),
    _SensorSpec(
        object_id="hs2_weekly_spend",
        name="HS2 Weekly Spend",
        icon="mdi:cash-minus",
        value=_money("spent_incl_pending"),
        attributes=weekly_spend_attributes,
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        unit="USD",
        precision=2,
    ),
    _SensorSpec(
        object_id="hs2_spent_settled",
        name="HS2 Spent Settled",
        icon="mdi:receipt-text-check",
        value=_money("spent_settled"),
        attributes=lambda snapshot: {"transaction_count": snapshot.transaction_count},
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        unit="USD",
        precision=2,
    ),
    _SensorSpec(
        object_id="hs2_pending",
        name="HS2 Pending",
        icon="mdi:clock-outline",
        value=_money("pending"),
        attributes=lambda snapshot: {
            "spent_incl_pending": snapshot.spent_incl_pending,
            "spent_settled": snapshot.spent_settled,
        },
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        unit="USD",
        precision=2,
    ),
    _SensorSpec(
        object_id="hs2_top_ups",
        name="HS2 Top Ups",
        icon="mdi:cash-plus",
        value=_money("top_ups"),
        attributes=lambda snapshot: {
            "top_up_count": snapshot.top_up_count,
            "refill_amount": snapshot.refill_amount,
            "refill_excluded": snapshot.refill_excluded,
            "pending_incoming": snapshot.pending_incoming,
        },
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        unit="USD",
        precision=2,
    ),
    _SensorSpec(
        object_id="hs2_remaining_percent",
        name="HS2 Remaining Percent",
        icon="mdi:percent",
        value=_money("percent"),
        attributes=lambda snapshot: {
            "ratio": snapshot.ratio,
            "status": snapshot.status,
            "balance": snapshot.balance,
            "budget": snapshot.budget,
        },
        state_class=SensorStateClass.MEASUREMENT,
        unit="%",
        precision=1,
    ),
    _SensorSpec(
        object_id="hs2_status",
        name="HS2 Status",
        icon="mdi:heart-pulse",
        value=_money("status"),
        attributes=lambda snapshot: {
            "percent": snapshot.percent,
            "ratio": snapshot.ratio,
            "thresholds": STATUS_THRESHOLDS,
        },
        device_class=SensorDeviceClass.ENUM,
        options=["Critical", "Low", "Healthy"],
    ),
    _SensorSpec(
        object_id="hs2_days_until_refill",
        name="HS2 Days Until Refill",
        icon="mdi:calendar-clock",
        value=_money("days_until_refill"),
        attributes=lambda snapshot: {
            "cycle_start": snapshot.cycle_start.isoformat(),
            "next_refill": snapshot.next_refill.isoformat(),
            "days_elapsed": snapshot.days_elapsed,
        },
        state_class=SensorStateClass.MEASUREMENT,
        unit=UnitOfTime.DAYS,
        precision=2,
    ),
    _SensorSpec(
        object_id="hs2_next_refill",
        name="HS2 Next Refill",
        icon="mdi:calendar-refresh",
        value=_money("next_refill"),
        attributes=lambda snapshot: {
            "refill_weekday": snapshot.refill_weekday,
            "cycle_start": snapshot.cycle_start.isoformat(),
        },
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    _SensorSpec(
        object_id="hs2_last_sync",
        name="HS2 Last Sync",
        icon="mdi:update",
        value=_money("last_sync"),
        attributes=lambda snapshot: {"history_truncated": snapshot.history_truncated},
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    _SensorSpec(
        object_id="hs2_burn_rate",
        name="HS2 Burn Rate",
        icon="mdi:speedometer",
        value=_money("burn_rate"),
        attributes=lambda snapshot: {
            "days_elapsed": snapshot.days_elapsed,
            "safe_daily_allowance": snapshot.safe_daily_allowance,
            "spent_incl_pending": snapshot.spent_incl_pending,
            "basis": "spent_incl_pending_per_elapsed_day",
        },
        state_class=SensorStateClass.MEASUREMENT,
        unit="USD/day",
        precision=2,
    ),
    _SensorSpec(
        object_id="hs2_average_transaction",
        name="HS2 Average Transaction",
        icon="mdi:calculator",
        value=_money("average_transaction"),
        attributes=lambda snapshot: {"purchase_count": snapshot.purchase_count},
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        unit="USD",
        precision=2,
    ),
    _SensorSpec(
        object_id="hs2_median_transaction",
        name="HS2 Median Transaction",
        icon="mdi:approximately-equal",
        value=_money("median_transaction"),
        attributes=lambda snapshot: {"purchase_count": snapshot.purchase_count},
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        unit="USD",
        precision=2,
    ),
    _SensorSpec(
        object_id="hs2_largest_transaction",
        name="HS2 Largest Transaction",
        icon="mdi:arrow-expand-up",
        value=_money("largest_transaction"),
        attributes=lambda snapshot: {"purchase_count": snapshot.purchase_count},
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        unit="USD",
        precision=2,
    ),
    _SensorSpec(
        object_id="hs2_top_merchant",
        name="HS2 Top Merchant",
        icon="mdi:store",
        value=_money("top_merchant"),
        attributes=lambda snapshot: {
            "spent": snapshot.top_merchant_spent,
            "count": snapshot.top_merchant_count,
        },
    ),
    _SensorSpec(
        object_id="hs2_transactions",
        name="HS2 Transactions",
        icon="mdi:format-list-bulleted",
        value=_money("transaction_count"),
        attributes=transactions_attributes,
        state_class=SensorStateClass.MEASUREMENT,
        unrecorded=frozenset({"transactions"}),
    ),
    _SensorSpec(
        object_id="hs2_breakdown",
        name="HS2 Breakdown",
        icon="mdi:chart-donut",
        value=_money("top_merchant"),
        attributes=breakdown_attributes,
        unrecorded=frozenset({"daily", "merchants"}),
    ),
)


def async_add_budget_sensors(
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add weekly budget sensors when the feature is configured."""

    coordinator: SequenceDataUpdateCoordinator = entry.runtime_data
    budget: WeeklyBudgetDataUpdateCoordinator | None = coordinator.weekly_budget
    if budget is None:
        return
    async_add_entities([HouseholdSpendSensor(budget, entry, spec) for spec in _SPECS])


class HouseholdSpendSensor(CoordinatorEntity[WeeklyBudgetDataUpdateCoordinator], SensorEntity):
    """One weekly-budget metric."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: WeeklyBudgetDataUpdateCoordinator,
        entry: ConfigEntry,
        spec: _SensorSpec,
    ) -> None:
        """Initialize the sensor."""

        super().__init__(coordinator)
        self._spec = spec
        self._attr_unique_id = f"{entry.entry_id}_{spec.object_id}"
        self._attr_suggested_object_id = spec.object_id
        self._attr_name = spec.name
        self._attr_icon = spec.icon
        self._attr_device_class = spec.device_class
        self._attr_state_class = spec.state_class
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_suggested_display_precision = spec.precision
        if spec.options is not None:
            self._attr_options = spec.options
        self._unrecorded_attributes = spec.unrecorded
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_weekly_budget")},
            "manufacturer": "Sequence",
            "model": "Weekly budget",
            "name": "Sequence Weekly Budget",
        }

    @property
    def native_value(self) -> Any:
        """Return the sensor state."""

        snapshot = self.coordinator.data
        if snapshot is None:
            return None
        return self._spec.value(snapshot)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the currency for monetary sensors."""

        if self._spec.device_class == SensorDeviceClass.MONETARY and self._spec.unit == "USD":
            snapshot = self.coordinator.data
            if snapshot is not None and snapshot.currency:
                return snapshot.currency
        return self._attr_native_unit_of_measurement

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes. Large lists live on their own sensors."""

        snapshot = self.coordinator.data
        if snapshot is None or self._spec.attributes is None:
            return {}
        return self._spec.attributes(snapshot)
