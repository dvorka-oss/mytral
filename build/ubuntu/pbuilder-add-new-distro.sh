#!/bin/bash
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

# https://en.wikipedia.org/wiki/Ubuntu_version_history
# boostrap new OR refresh distribution base for pbuilder
export DISTRO=resolute

sudo pbuilder --create --distribution ${DISTRO}
rm -vf ~/pbuilder/${DISTRO}-base.tgz
cp /var/cache/pbuilder/base.tgz ~/pbuilder/${DISTRO}-base.tgz

# eof
