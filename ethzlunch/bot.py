# ethzlunch - A maubot plugin for the canteen lunch menus at ETH Zurich.
# Copyright (C) 2024 Sven Mäder
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
from typing import Type, Tuple, List, Dict
from datetime import date, timedelta
import pytz

from mautrix.types import (EventType, RedactionEvent, StateEvent, ReactionEvent, EventID)
from maubot import Plugin, MessageEvent
from maubot.handlers import command, event
from mautrix.util.async_db import UpgradeTable
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper

from .migrations import upgrade_table
from .db import ETHzLunchDatabase
from .util import validate_locale, validate_timezone, CommandSyntaxError
from .reminder import Reminder
from .ethz import (parse_facilities, parse_menus, filter_facilities, markdown_facilities,
                   markdown_menus)
from apscheduler.schedulers.asyncio import AsyncIOScheduler


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("default_timezone")
        helper.copy("default_locale")
        helper.copy("base_command")
        helper.copy("hunger_command")
        helper.copy("rate_limit_minutes")
        helper.copy("rate_limit")
        helper.copy("admin_power_level")
        helper.copy("time_format")
        helper.copy("url_facilities")
        helper.copy("url_menus")
        helper.copy("default_price")
        helper.copy("default_facilities")


class ETHzLunchBot(Plugin):
    base_command: Tuple[str, ...]
    hunger_command: Tuple[str, ...]
    default_timezone: pytz.timezone
    admin_power_level: int
    scheduler: AsyncIOScheduler
    reminders: Dict[EventID, Reminder]
    db: ETHzLunchDatabase
    url_facilities: str
    url_menus: str

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    @classmethod
    def get_db_upgrade_table(cls) -> UpgradeTable:
        return upgrade_table

    async def start(self) -> None:
        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()
        self.db = ETHzLunchDatabase(self.database)
        self.on_external_config_update()
        self.reminders = await self.db.load_all(self)

    def on_external_config_update(self) -> None:
        self.config.load_and_update()

        def config_to_tuple(list_or_str: List | str):
            return tuple(list_or_str) if isinstance(list_or_str, list) else (list_or_str,)
        self.base_command = config_to_tuple(self.config["base_command"])
        self.hunger_command = config_to_tuple(self.config["hunger_command"])
        self.admin_power_level = self.config["admin_power_level"]

        # If the locale or timezone is invalid, use default one
        self.db.defaults.locale = self.config["default_locale"]
        if not validate_locale(self.config["default_locale"]):
            self.log.warning(f'unknown default locale: {self.config["default_locale"]}')
            self.db.defaults.locale = "en"
        self.db.defaults.timezone = self.config["default_timezone"]
        if not validate_timezone(self.config["default_timezone"]):
            self.log.warning(f'unknown default timezone: {self.config["default_timezone"]}')
            self.db.defaults.timezone = "UTC"
        self.url_facilities = self.config["url_facilities"]
        self.url_menus = self.config["url_menus"]
        self.db.defaults.price = self.config["default_price"]
        self.db.defaults.facilities = ",".join(self.config["default_facilities"])

    async def stop(self) -> None:
        self.scheduler.shutdown(wait=False)

    async def get_facilities_data(self, lang: str) -> Dict:
        headers = {"Accept": "application/json"}
        params = {"lang": lang}
        resp = await self.http.get(self.url_facilities, headers=headers, params=params)
        if resp.status == 200:
            data = await resp.json()
            return data
        resp.raise_for_status()
        return None

    async def get_menus_data(self, lang: str) -> Dict:
        today = date.today().strftime("%Y-%m-%d")
        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        headers = {"Accept": "application/json"}
        params = {"lang": lang, "valid-after": today, "valid-before": tomorrow}
        resp = await self.http.get(self.url_menus, headers=headers, params=params)
        if resp.status == 200:
            data = await resp.json()
            return data
        resp.raise_for_status()
        return None

    async def get_facilities(self, user: str = "") -> Dict:
        lang = (await self.db.get_user_info(user)).locale
        facilities_data = await self.get_facilities_data(lang)
        return parse_facilities(facilities_data)

    async def get_menus(self, user: str = "", facilities_filter: str = None) -> Dict:
        user_info = await self.db.get_user_info(user)
        lang = user_info.locale
        price = user_info.price

        facilities = await self.get_facilities(user)
        menus_data = await self.get_menus_data(lang)

        if not facilities_filter:
            facilities_filter = user_info.facilities

        if facilities_filter == "all":
            facilities_filter = None

        if facilities_filter:
            facilities = filter_facilities(facilities, facilities_filter)

        return parse_menus(menus_data, facilities, customer=price)

    async def get_markdown_facilities(self, user: str = "") -> Dict | None:
        facilities = await self.get_facilities(user=user)

        if facilities:
            return markdown_facilities(facilities)
        else:
            return None

    async def get_markdown_menus(self, user: str = "",
                                 facilities_filter: str = None) -> Dict | None:
        menus = await self.get_menus(user=user, facilities_filter=facilities_filter)

        if menus:
            return markdown_menus(menus)
        else:
            return None

    async def show_lunch_menu(self, evt: MessageEvent, canteens: str) -> None:
        markdown_menus = await self.get_markdown_menus(user=evt.sender, facilities_filter=canteens)

        if markdown_menus:
            await evt.respond(markdown_menus)
        else:
            await evt.respond("No results")

    @command.new(name=lambda self: self.hunger_command[0],
                 aliases=lambda self, alias: alias in self.hunger_command)
    @command.argument("canteens", pass_raw=True, required=False)
    async def hunger(self, evt: MessageEvent, canteens: str) -> None:
        await self.show_lunch_menu(evt, canteens)

    @command.new(name=lambda self: self.base_command[0],
                 aliases=lambda self, alias: alias in self.base_command)
    async def lunch(self, evt: MessageEvent) -> None:
        pass

    @lunch.subcommand("menu", aliases=["menus", "show"],
                      help="Show lunch menu (canteens example: `all` or `poly,food market,fusion`)")
    @command.argument("canteens", pass_raw=True, required=False)
    async def show(self, evt: MessageEvent, canteens: str) -> None:
        await self.show_lunch_menu(evt, canteens)

    @lunch.subcommand("canteen", aliases=["canteens", "mensa"], help="List all canteen names")
    async def facilities_list(self, evt: MessageEvent) -> None:
        markdown_facilities = await self.get_markdown_facilities(user=evt.sender)

        if markdown_facilities:
            await evt.respond(markdown_facilities)
        else:
            await evt.respond("No results")

    @lunch.subcommand("config", aliases=["conf"], help="Set or show config settings")
    async def settings(self, evt: MessageEvent) -> None:
        pass

    @settings.subcommand("language", aliases=["lang"], help="Set menu language (`en` or `de`)")
    @command.argument("lang")
    async def config_lang(self, evt: MessageEvent, lang: str) -> None:
        if not lang:
            await evt.reply(f"Menu language is "
                            f"{(await self.db.get_user_info(evt.sender)).locale}")
            return
        if lang in ["en", "de"]:
            await self.db.set_user_info(evt.sender, key="locale", value=lang)
            await evt.react("👍")
        else:
            await evt.reply(f"Unknown language: `{lang}`\n"
                            f"Available languages: `en`, `de`")

    @settings.subcommand("canteen", aliases=["canteens", "mensa"],
                         help="Set canteens (example: `all` or `poly,food market,fusion`)")
    @command.argument("canteens", pass_raw=True)
    async def config_canteen(self, evt: MessageEvent, canteens: str) -> None:
        if not canteens:
            canteens = (await self.db.get_user_info(evt.sender)).facilities
            await evt.reply(f"Canteen filter is: `{canteens}`")
            return

        await self.db.set_user_info(evt.sender, key="facilities", value=canteens)
        await evt.react("👍")

    @settings.subcommand("price", help="Set price category (`int`, `ext`, `stud` or `off`)")
    @command.argument("category")
    async def config_price(self, evt: MessageEvent, category: str) -> None:
        if not category:
            category = (await self.db.get_user_info(evt.sender)).price
            off = " (prices not shown)" if category == "off" else ""
            await evt.reply(f"Price category is: `{category}`{off}")
            return

        if category in ["int", "ext", "stud", "off"]:
            await self.db.set_user_info(evt.sender, key="price", value=category)
            await evt.react("👍")
        else:
            await evt.reply(f"Unknown price category: `{category}`\n"
                            f"Available price categories: `int`, `ext`, `stud`\n"
                            f"Disable prices in menus: `off`")

    @lunch.subcommand("remind", aliases=["reminder"],
                      help="Create reminder (time: `hh:mm`, days default: `mon-fri`)")
    @command.argument("time", matches="[0-9]{1,2}:[0-9]{2}")
    @command.argument("days", required=False)
    @command.argument("canteens", required=False, pass_raw=True)
    async def remind(self, evt: MessageEvent,
                     time: str = None,
                     days: str = None,
                     canteens: str = None) -> None:
        power_levels = await self.client.get_state_event(room_id=evt.room_id,
                                                         event_type=EventType.ROOM_POWER_LEVELS)
        user_power = power_levels.users.get(evt.sender, power_levels.users_default)

        if user_power < self.admin_power_level:
            await evt.reply(f"Power level of {self.admin_power_level} is required")
            return

        user_info = await self.db.get_user_info(evt.sender)
        hour, minute = tuple(time.split(':'))

        if not days:
            days = "mon-fri"

        cron = f"{minute} {hour} * * {days}"

        try:
            reminder = Reminder(
                bot=self,
                room_id=evt.room_id,
                message=canteens,
                event_id=evt.event_id,
                cron_tab=cron,
                creator=evt.sender,
                user_info=user_info,
            )

        except CommandSyntaxError as e:
            await evt.reply(e.message)
            return

        await self.db.store_reminder(reminder)
        await self.confirm_reminder(evt, reminder)
        self.reminders[reminder.event_id] = reminder

    async def confirm_reminder(self, evt: MessageEvent, reminder: Reminder):
        confirmation_event = await evt.react("\U0001F44D")
        await reminder.set_confirmation(confirmation_event)

        body = "Reminder"
        if reminder.message:
            body += f" for `{reminder.message}`"
        body += " scheduled"
        if reminder.recur_every or reminder.cron_tab:
            user_info = await self.db.get_user_info(evt.sender)
            formatted_time = reminder.formatted_time(user_info)
            body += f" {formatted_time}"
        body += ".\n\nAnyone can \U0001F44D the command message above to get pinged."

        await evt.reply(body)

    @lunch.subcommand("cancel", help="Cancel reminder")
    async def cancel_reminder(self, evt: MessageEvent) -> None:
        reminders = []
        if evt.content.get_reply_to():
            reminder_message = await self.client.get_event(evt.room_id, evt.content.get_reply_to())
            if "ch.ethz.phys.lunch" not in reminder_message.content:
                await evt.reply("That doesn't look like a valid reminder event.")
                return
            reminders = [self.reminders[reminder_message.content["ch.ethz.phys.lunch"]["id"]]]
        else:
            reminders = [v for k, v in self.reminders.items() if v.room_id == evt.room_id]

        for reminder in reminders:
            power_levels = await self.client.get_state_event(room_id=reminder.room_id,
                                                             event_type=EventType.ROOM_POWER_LEVELS)
            user_power = power_levels.users.get(evt.sender, power_levels.users_default)

            if reminder.creator == evt.sender or user_power >= self.admin_power_level:
                await reminder.cancel()
            else:
                await evt.reply(f"Power level of {self.admin_power_level} is required")

        await evt.react("👍")

    @command.passive(regex=r"(?:\U0001F44D[\U0001F3FB-\U0001F3FF]?)",
                     field=lambda evt: evt.content.relates_to.key,
                     event_type=EventType.REACTION, msgtypes=None)
    async def subscribe_react(self, evt: ReactionEvent, _: Tuple[str]) -> None:
        """
        Subscribe to a reminder by reacting with "👍"️
        """
        reminder_id = evt.content.relates_to.event_id
        reminder = self.reminders.get(reminder_id)
        if reminder:
            await reminder.add_subscriber(user_id=evt.sender, subscribing_event=evt.event_id)

    @event.on(EventType.ROOM_REDACTION)
    async def redact(self, evt: RedactionEvent) -> None:
        """Unsubscribe from a reminder by redacting the message"""
        for key, reminder in self.reminders.items():
            if evt.redacts in reminder.subscribed_users:
                await reminder.remove_subscriber(subscribing_event=evt.redacts)

                # If the reminder has no users left, cancel it
                # if not reminder.subscribed_users or reminder.event_id == evt.redacts:
                #     await reminder.cancel(redact_confirmation=True)
                # break

    @event.on(EventType.ROOM_TOMBSTONE)
    async def tombstone(self, evt: StateEvent) -> None:
        """If a room gets upgraded or replaced, move any reminders to the new room"""
        if evt.content.replacement_room:
            await self.db.update_room_id(old_id=evt.room_id, new_id=evt.content.replacement_room)

    @lunch.subcommand("help", help="Show the help")
    async def help(self, evt: MessageEvent) -> None:
        await evt.reply(self._help_message())

    def _help_message(self) -> str:
        bc = f"!{self.base_command[0]}"
        hc = f"`!{'`, `!'.join(self.hunger_command)}`"
        default_facilities_markdown = '\n- '.join(self.config["default_facilities"])
        return (f"Type `{bc}` for available subcommands and syntax\n\n"
                f"Type `{bc} menu` to show the lunch menus of the day\n\n"
                f"By default the menus for then following canteens are shown:\n"
                f"- {default_facilities_markdown}\n\n"
                f"Type `{bc} canteens` to show all available canteens\n\n"
                f"Type `{bc} config` for configuration settings and syntax\n\n"
                f"Type `{bc} config canteen <canteens>` to configure other canteens.\n\n"
                f"Replace `<canteens>` with a comma-separated list of canteen names,\n"
                f"a comma-separated list of sequences of characters matching parts of\n"
                f"canteen names (example: `poly,food market,fusion`) or `all`.\n"
                f"This will store your canteen selection and remember it for any commands\n"
                f"or reminders without explicit `[canteens]` selection.\n\n"
                f"Type `{bc} config language de` to show menus in German\n\n"
                f"Type `{bc} config price off` to hide menu prices\n\n"
                f"Type `{bc} remind 11:00` to schedule a reminder in the room.\n"
                f"The bot will then send the lunch menu every weekday at the specified time.\n"
                f"A power level of {self.admin_power_level} is required for reminders.\n\n"
                f"React with \U0001F44D to any `{bc} remind` command message\n"
                f"to get pinged (mentioned) in the reminder.\n\n"
                f"Type `{bc} cancel` in a new message to cancel all reminders in the room\n"
                f"or reply to a reminder to cancel a specific reminder\n\n"
                f"The following commands are aliases for the `{bc} menu` subcommand: {hc}")
