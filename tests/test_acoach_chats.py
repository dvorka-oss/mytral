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
import pytest

from mytral.ai import acoaches as ai_chats


@pytest.mark.mytral
def test_acoach_message_roundtrip():
    """Test ACoachMessage serialization roundtrip."""
    # GIVEN
    msg = ai_chats.ACoachMessage(
        role="user",
        content="How did I train this week?",
        ts="2025-01-01T10:00:00",
    )

    # WHEN
    d = msg.to_dict()
    restored = ai_chats.ACoachMessage.from_dict(d)

    # THEN
    assert restored.role == msg.role
    assert restored.content == msg.content
    assert restored.ts == msg.ts
    print("DONE: ACoachMessage roundtrip")


@pytest.mark.mytral
def test_acoach_chat_roundtrip():
    """Test ACoachChat serialization roundtrip."""
    # GIVEN
    chat = ai_chats.ACoachChat(
        key="chat-1",
        coach_key="c1",
        title="Weekly training review",
        created_at="2025-01-01T10:00:00",
        messages=[
            ai_chats.ACoachMessage(
                role="user", content="How did I train?", ts="2025-01-01T10:00:00"
            ),
            ai_chats.ACoachMessage(
                role="assistant",
                content="You trained well this week.",
                ts="2025-01-01T10:00:05",
            ),
        ],
    )

    # WHEN
    d = chat.to_dict()
    restored = ai_chats.ACoachChat.from_dict(d)

    # THEN
    assert restored.key == chat.key
    assert restored.coach_key == chat.coach_key
    assert restored.title == chat.title
    assert restored.created_at == chat.created_at
    assert len(restored.messages) == 2
    assert restored.messages[0].role == "user"
    assert restored.messages[1].role == "assistant"
    print("DONE: ACoachChat roundtrip")


@pytest.mark.mytral
def test_acoach_chat_empty_messages():
    """Test ACoachChat with no messages."""
    # GIVEN
    d = {
        "key": "chat-2",
        "coach_key": "c1",
        "title": "Empty chat",
        "created_at": "2025-01-01T00:00:00",
    }

    # WHEN
    chat = ai_chats.ACoachChat.from_dict(d)

    # THEN
    assert chat.messages == []
    print("DONE: ACoachChat with empty messages")
