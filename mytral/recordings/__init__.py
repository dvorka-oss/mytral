# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""Data recordings to MyTraL internal representation ~ Parquet @ Polars."""


def _patch_fit_tool_tolerant_string_decode():
    """Monkeypatch fit_tool to tolerate non-UTF8 bytes in FIT string fields.

    Garmin FIT files may contain binary data in string containers (e.g.
    developer fields), which causes fit_tool's strict ``.decode('utf-8')``
    to raise UnicodeDecodeError, silently killing the entire FIT parse.
    Using ``errors='replace'`` keeps the parser running so that standard
    fields (timestamp, HR, speed, etc.) are still extracted correctly.
    """
    try:
        import fit_tool.field as _ft_field  # noqa: PLC0415
    except ImportError:
        return

    if getattr(
        _ft_field.Field.read_strings_from_bytes,
        "_mytral_patched",
        False,
    ):
        return  # already patched

    _original = _ft_field.Field.read_strings_from_bytes

    def _tolerant_read_strings_from_bytes(self, bytes_buffer: bytes) -> None:
        string_container = bytes_buffer.decode("utf-8", errors="replace")
        strings = string_container.split(chr(0))
        strings = strings[:-1]
        strings = [x for x in strings if x]
        self.encoded_values = []
        self.encoded_values.extend(strings)

    _tolerant_read_strings_from_bytes._mytral_patched = True  # type: ignore[attr-defined]
    _ft_field.Field.read_strings_from_bytes = _tolerant_read_strings_from_bytes


_patch_fit_tool_tolerant_string_decode()
