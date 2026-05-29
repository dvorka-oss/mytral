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
import tempfile

import pytest

from mytral.ai import acoaches as ai_chats


@pytest.mark.mytral
def test_save_and_load_acoach_chats():
    """Test save_acoach_chats and load_acoach_chats roundtrip."""
    # GIVEN
    chats = [
        ai_chats.ACoachChat(
            key="chat-1",
            coach_key="c1",
            title="Test chat",
            created_at="2025-01-01T10:00:00",
            messages=[
                ai_chats.ACoachMessage(
                    role="user", content="Hello coach", ts="2025-01-01T10:00:00"
                ),
                ai_chats.ACoachMessage(
                    role="assistant",
                    content="Hello athlete!",
                    ts="2025-01-01T10:00:01",
                ),
            ],
        )
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        # WHEN
        ai_chats.save_acoach_chats(user_id="testuser", data_dir=tmpdir, chats=chats)
        loaded = ai_chats.load_acoach_chats(user_id="testuser", data_dir=tmpdir)

        # THEN
        assert len(loaded) == 1
        assert loaded[0].key == "chat-1"
        assert loaded[0].title == "Test chat"
        assert len(loaded[0].messages) == 2
        assert loaded[0].messages[0].content == "Hello coach"
        assert loaded[0].messages[1].content == "Hello athlete!"
        print("DONE: save and load acoach chats")


@pytest.mark.mytral
def test_load_acoach_chats_missing_file():
    """Test load_acoach_chats returns empty list when file does not exist."""
    # GIVEN
    with tempfile.TemporaryDirectory() as tmpdir:
        # WHEN
        loaded = ai_chats.load_acoach_chats(user_id="nouser", data_dir=tmpdir)

        # THEN
        assert loaded == []
        print("DONE: load missing file returns empty list")


@pytest.mark.mytral
def test_save_acoach_chats_creates_directory():
    """Test save_acoach_chats creates user directory if missing."""
    # GIVEN
    chats = [
        ai_chats.ACoachChat(
            key="chat-2",
            coach_key="c2",
            title="Dir creation test",
            created_at="2025-01-01T00:00:00",
            messages=[],
        )
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        # WHEN
        ai_chats.save_acoach_chats(user_id="newuser", data_dir=tmpdir, chats=chats)
        loaded = ai_chats.load_acoach_chats(user_id="newuser", data_dir=tmpdir)

        # THEN
        assert len(loaded) == 1
        assert loaded[0].key == "chat-2"
        print("DONE: save creates directory")
