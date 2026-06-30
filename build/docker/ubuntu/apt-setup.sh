#!/bin/sh
#
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

# Make "apt-get update" work on any Ubuntu release, including end-of-life ones.
#
# EOL releases (trusty, xenial, ...) are removed from archive.ubuntu.com and
# moved to old-releases.ubuntu.com, and their Release files are expired. This
# script first tries a normal update and, only if that fails, switches the
# sources to old-releases and disables the Valid-Until check.

set -e

if apt-get update 2>/dev/null; then
    exit 0
fi

echo "apt-setup: archive update failed — switching to old-releases.ubuntu.com"
sed -i \
    -e 's|//archive.ubuntu.com|//old-releases.ubuntu.com|g' \
    -e 's|//security.ubuntu.com|//old-releases.ubuntu.com|g' \
    /etc/apt/sources.list
apt-get -o Acquire::Check-Valid-Until=false update
