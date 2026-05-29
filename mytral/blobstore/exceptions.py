# MyTraL: my trailing log
#
# Copyright (C) 2022-2026 Martin Dvorak <martin.dvorak@mindforger.com>
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


class BlobStoreError(Exception):
    """Base exception for all blob store errors."""


class BlobNotFoundError(BlobStoreError):
    """Raised when a requested blob does not exist."""


class BlobConflictError(BlobStoreError):
    """Raised when a conflicting blob already exists and replace is not requested."""


class BlobValidationError(BlobStoreError):
    """Raised when an uploaded file fails validation rules."""


class BlobConfigurationError(BlobStoreError):
    """Raised when the blob store backend is misconfigured."""
