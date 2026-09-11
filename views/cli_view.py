"""
CLI Dashboard View for HLK-LD2450 mmWave Radar using Rich.

Renders real-time formatted console tables showing detected targets,
spatial coordinates, radial velocities, distances, and active zone occupancy.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.ld2450_parser import RadarFrame, Target
from core.zone_manager import ZoneManager


class CLIView:
    """Rich-based terminal UI for live tracking visualization."""

    def __init__(self, zone_manager: Optional[ZoneManager] = None) -> None:
        self.console = Console()
        self.zone_manager = zone_manager
        self.live: Optional[Live] = None
        self._start_time = time.time()
        self._frame_count = 0
        self._last_fps_time = time.time()
        self._fps = 0.0

    def start(self) -> None:
        """Starts the live rich display context."""
        self.live = Live(
            console=self.console,
            screen=False,
            auto_refresh=False,
            transient=True,
        )
        self.live.start()

    def stop(self) -> None:
        """Stops the live display context."""
        if self.live:
            self.live.stop()
            self.live = None

    def _compute_fps(self) -> float:
        self._frame_count += 1
        now = time.time()
        elapsed = now - self._last_fps_time
        if elapsed >= 1.0:
            self._fps = self._frame_count / elapsed
            self._frame_count = 0
            self._last_fps_time = now
        return self._fps

    def _generate_target_table(
        self, targets: List[Target], occupancy: Dict[str, List[Target]]
    ) -> Table:
        table = Table(
            title="🎯 Tracked Radar Targets",
            title_style="bold cyan",
            expand=True,
            header_style="bold magenta",
        )
        table.add_column("ID", justify="center", style="bold yellow", width=4)
        table.add_column("Status", justify="center", width=10)
        table.add_column("X (m)", justify="right", width=9)
        table.add_column("Y (m)", justify="right", width=9)
        table.add_column("Distance (m)", justify="right", width=12)
        table.add_column("Angle (°)", justify="right", width=10)
        table.add_column("Speed (m/s)", justify="right", width=12)
        table.add_column("Resolution (mm)", justify="right", width=15)
        table.add_column("Occupied Zones", justify="left")

        for target in targets:
            if target.is_valid:
                status_text = Text("DETECTED", style="bold green")
                x_str = f"{target.x_m:+.2f}"
                y_str = f"{target.y_m:.2f}"
                dist_str = f"{target.distance_mm / 1000.0:.2f}"
                angle_str = f"{target.angle_deg:+.1f}°"

                # Speed styling: negative (approaching) vs positive (departing)
                speed_val = target.speed_ms
                if speed_val > 0.05:
                    speed_style = "bold cyan"
                    speed_symbol = "↗ "
                elif speed_val < -0.05:
                    speed_style = "bold red"
                    speed_symbol = "↙ "
                else:
                    speed_style = "dim"
                    speed_symbol = "• "
                speed_text = Text(f"{speed_symbol}{speed_val:+.2f}", style=speed_style)

                # Find occupied zones for this target
                in_zones = [
                    z_name for z_name, z_targets in occupancy.items()
                    if any(t.id == target.id for t in z_targets)
                ]
                zone_str = ", ".join(in_zones) if in_zones else Text("None", style="dim")
                res_str = str(target.distance_resolution_mm)

                table.add_row(
                    str(target.id),
                    status_text,
                    x_str,
                    y_str,
                    dist_str,
                    angle_str,
                    speed_text,
                    res_str,
                    zone_str,
                )
            else:
                table.add_row(
                    str(target.id),
                    Text("NO TARGET", style="dim"),
                    "—",
                    "—",
                    "—",
                    "—",
                    "—",
                    "—",
                    Text("—", style="dim"),
                )

        return table

    def _generate_zone_table(self, occupancy: Dict[str, List[Target]]) -> Table:
        table = Table(
            title="📍 Geofence Zones Occupancy",
            title_style="bold green",
            expand=True,
            header_style="bold blue",
        )
        table.add_column("Zone Name", style="bold")
        table.add_column("X Bounds [m]", justify="center")
        table.add_column("Y Bounds [m]", justify="center")
        table.add_column("Status", justify="center")
        table.add_column("Target Count", justify="center")
        table.add_column("Target IDs", justify="center")

        if not self.zone_manager or not self.zone_manager.zones:
            table.add_row("No zones configured", "—", "—", "—", "0", "None")
            return table

        for zone in self.zone_manager.zones:
            targets_in_zone = occupancy.get(zone.name, [])
            count = len(targets_in_zone)
            if count > 0:
                status = Text("OCCUPIED", style="bold red")
                ids = ", ".join(str(t.id) for t in targets_in_zone)
            else:
                status = Text("VACANT", style="dim green")
                ids = "—"

            x_bounds = f"[{zone.x_min/1000:+.2f}, {zone.x_max/1000:+.2f}]"
            y_bounds = f"[{zone.y_min/1000:.2f}, {zone.y_max/1000:.2f}]"

            table.add_row(zone.name, x_bounds, y_bounds, status, str(count), ids)

        return table

    def update(
        self,
        frame: RadarFrame,
        occupancy: Dict[str, List[Target]],
        stats: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Updates the live console dashboard with new radar frame data.
        """
        fps = self._compute_fps()
        stats_info = stats or {}
        transport_type = stats_info.get("transport_type", "Serial")
        packets_total = stats_info.get("packet_count", 0)

        header_text = Text.assemble(
            ("HLK-LD2450 mmWave Radar System  |  ", "bold white"),
            (f"Transport: {transport_type}  |  ", "cyan"),
            (f"Rate: {fps:.1f} FPS  |  ", "yellow"),
            (f"Packets: {packets_total}  |  ", "green"),
            (f"Active Targets: {len(frame.valid_targets)}", "bold magenta"),
        )
        header_panel = Panel(header_text, style="blue")

        target_table = self._generate_target_table(frame.targets, occupancy)
        zone_table = self._generate_zone_table(occupancy)

        render_group = Group(header_panel, target_table, zone_table)

        if self.live:
            self.live.update(render_group, refresh=True)
        else:
            self.console.clear()
            self.console.print(render_group)
