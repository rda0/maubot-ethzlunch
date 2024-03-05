# ethzlunch - A maubot plugin for the canteen lunch menus at ETH Zurich.
# Copyright (C) 2024 Sven Mäder
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
import re
from typing import List, Dict
from datetime import date

client_id = "?client-id=ethz-wcms"
default_meal_time_names = ["lunch", "mittag"]


def parse_facilities(data: Dict) -> Dict:
    data = data["facility-array"]
    return {d["facility-name"]: d["facility-id"] for d in data}


def filter_facilities(facilities: Dict, facilities_filter: str) -> Dict:
    filter_list = list(filter(len, re.split(r"\s?,\s?|\s?\n+\s?", facilities_filter)))
    return {k: v for k, v in facilities.items() if any(f.lower() in k.lower() for f in filter_list)}


def markdown_facilities(facilities: Dict) -> str:
    return "\n".join(['- ' + m for m in sorted(facilities)])


def parse_menus(data: Dict, facilities: Dict, customer: str = "int",  # noqa: C901
                meal_time_names: List = default_meal_time_names) -> Dict:
    menus = {}
    data = data["weekly-rota-array"]

    for facility_name, facility_id in facilities.items():
        weekday = date.today().weekday()
        menu = next(filter(lambda m: m["facility-id"] == facility_id, data), None)

        if not menu:
            menus[facility_name] = None
            continue

        day = menu["day-of-week-array"][weekday]

        if "opening-hour-array" in day and day["opening-hour-array"]:
            oha = day["opening-hour-array"][0]
            open_hours_from = oha["time-from"]
            open_hours_to = oha["time-to"]
            open_hours = f"{open_hours_from} - {open_hours_to}"
        else:
            menus[facility_name] = None
            continue

        if "meal-time-array" in oha and oha["meal-time-array"]:
            mta = oha["meal-time-array"]
        else:
            menus[facility_name] = None
            continue

        for mt in mta:
            mt_name = mt["name"].lower()

            if not any(mtn in mt_name for mtn in meal_time_names):
                continue

            mt_from = mt["time-from"]
            mt_to = mt["time-to"]
            time = f"{mt_from} - {mt_to}"
            meals = {}

            if "line-array" not in mt:
                menus[facility_name] = {"open": open_hours, "time": time, "meals": None}
                continue

            for meal in mt["line-array"]:
                try:
                    station = meal["name"].strip()
                    name = meal["meal"]["name"].strip()
                    description = meal["meal"]["description"].strip()
                    image_url = ""
                    if "image-url" in meal["meal"]:
                        image_url = meal["meal"]["image-url"].strip()
                    image = image_url + client_id if image_url else ""
                    price = ""

                    if "meal-price-array" in meal["meal"]:
                        for mp in meal["meal"]["meal-price-array"]:
                            if customer in mp["customer-group-desc-short"].lower():
                                price = mp["price"]

                    meals[station] = {"name": name, "description": description,
                                      "price": price, "image": image}
                except KeyError:
                    continue

            menus[facility_name] = {"open": open_hours, "time": time, "meals": meals}

    return menus


def markdown_menus(menus: Dict) -> str:
    md = ""

    for facility, value in dict(sorted(menus.items())).items():
        time = value["time"] if value and value['meals'] else "no menu"
        md += f"#### {facility.lower()} ({time})\n"

        if value and value['meals']:
            for meal, value in dict(sorted(value['meals'].items())).items():
                md += "- "
                md += f"**{meal.lower()}** "
                md += f"[{value['name'].lower()}]({value['image']})"
                if value['price']:
                    md += f" [{float(value['price']):.2f}]"
                md += f": {value['description'].lower()}"
                md += "\n"

    return md
