"""
2D Real-time Cartesian Radar Plot View using Matplotlib.

Visualizes radar sensor field-of-view (FOV), spatial geofence zones (AABB),
and active moving targets with velocity vectors and trail history.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import matplotlib.patches as patches
import matplotlib.pyplot as plt

from core.ld2450_parser import RadarFrame, Target
from core.zone_manager import ZoneManager


class PlotView:
    """Real-time 2D Matplotlib graphical visualization for radar tracking."""

    TARGET_COLORS = ["#e74c3c", "#f39c12", "#2ecc71"]

    def __init__(
        self,
        zone_manager: Optional[ZoneManager] = None,
        max_distance_m: float = 6.0,
        fov_deg: float = 120.0,
    ) -> None:
        self.zone_manager = zone_manager
        self.max_distance_m = max_distance_m
        self.fov_deg = fov_deg

        # Matplotlib figure & axes setup
        plt.ion()
        self.fig, self.ax = plt.subplots(figsize=(9, 8))
        self.fig.canvas.manager.set_window_title("HLK-LD2450 mmWave Radar - 2D Spatial Tracker")

        # Visual elements cache
        self.zone_patches: Dict[str, patches.Rectangle] = {}
        self.zone_texts: Dict[str, plt.Text] = {}
        self.target_scatters: List[Any] = []
        self.target_annotations: List[plt.Text] = []
        self.target_quivers: List[Any] = []

        self._init_canvas()

    def _init_canvas(self) -> None:
        """Draws static radar geometry, coordinate axes, and FOV lines."""
        self.ax.set_facecolor("#1e1e2f")
        self.fig.patch.set_facecolor("#12121c")

        max_x = self.max_distance_m * math.sin(math.radians(self.fov_deg / 2.0)) * 1.15
        max_y = self.max_distance_m * 1.1

        self.ax.set_xlim(-max_x, max_x)
        self.ax.set_ylim(-0.5, max_y)
        self.ax.set_aspect("equal", adjustable="box")
        self.ax.set_xlabel("X - Lateral Position (meters)", color="#cccccc", fontsize=11)
        self.ax.set_ylabel("Y - Distance (meters)", color="#cccccc", fontsize=11)
        self.ax.tick_params(colors="#aaaaaa")
        self.ax.grid(True, linestyle="--", alpha=0.3, color="#888888")

        # Draw Sensor icon/point at (0, 0)
        self.ax.plot(0, 0, marker="^", markersize=14, color="#00ffcc", label="Radar Origin (0,0)")
        self.ax.text(0, -0.35, "SENSOR", color="#00ffcc", ha="center", fontsize=9, fontweight="bold")

        # Draw FOV arc lines
        half_fov = math.radians(self.fov_deg / 2.0)
        fov_left_x = -self.max_distance_m * math.sin(half_fov)
        fov_right_x = self.max_distance_m * math.sin(half_fov)
        fov_y = self.max_distance_m * math.cos(half_fov)

        self.ax.plot([0, fov_left_x], [0, fov_y], color="#555577", linestyle=":", linewidth=1.5)
        self.ax.plot([0, fov_right_x], [0, fov_y], color="#555577", linestyle=":", linewidth=1.5)

        # Draw concentric distance rings
        for r in range(1, int(self.max_distance_m) + 1):
            arc = patches.Arc(
                (0, 0),
                2 * r,
                2 * r,
                angle=90,
                theta1=-self.fov_deg / 2.0,
                theta2=self.fov_deg / 2.0,
                color="#444466",
                linestyle="--",
                linewidth=0.8,
            )
            self.ax.add_patch(arc)
            self.ax.text(0.05, r, f"{r}m", color="#777799", fontsize=8, alpha=0.7)

        # Draw static geofence zones
        if self.zone_manager:
            for zone in self.zone_manager.zones:
                rect = patches.Rectangle(
                    (zone.x_min / 1000.0, zone.y_min / 1000.0),
                    zone.width_m,
                    zone.height_m,
                    linewidth=2,
                    edgecolor=zone.color,
                    facecolor=zone.color,
                    alpha=0.15,
                    linestyle="--",
                )
                self.ax.add_patch(rect)
                self.zone_patches[zone.name] = rect

                txt = self.ax.text(
                    (zone.x_min + zone.x_max) / 2000.0,
                    (zone.y_min + zone.y_max) / 2000.0,
                    zone.name,
                    color=zone.color,
                    ha="center",
                    va="center",
                    fontsize=9,
                    weight="bold",
                    alpha=0.8,
                )
                self.zone_texts[zone.name] = txt

        self.ax.set_title("HLK-LD2450 Real-Time 2D Tracking", color="#ffffff", fontsize=13, pad=12)

    def update(self, frame: RadarFrame, occupancy: Dict[str, List[Target]]) -> None:
        """
        Refreshes plot with current target positions and zone states.
        """
        # Clear previous target visuals
        for sc in self.target_scatters:
            sc.remove()
        for ann in self.target_annotations:
            ann.remove()
        for q in self.target_quivers:
            q.remove()

        self.target_scatters.clear()
        self.target_annotations.clear()
        self.target_quivers.clear()

        # Update zone highlight styles based on occupancy
        if self.zone_manager:
            for zone in self.zone_manager.zones:
                rect = self.zone_patches.get(zone.name)
                is_occupied = len(occupancy.get(zone.name, [])) > 0
                if rect:
                    if is_occupied:
                        rect.set_facecolor("#ff3333")
                        rect.set_alpha(0.35)
                        rect.set_linestyle("-")
                    else:
                        rect.set_facecolor(zone.color)
                        rect.set_alpha(0.15)
                        rect.set_linestyle("--")

        # Plot active targets
        for idx, target in enumerate(frame.valid_targets):
            color = self.TARGET_COLORS[(target.id - 1) % len(self.TARGET_COLORS)]

            # Target position point
            sc = self.ax.scatter(
                [target.x_m],
                [target.y_m],
                color=color,
                s=120,
                edgecolors="#ffffff",
                linewidth=1.5,
                zorder=5,
            )
            self.target_scatters.append(sc)

            # Target label (ID, Speed, Distance)
            label = f"T{target.id}: {target.distance_mm/1000:.2f}m\n{target.speed_ms:+.1f}m/s"
            ann = self.ax.text(
                target.x_m + 0.1,
                target.y_m + 0.1,
                label,
                color=color,
                fontsize=9,
                fontweight="bold",
                zorder=6,
                bbox=dict(boxstyle="round,pad=0.2", fc="#2a2a3c", ec=color, alpha=0.8),
            )
            self.target_annotations.append(ann)

            # Velocity vector pointing in direction of radial movement
            # LD2450 reports radial speed along line of sight
            if abs(target.speed_ms) > 0.05 and target.distance_mm > 0:
                ux = target.x_m / (target.distance_mm / 1000.0)
                uy = target.y_m / (target.distance_mm / 1000.0)
                vx = ux * (target.speed_ms * 0.4)
                vy = uy * (target.speed_ms * 0.4)
                q = self.ax.quiver(
                    target.x_m,
                    target.y_m,
                    vx,
                    vy,
                    angles="xy",
                    scale_units="xy",
                    scale=1,
                    color=color,
                    width=0.008,
                    zorder=5,
                )
                self.target_quivers.append(q)

        self.fig.canvas.draw_idle()
        plt.pause(0.001)

    def close(self) -> None:
        """Closes the figure window."""
        plt.close(self.fig)
