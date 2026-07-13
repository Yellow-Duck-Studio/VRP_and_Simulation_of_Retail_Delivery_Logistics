"""
Resolves a raw (lat, lon) Location back to the semantic entity id
(warehouse_id / order_id) it belongs to, so that distance-matrix lookups
use the same key scheme the matrix was actually built with.

Why this exists
================
`data_loader.load_simulation_data` builds the DistanceMatrix from
`from_id` / `to_id` pairs (e.g. "WH_PYATEROCHKA_INNOPOLIS" -> "ORD001") -
these are business entity ids, not coordinates.

Everywhere else in the engine (CourierFSM, TripConnectionValidator) only
has a `Location(latitude, longitude)` in hand when it needs a distance,
and was building lookup keys as f"{lat},{lon}".

LocationResolver builds a coordinate -> entity_id index once from
StateManager (warehouses + order delivery locations) and exposes
`matrix_key(location)`, which returns the entity id when the coordinate
is recognized, and falls back to the raw "lat,lon" string otherwise (so
behavior degrades gracefully for locations that aren't tied to a known
warehouse/order, e.g. synthetic waypoints).
"""

from __future__ import annotations

from typing import Dict, Tuple

from .state_manager import StateManager


class LocationResolver:
    def __init__(self, state_manager: StateManager, precision: int = 6):
        self.state_manager = state_manager
        self.precision = precision
        self._coord_to_id: Dict[Tuple[float, float], str] = {}
        self.refresh()

    def refresh(self) -> None:
        """(Re)builds the coordinate -> entity id index from current state.

        Call this if warehouses/orders are added to StateManager after this
        resolver was constructed.
        """
        self._coord_to_id.clear()

        for warehouse in self.state_manager.warehouses.values():
            self._coord_to_id[self._key(warehouse.location)] = warehouse.warehouse_id

        for order in self.state_manager.orders.values():
            delivery_location = getattr(order, "delivery_location", None)
            if delivery_location is not None:
                # Don't let a warehouse entry get silently overwritten by an
                # order that happens to share coordinates with it.
                key = self._key(delivery_location)
                self._coord_to_id.setdefault(key, order.order_id)

    def _key(self, location) -> Tuple[float, float]:
        return round(location.latitude, self.precision), round(location.longitude, self.precision)

    def entity_id(self, location) -> str | None:
        """Returns the known entity id for this location, or None."""
        return self._coord_to_id.get(self._key(location))

    def matrix_key(self, location) -> str:
        """Best-effort key for distance_matrix lookups: entity id if known,
        otherwise a raw 'lat,lon' string (matrix lookup will then almost
        certainly miss and fall back to haversine - which is the correct,
        honest behavior for genuinely unrecognized locations)."""
        entity_id = self.entity_id(location)
        return entity_id if entity_id is not None else f"{location.latitude},{location.longitude}"

    def same_location(self, a, b) -> bool:
        return self._key(a) == self._key(b)