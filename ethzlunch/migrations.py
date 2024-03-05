# reminder - A maubot plugin to remind you about things.
# Copyright (C) 2020 Tulir Asokan
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from mautrix.util.async_db import Connection, Scheme, UpgradeTable

upgrade_table = UpgradeTable()


@upgrade_table.register(description="Latest revision")
async def upgrade_v1(conn: Connection, scheme: Scheme) -> None:
    await conn.execute(
        f"""CREATE TABLE IF NOT EXISTS reminder (
            event_id    VARCHAR(255) NOT NULL,  /* event_id of the message that created the reminder */
            room_id     VARCHAR(255) NOT NULL,  /* room_id for this reminder */
            start_time  TEXT,                   /* time for one-off reminders, stored as an ISO 8601 string because sqlite doesn't have date types */
            message     TEXT,                   /* message for the reminder */
            reply_to    VARCHAR(255),           /* if the reminder created as a reply to another message, this is that message's event_id */
            cron_tab    TEXT,                   /* cron string if it's a cron reminder */
            creator     VARCHAR(255),           /* user_id of the person who created the reminder */
            recur_every TEXT,                   /* string to parse to schedule the next recurring reminder, e.g. 'tuesday at 2pm' */
            is_agenda   BOOL,                   /* agendas are alarms that don't trigger */
            confirmation_event TEXT,            /* event_id of the confirmation message, so that we can delete the confirmation if the reminder is deleted */
            PRIMARY KEY (event_id)
        )"""
    )

    await conn.execute(
        f"""CREATE TABLE IF NOT EXISTS reminder_target (
            event_id            VARCHAR(255) NOT NULL,  /* event_id in the reminder table */
            user_id             VARCHAR(255) NOT NULL,  /* user_id of the subscriber */
            subscribing_event   VARCHAR(255) NOT NULL,  /* event_id of the event creating the subscription, either a 👍 or the reminder message itself */
            PRIMARY KEY (user_id, event_id),
            FOREIGN KEY (event_id) REFERENCES reminder (event_id) ON DELETE CASCADE
        )"""
    )

    await conn.execute(
        f"""CREATE TABLE IF NOT EXISTS user_settings (
            user_id     VARCHAR(255) NOT NULL,  /* user_id */
            timezone    TEXT,                   /* user's timezone, e.g. America/Los_Angeles, PST. see https://en.wikipedia.org/wiki/List_of_tz_database_time_zones */
            locale      TEXT,                   /* user's locale or langauge, e.g. en, en-AU, fr, fr-CA. See https://dateparser.readthedocs.io/en/latest/supported_locales.html */
            price       TEXT,                   /* user's price category */
            facilities  TEXT,                   /* user's facilities filter list */
            PRIMARY KEY (user_id)
        )"""
    )
