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
import pathlib
import re

import pytest


@pytest.mark.mytral
def test_activity_get_highlight_photo_uses_lightbox_gallery_link():
    # GIVEN
    template_path = (
        pathlib.Path(__file__).parent.parent
        / "mytral"
        / "templates"
        / "activity-get.html"
    )

    # WHEN
    template = template_path.read_text(encoding="utf-8")

    # THEN
    match = re.search(
        r'<a\s+data-fslightbox="activity-photos"\s+data-type="image"\s+'
        r'href="{{ url_for\('
        r"'download_activity_photo', activity_key=activity_entity\.key, "
        r"blob_key=photo\.blob_key\)\s*}}"
        r'"\s+class="d-block">',
        template,
    )
    assert match is not None
    print("DONE: activity highlight photo stays in the lightbox gallery")
