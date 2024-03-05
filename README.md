# ETH Zurich Lunch Bot

A [maubot](https://github.com/maubot/maubot) plugin for the canteen lunch menus at ETH Zurich.

Maubot forked from [reminder-agenda bot](https://github.com/MxMarx/reminder), which is
basically [matrix-reminder-bot](https://github.com/anoadragon453/matrix-reminder-bot/tree/master) and [maubot/reminder](https://github.com/maubot/reminder) smushed together.
Extension of [lunch-menu-fetcher](https://gitlab.phys.ethz.ch/gabriema/lunch-menu-fetcher),
which uses webhooks to post lunch menus to rooms.
This project includes code taken from all repositories, credit goes to them!

## Features

* Show lunch menu (optional canteens filter)
* Persistent user config: menu language, canteens filter, price category
* Set up recurring reminders to post the lunch menu
* Subscribe to other people's reminders

## Setup

Dependencies:

```bash
pip install pytz
pip install dateparser
pip install apscheduler
pip install cron_descriptor
```

* [pytz](https://pypi.org/project/pytz/)
* [apscheduler](https://github.com/agronholm/apscheduler)
* [dateparser](https://github.com/scrapinghub/dateparser)
* [cron_descriptor](https://github.com/Salamek/cron-descriptor) (optional, shows cron reminders with natural language)

## Usage

```
!lunch
!lunch config
!lunch help
```
