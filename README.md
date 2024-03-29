# Discogs Alert

<p align="center">
    <a href="https://github.com/michaelhball/discogs_alert/blob/main/LICENSE">
        <img alt="GitHub" src="https://img.shields.io/badge/License-MIT-yellow.svg">
    </a>
    <a href="https://pypi.org/project/discogs_alert">
        <img alt="GitHub" src="https://img.shields.io/pypi/v/discogs_alert">
    </a>
    <a href="https://pypi.org/project/discogs_alert">
        <img alt="GitHub" src="https://img.shields.io/pypi/pyversions/tox.svg">
    </a>
    <a href="https://github.com/michaelhball/discogs_alert/actions/workflows/pr_checks.yml">
        <img alt="GitHub" src="https://github.com/michaelhball/discogs_alert/actions/workflows/pr_checks.yml/badge.svg">
    </a>
</p>

<h3 align="center">
<p>Customised, real-time alerting for your hard-to-find wantlist items.
</h3>

![vinyl icon](https://github.com/michaelhball/discogs_alert/blob/main/img/vinyl.png) 
discogs-alert enables you to configure ~real-time alerts that notify you the moment a hard-to-find release goes on sale. The project is designed to require as little effort as possible: you customise your preference once, upfront, and then sit back and wait for a notification.

![vinyl icon](https://github.com/michaelhball/discogs_alert/blob/main/img/vinyl.png) 
discogs-alert enables both global and fine-grained customisation of your preferences (including price thresholds, minimum seller rating, minimum media / sleeve conditions, and countries from which you either do or don't want to receive alerts). You'll only ever get notified if a record goes on sale that really matches what you're looking for.

![vinyl icon](https://github.com/michaelhball/discogs_alert/blob/main/img/vinyl.png) 
If you have suggestions or ideas, please reach out! So far I've bought more than 50 records thanks to `discogs_alert` and I'd love to make it useful as possible for others.

## Requirements

- Python >= 3.7
- [Chromedriver](https://chromedriver.chromium.org/). If you have Google Chrome or any Chromium browser installed on your computer, you'll be fine.

## Installation & Setup

You can install discogs-alert as a Python package, either via the Python Package Index (PyPI) or from source, or as a docker image from DockerHub.

### Python

To install using `pip`:
```
pip install discogs-alert
```

#### Downloading and installing from source 
Download the latest version of discogs-alert from PyPI:

[https://pypi.org/project/discogs-alert/](https://pypi.org/project/discogs-alert/)

You can then  install it by doing the following:
```
$ tar xvfz discogs_alert-0.0.x.tar.gz
$ cd discogs_alert-0.0.x
$ python setup.by build
$ python setup.py install 
```
The last command must be executed as a privileged user if you aren't currently using a virtualenv.

### Docker

Assuming you have docker installed, you can pull the latest image via
```bash
docker pull miggleball/discogs_alert:latest
```

Calling `docker run discogs_alert:latest` runs the entrypoint `python -m discogs_alert`, so you'll need to pass the
required arguments, easiest using an environment variable file (`docker run --env-file .env discogs_alert:latest`).

## Setup

Before you can use this project, there are a few more things that need to be setup.

### Discogs access token

A Discogs access token allows `discogs_alert` to send requests to the discogs API on your behalf, and in particular it increases the rate at which you're allowed to make requests. This token can only be used to access the music database features of the Discogs API, not the marketplace, so there is no risk that you're accidentally granting control over the buying or selling of records. You can find more information [here](https://www.discogs.com/developers/#page:authentication).

To create an access token, go to your Discogs settings and click on the [Developer](https://www.discogs.com/settings/developers) tab. There is a button on this page to generate a new token. For now, just copy this token to your computer.

### Creating your wantlist

There are two different ways you can create a wantlist: 1) by connecting to one of your existing Discogs lists, or 2) by creating a local JSON file. The first option is easier, faster, and fits within your regular Discogs workflow, while the latter enables more expressivity as you can specify fine-grained filters (e.g. price, media/sleeve quality) for each release. I plan to add this level of control to the Discogs list approach shortly, so I intend for that to completely replace the need for a local file.

#### Discogs List

Using one of your existing Discogs [lists](https://www.discogs.com/lists) only requires that you specify the ID of the list at runtime, the process for which is outlined in the [usage](#usage) section below. Ideally you should set up a list specifically for this purpose, as you'll be notified the moment any of the releases in your list go on sale. This approach makes it incredibly easy to add new releases to your wantlist: simply add a release to the specified list and `discogs_alert` will automatically identify this and add that release to those it's searching for on the next iteration.

#### Local JSON

Here is an example `wantlist.json` file:
```yaml
[
  {
    "id": 1061046,
    "display_title": "Deep² — Sphere",
    "min_media_condition": "VERY_GOOD"
  },
  {
    "id": 2247646,
    "display_title": "Charanjit Singh — Ten Ragas to a Disco Beat",
    "price_threshold": 500 
  }
]
```
The wantlist is a list of objects, each object representing a release. The only essential attributes are the `id` field, which can be found on each release's Discogs page, and the `display_title`, which is the name you give the release s.t. you will recognise it when you're notified.

There are a number of optional attributes that can be included for each release. The combination of all attributes applied to a given release are used as a filter, so you will only be notified if all conditions are met for a given listing item. In the above case, the user is looking for any `VERY_GOOD` or higher copies of the `Deep²` release, with no maximum price (e.g. an example scenario here is that there are currently no copies on the market, and the user wants to be notified as soon as one goes on sale). For the `Charanjit Singh` release, the user is looking for any copies on sale for less than `€500`. NB: the currency is determined later, at runtime. This is outlined in the [usage](#usage) section below.

Remember that all criteria for restricting your alerts also have global values, the setting of which is discussed in [usage](#usage)). This means that if you want the same filters for most releases you do _not_ need to specify them for every single release in your `wantlist.json`. You can set the values once globally (when you run the program), and then set only those per-release values that differ from the global settings. Any filters specified in your `wantlist.json` will override the global values.

The possible optional filters are as follows:
* `price_threshold`: maximum allowable price (_excluding_ shipping)
* `min_media_condition`: minimum allowable media condition (one of `'POOR'`, `'FAIR'`, `'GOOD'`, `'GOOD_PLUS'`,
`'VERY_GOOD'`, `'VERY_GOOD_PLUS'`, `'NEAR_MINT'`, or `'MINT'`)
* `min_sleeve_condition`: minimum allowable sleeve condition (one of `'POOR'`, `'FAIR'`, `'GOOD'`, `'GOOD_PLUS'`,
`'VERY_GOOD'`, `'VERY_GOOD_PLUS'`, `'NEAR_MINT'`, or `'MINR'`)

### Alerting

You can choose from  several different alerting services to notify you once a record you are searching is on sale, each coming with its own setup requirements. The options and their setup are outlined here

#### Pushbullet

As of June 2023, Pushbullet is only available on Android or Desktop. To use Pushbullet, you first need to create an [account](https://www.pushbullet.com/) before installing the app anywhere you wish to receive notifications. Once you've created an account, navigate to your [settings](https://www.pushbullet.com/#settings) page and  create an access token. As before, save this token somewhere on your computer. You'll need to configure it either at the command-line or via an environment variable (see the [usage](#usage) section below).

NB: when using Pushbullet, please be sure to open the app at least once a month. If you don't the notification service will silently stop working as it deams your account to be 'dead'.

#### Telegram

To use Telegram you first need to create a custom bot, the easiest mechanism for which is to use `BotFather`. Search for `@BotFather` on Telegram and send a "/start" message followed by "/newbot", before following the setup instructions. Be sure to save your API token somewhere on your computer, you'll need this to configure `discogs_alert`. Next you need to search for your bot on Telegram (by the username you just created) and send a "/start" message. Open a new tab in your browser and enter `"https://api.telegram.org/bot<yourAPIToken>/getUpdates"` in the URL bar, and you should see a response that looks like the following
```json
{"ok":true,"result":[{"update_id":"xxxxx",
"message":{"message_id":2, "from":{"id":"xxxxx","is_bot":false,"first_name":"xxxxx","username":"xxxxx","language_code":"en"},"chat":{"id":"<CHAT_ID>","first_name":"xxxxx","username":"xxxxx","type":"private"},"date":1685860541,"text":"/start","entities":[{"offset":0,"length":6,"type":"bot_command"}]}}]}
```
You need to find your `CHAT_ID` as indicated above and save that. You may have to send a few "/start" messages to your bot before you get a response that looks like this. Once you've got your CHAT ID as well as your API token, you're all good to go!

#### More coming soon ...

I plan to add more alerting options as soon as possible! Please feel free to open a PR if you have a particular service
in mind that you'd like to support.

## Usage

`discogs_alert` can be run either as a Python process or as a Docker container. Regardless of which command is used, the `discogs_alert` service will regularly pull the releases from your wantlist, check their availability on the Discogs marketplace, and send you a notification if any release (satisfying your filters) is for sale. You should leave the service running in the background at all times to be most effective.

#### Python

The minimal command needed to run the `discogs_alert` Python package is 
```bash
$ python -m discogs_alert --alerter-type=PUSHBULLET
```
though this assumes that you have previously set a few environment variables: `DA_DISCOGS_TOKEN`, either `DA_LIST_ID` or `DA_WANTLIST_PATH`, and in this case `DA_PUSHBULLET_TOKEN` (though the required arguments are different for different alerters). The discogs token should be set to the value of the token you created earlier and the list ID should be set to the ID of the Discogs list you want to use as your `discogs_alert` wantlist (or the wantlist path to a local `wantlist.json` file).

If you aren't sure how to set environment variables, you can pass these values manually using the following command
```bash
$ python -m discogs_alert --alerter-type -dt <discogs_access_token> --list-id <discogs_list_id> -pt <pushbullet_token>
```

#### Docker

The minimal command needed to run the `discogs_alert` Docker image is
```bash
$ docker run -d --env-file .env miggleball/discogs_alert:latest
```
where it is assumed that you have specified the three minimal environment variables outlined above (as well as any additional customizations) in an `.env` txt file in the current directory. Your env file should simply look as follows:
```bash
DA_DISCOGS_TOKEN=<discogs_access_token>
DA_LIST_ID=<discogs_list_id>
DA_PUSHBULLET_TOKEN=<pushbullet_token>
...
```
The `-d` flag specifies that you want to "detach" from the newly created docker container meaning it will continue running in the background.

### Extras

Please note that you _can_ add to or change the contents of your wantlist (either Discogs list or local file) while the service is running; the updated list of releases will come into effect the next time the service runs.

Each time a listing is found for one of the releases in your wantlist, you will be sent a notification via the alerter service of your choice with the title of the release and the URL to the marketplace listing. If you're using Pushbullet, as long as you don't delete a given notification then you will _not_ be sent repeat notifications for the same listing. I hope to add this functionality for the Telegram alerter in due course. You can test that your alerting is working properly by adding a release to your wantlist that you know is currently for sale.

There are a a number of additional arguments and flags that provide a deeper level of customisation. These optional arguments include the global versions of the conditions mentioned above (i.e. global seller, media, and sleeve conditions), as well as a country whitelist and blacklist. The use of any of these flags will apply to all releases in your wantlist.

For any of the following arguments, you can use either the abbreviated argument indicator (prefixed with `-`) or the verbose option (prefixed with `--`). The complete list of options, including options and default values, can be accessed at any time by running:
```bash
$ python -m discogs_alert --help
```

Here are the possible arguments:
 
* `-dt` `--discogs-token`: (str) your discogs user access token
* `-lid` `--list-id`: (int) the ID of your Discogs list (NB: either this or the `-wp` option are required).
*  `-wp` `--wantlist-path`: (str) the relative or absolute path to your `wantlist.json` file (NB: either this or the `-lid` option are required).
* `-ua` `--user-agent`: (str) the user agent string to use for anonymous queries to `discogs.com`. Please make some personalised modification to this string before you use this program, otherwise your requests might be blocked.
* `-f` `--frequency`: (int) how often you want the service to run (number of times per hour). This value must be in [1, 60]  (default=`60`, meaning the service runs once a minute)
* `-co` `--country`: (str) the country where you are (used for things like computing shipping) (default=`'Germany'`)
* `-$` `--currency`: (str) your preferred currency (default=`EUR`)
* `-msr` `--min-seller-rating`: (float) the minimum seller rating you want to accept (default=`99`)
* `-mss` `--min-seller-sales`: (float) the minimum number of sales your accept a seller to have (default=`None`)
* `-mmc` `--min-media-condition`: (str) minimum allowable media condition, as outlined above (default=`'VERY_GOOD'`)
* `-msc` `--min-sleeve-condition`: (str) minimum allowable sleeve condition, as outlined above (default=`'VERY_GOOD'`)
* `-wl` `--country-whitelist`: (str) you can pass this argument any number of times to construct a list of countries. If using a whitelist, you will only be alerted about listings by sellers from those specified countries.
* `-bl` `--country-blacklist`: (str) you can pass this argument any number of times to construct a list of countries. If using a blacklist, you will be alerted about listings by sellers from all countries except those specified in the list.
* `-at` `--alerter-type`: (str) one of the valid alerter types: `PUSHBULLET` or `TELEGRAM`
* `-pt` `--pushbullet-token`: (str) your pushbullet token (only required if `"--alerter-type=PUSHBULLET"`)
* `-tt` `--telegram-token`: (str) your telegram API token (only required if `"--alerter-type=TELEGRAM"`)
* `-tci` `--telegram-chat-id`: (str) your telgram chat ID (only required if `"--alerter-type=TELEGRAM"`)

And here are the possible flags:
* `-V` `--verbose`: (bool) use this flag if you want to run the server in verbose mode, meaning it will log updates to the command line as it runs (default=`false`)
* `-T` `--test`: (bool) use this flag if you want to run the script once rather than a fixed number of times per hour. This is useful not only for testing, but also if you're running the service as a cron job (& => cron handles scheduling).

NB: all command-line options & arguments outlined above can be configured using environment variables. Check out `python -m discogs_alert --help` for more info.

#### Full Example

To clarify the command-line interfact outlined above, here is a realistic example. In this case, we are replicating a user who is using a Discogs list as their wantlist, who wants verbose logs, no minimum seller rating, a global minimum media condition of `"VERY_GOOD"`, and who doesn't want to consider sellers from the UK or US. The command to run the service in this case would be
```bash
$ python -m discogs_alert -dt <discogs_access_token> -at PUSHBULLET -pt <pushbullet_token> --list-id <list_id> --msr None -mmc VERY_GOOD -bl UK -bl US --verbose
```

#### Running as a `cron` job

If you aren't running `discogs_alert` as a background docker container, another good approach (and my preference) is to run the process as a `cron` job. This method uses the cron command-line utility to run `discogs_alert` at regular intervals. Assuming you have specified the required environment variables, all you have to do is run `crontab -e` to open the cronjob editing window before appending the following line to the bottom of the file
```bash
*/10 * * * * source ~/.bash_profile; python -m discogs_alert -T >> <path_to_log_file>.log 2>&1
```
Upon saving & existing the file, `discogs_alert` will be run every 10 minutes and its logs will be output to the specified log file. You can then `tail -f <path_to_log_file>.log` at any point to make sure that things are running as expected.

Please refer [here](https://www.hostinger.com/tutorials/cron-job) for more information on cron and how to use `crontab`.


## Contributing

1. Fork (https://github.com/michaelhball/discogs_alert/fork)
2. Create your feature branch (git checkout -b feature/fooBar)
3. Commit your changes (git commit -am 'Add some fooBar')
4. Push to the branch (git push origin feature/fooBar)
5. Create a new Pull Request

### Setting up the dev environment

Ideally, you should work inside a virtual environment set up for this project. Once that's the case, simply run the following two commands to install all dependencies:

* `$ pip install --user poetry`
* `$ poetry install` 

And that's it! Until you want to propose your changes as a new PR. When that's the case you need to run the tests to make sure nothing has broken, which you can do simply by running `$ tox` in the project's root directory. 

## Author

[**mhsb**](https://github.com/michaelhball)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Housekeeping

<div>vinyl icon made by <a href="https://www.flaticon.com/authors/those-icons" title="Those Icons">Those Icons</a> on <a href="https://www.flaticon.com/" title="Flaticon">www.flaticon.com</a></div>
