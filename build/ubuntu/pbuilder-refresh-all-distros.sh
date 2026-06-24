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

set -euo pipefail

# https://en.wikipedia.org/wiki/Ubuntu_version_history
# obsolete:
#    precise quantal saucy precise utopic vivid wily yakkety artful cosmic
# current :
#   (trusty) xenial bionic (cosmic disco eoan) focal (groovy) hirsute impish noble
#   plucky questing resolute
for DISTRO in trusty xenial bionic focal jammy noble plucky questing resolute
do
    # pbuilder-dist stores the base tarball at ~/pbuilder/${DISTRO}-base.tgz automatically
    pbuilder-dist "${DISTRO}" create
done

# eof
