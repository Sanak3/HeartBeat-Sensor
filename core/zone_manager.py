"""
Zone Manager for Spatial Tracking and Geofencing.

Allows configuring Axis-Aligned Bounding Boxes (AABB) in the 2D Cartesian plane
(X, Y in millimeters relative to the sensor origin) to detect occupancy and trigger zone events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from core.ld2450_parser import Target


@dataclass
class Zone:
    """Represents a 2D Axis-Aligned Bounding Box (AABB) zone in millimeters."""
    name: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    color: str = "#3498db"
    alert_level: str = "info"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def contains_point(self, x_mm: float, y_mm: float) -> bool:
        """Checks if a given coordinate is located inside this zone's bounds."""
        return (self.x_min <= x_mm <= self.x_max) and (self.y_min <= y_mm <= self.y_max)

    def contains(self, target: Target) -> bool:
        """Checks if a target is within the zone bounding box."""
        if not target.is_valid:
            return False
        return self.contains_point(target.x_mm, target.y_mm)

    @property
    def width_m(self) -> float:
        """Width in meters along X axis."""
        return abs(self.x_max - self.x_min) / 1000.0

    @property
    def height_m(self) -> float:
        """Height/depth in meters along Y axis."""
        return abs(self.y_max - self.y_min) / 1000.0


class ZoneManager:
    """Manages collection of spatial zones and evaluates target occupancy."""

    def __init__(self, zones: Optional[List[Zone]] = None) -> None:
        self.zones: List[Zone] = zones or []
        self._last_occupancy: Dict[str, List[int]] = {}  # zone_name -> list of target_ids

    @classmethod
    def from_config(cls, zone_configs: List[Dict[str, Any]]) -> "ZoneManager":
        """Instantiates ZoneManager from a configuration list of dictionaries."""
        zones = [
            Zone(
                name=z.get("name", f"Zone_{i+1}"),
                x_min=float(z.get("x_min", 0)),
                x_max=float(z.get("x_max", 0)),
                y_min=float(z.get("y_min", 0)),
                y_max=float(z.get("y_max", 0)),
                color=z.get("color", "#3498db"),
                alert_level=z.get("alert_level", "info"),
                metadata=z.get("metadata", {}),
            )
            for i, z in enumerate(zone_configs)
        ]
        return cls(zones=zones)

    def add_zone(self, zone: Zone) -> None:
        """Registers a new zone."""
        self.zones.append(zone)

    def get_zones_for_target(self, target: Target) -> List[Zone]:
        """Returns all zones currently containing the target."""
        if not target.is_valid:
            return []
        return [zone for zone in self.zones if zone.contains(target)]

    def evaluate_occupancy(self, targets: List[Target]) -> Dict[str, List[Target]]:
        """
        Evaluates active targets against all registered zones.

        :param targets: List of active Target objects.
        :return: Dictionary mapping zone names to lists of targets inside that zone.
        """
        valid_targets = [t for t in targets if t.is_valid]
        occupancy: Dict[str, List[Target]] = {zone.name: [] for zone in self.zones}

        for target in valid_targets:
            for zone in self.zones:
                if zone.contains(target):
                    occupancy[zone.name].append(target)

        return occupancy
