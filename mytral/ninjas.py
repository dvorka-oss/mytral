# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
from mytral import app_logger

"""ninjas ~ (data) classes for Jinja templates w/ visualization metadata and config"""


class HeatmapPaletteNinja:
    """Color palette for heatmaps."""

    BASE_COLOR_GRAY = "gray"
    BASE_COLOR_R = "red"
    BASE_COLOR_G = "green"
    BASE_COLOR_B = "blue"

    def __init__(
        self,
        min_value: float = 0.0,
        max_value: float = 100.0,
        base_color: str = BASE_COLOR_GRAY,
    ) -> None:
        self.base_color = base_color
        self.min_value = min_value
        self.max_value = max_value

    def color(self, value: float) -> str:
        """Get color for value."""
        app_logger.info(
            f"Heatmap palette:\n"
            f"  value={value}, min={self.min_value}, max={self.max_value}"
        )

        d = self.max_value - self.min_value
        normalized = 1.0 - ((value - self.min_value) / d if d else 0)
        # avoid black/dark by adding 20% of lightness
        normalized = 0.5 + 0.5 * normalized
        app_logger.info(f"  normalized={normalized}")

        if self.base_color == self.BASE_COLOR_GRAY:
            return (
                f"#{int(255 * normalized):02x}"
                f"{int(255 * normalized):02x}"
                f"{int(255 * normalized):02x}"
            )
        if self.base_color == self.BASE_COLOR_R:
            return f"#{int(255 * normalized):02x}0000"
        if self.base_color == self.BASE_COLOR_G:
            return f"#00{int(255 * normalized):02x}00" if value else "#99ff99"
        if self.base_color == self.BASE_COLOR_B:
            return f"#0000{int(255 * normalized):02x}"

        return "#000000"
