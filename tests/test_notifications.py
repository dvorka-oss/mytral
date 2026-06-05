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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Tests for notification system."""

import pytest

from mytral.notifications import _entities
from mytral.notifications import _storage


@pytest.mark.mytral
class TestNotificationEntity:
    """Tests for NotificationEntity dataclass."""

    def test_create_notification(self):
        # GIVEN notification parameters
        user_id = "test_user"
        category = "success"
        message = "Activity created"

        # WHEN creating a notification
        notif = _entities.NotificationEntity.create(
            user_id=user_id,
            category=category,
            message=message,
        )

        # THEN notification has expected values
        assert notif.user_id == user_id
        assert notif.category == category
        assert notif.message == message
        assert notif.key is not None
        assert len(notif.key) > 0
        assert notif.created_at is not None
        print("DONE: notification entity created successfully")

    def test_to_dict_and_from_dict_roundtrip(self):
        # GIVEN a notification entity
        notif = _entities.NotificationEntity.create(
            user_id="test_user",
            category="error",
            message="Something went wrong",
        )

        # WHEN converting to dict and back
        notif_dict = notif.to_dict()
        restored = _entities.NotificationEntity.from_dict(notif_dict)

        # THEN the restored entity matches the original
        assert restored.key == notif.key
        assert restored.user_id == notif.user_id
        assert restored.category == notif.category
        assert restored.message == notif.message
        assert restored.created_at == notif.created_at
        print("DONE: notification dict roundtrip successful")


@pytest.mark.mytral
class TestNotificationStorage:
    """Tests for NotificationStorage in-memory store."""

    def test_add_and_list_notifications(self):
        # GIVEN notification storage
        notif_storage = _storage.NotificationStorage(max_notifications=10)
        user_id = "test_user"

        # WHEN adding notifications
        notif_storage.add(user_id, "success", "First notification")
        notif_storage.add(user_id, "error", "Second notification")
        notif_storage.add(user_id, "info", "Third notification")

        # THEN all notifications are listed (newest first)
        notif_list = notif_storage.list(user_id)
        assert len(notif_list) == 3
        assert notif_list[0].message == "Third notification"
        assert notif_list[1].message == "Second notification"
        assert notif_list[2].message == "First notification"
        print("DONE: add and list notifications works")

    def test_max_notifications_enforced(self):
        # GIVEN notification storage with max 3 notifications
        notif_storage = _storage.NotificationStorage(max_notifications=3)
        user_id = "test_user"

        # WHEN adding more notifications than the max
        for i in range(5):
            notif_storage.add(user_id, "info", f"Notification {i}")

        # THEN only the last 3 notifications are kept (newest first)
        notif_list = notif_storage.list(user_id)
        assert len(notif_list) == 3
        assert notif_list[0].message == "Notification 4"
        assert notif_list[2].message == "Notification 2"
        print("DONE: max notifications enforced")

    def test_get_count(self):
        # GIVEN notification storage with some notifications
        notif_storage = _storage.NotificationStorage(max_notifications=10)
        user_id = "test_user"

        # WHEN counting
        count_empty = notif_storage.get_count(user_id)
        notif_storage.add(user_id, "info", "Test")
        count_one = notif_storage.get_count(user_id)

        # THEN counts are correct
        assert count_empty == 0
        assert count_one == 1
        print("DONE: notification count works")

    def test_clear_all_notifications(self):
        # GIVEN notification storage with notifications
        notif_storage = _storage.NotificationStorage(max_notifications=10)
        user_id = "test_user"
        notif_storage.add(user_id, "success", "Msg 1")
        notif_storage.add(user_id, "info", "Msg 2")

        # WHEN clearing all notifications
        deleted_count = notif_storage.clear_all(user_id)

        # THEN all notifications are deleted
        assert deleted_count == 2
        notif_list = notif_storage.list(user_id)
        assert len(notif_list) == 0
        print("DONE: clear all notifications works")

    def test_clear_all_empty(self):
        # GIVEN notification storage with no notifications
        notif_storage = _storage.NotificationStorage(max_notifications=10)
        user_id = "test_user"

        # WHEN clearing notifications
        deleted_count = notif_storage.clear_all(user_id)

        # THEN no errors occur and count is zero
        assert deleted_count == 0
        print("DONE: clear empty notifications works")

    def test_notifications_per_user_isolated(self):
        # GIVEN two different users
        notif_storage = _storage.NotificationStorage(max_notifications=10)

        # WHEN adding notifications for different users
        notif_storage.add("user_a", "info", "User A msg")
        notif_storage.add("user_b", "error", "User B msg")

        # THEN each user sees only their own notifications
        list_a = notif_storage.list("user_a")
        list_b = notif_storage.list("user_b")
        assert len(list_a) == 1
        assert list_a[0].message == "User A msg"
        assert len(list_b) == 1
        assert list_b[0].message == "User B msg"
        print("DONE: user notification isolation works")
