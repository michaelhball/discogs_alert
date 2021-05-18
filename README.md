# Discogs Alert

<p align="center">
    <a href="https://github.com/michaelhball/discogs_alert/blob/main/LICENSE">
        <img alt="GitHub" src="https://img.shields.io/badge/license-GPL%203.0-blue">
    </a>
    <a href="https://github.com/michaelhball/discogs_alert/releases">
        <img alt="GitHub release" src="https://img.shields.io/github/v/release/michaelhball/discogs_alert?sort=semver">
    </a>
</p>

<h3 align="center">
<p>Customised, real-time alerting for your hard-to-find wantlist items.
</h3>

![vinyl icon](https://github.com/michaelhball/discogs_alert/blob/main/img/vinyl.png) 
discogs-alert enables you to set up ~real-time alerts so you get notified the moment those 
hard-to-find releases go on sale. The project is designed to be 'set and forget'; you customise your preferences for a 
particular release once, and then sit back and wait for a notification. 

![vinyl icon](https://github.com/michaelhball/discogs_alert/blob/main/img/vinyl.png) 
discogs-alert enables both global and fine-grained customisation of your preferences
(incl. price thresholds, minimum seller rating, and minimum media/sleeve condition). This 
means you'll only be notified if a record goes on sale that really matches what you're looking 
for.

## Requirements

- Python >= 3.6
- [Chromedriver](https://chromedriver.chromium.org/) (if you have Google Chrome or any Chromium browser 
installed on your computer, you'll be fine).

## Installation & Setup

You can install discogs-alert either via the Python Package Index (PyPI) or from source.
To install using `pip`:
```
pip install discogs-alert
```

### Downloading and installing from source 
Download the latest version of discogs-alert from PyPI:

[https://pypi.org/project/discogs-alert/](https://pypi.org/project/discogs-alert/)

You can then  install it by doing the following:
```
$ tar xvfz discogs_alert-0.0.0.tar.gz
$ cd discogs_alert-0.0.0
$ python setup.by build
$ python setup.py install 
```
The last command must be executed as a privileged user if you aren't currently using a virtualenv.

## Setup

Before you can use this project, there are a couple more things that need to be setup.

### Discogs access token

A Discogs access token allows discogs_alert to send requests to the discogs API on your behalf, as well as to
increase its allowed rate of request. This token can only be used to access the music database features of 
the Discogs API, not the marketplace, so there is no concern that you are accidentally granting control over 
the buying or selling of records. You can find more information 
[here](https://www.discogs.com/developers/#page:authentication).

To create an access token, go to your Discogs settings and click on the 
[Developer](https://www.discogs.com/settings/developers) tab. There is a button on this page to generate a 
new token. For now, just copy this token to your computer.

### Pushbullet

This project uses Pushbullet for notifying you once a record you are searching for has gone on sale. You can 
choose exactly how you want to receive these notifications (i.e. on which device), but you first need to 
create a [Pushbullet](https://www.pushbullet.com/) account. After signing up, make sure to install Pushbullet 
on all devices where you would like to receive notifications.

Once you've created an account, simply navigate to your [settings](https://www.pushbullet.com/#settings) page and 
create an access token. As before, copy this token to your computer.

### Creating your wantlist

There are two different ways you can create your wantlist (file containing all records you want to 
set up notifications for) 1) by connecting to one of your Discogs lists, or 2) by creating a local 
JSON file. The former is simpler, and requires no extra effort on your part, while the latter allows
more expressivity, as you can specify fine-grained preferences for each release.

#### Discogs List

Using one of your existing Discogs [lists]() requires only specifying the ID of the list at runtime 
(outlined in the [usage](#usage) section below). As of now, there is no fine-grained control allowed with 
this option, meaning the list you use should be one containing only those records about which you want to 
be notified immediately if they go on sale. 

#### Local JSON   

Here is an example `wantlist.json` file:
```yaml
[
  {
    "id": 1061046,
    "artist_name": "Deep²",    
    "release_name": "Sphere",
    "accept_generic_sleeve": true,
    "min_media_condition": "VG"
  },
  {
    "id": 2247646,
    "artist_name": "Charanjit Singh",
    "release_name": "Ten Ragas to a Disco Beat",
    "price_threshold": 500 
  }
]
```
The wantlist is a list of objects, each object representing one release. The only essential 
attribute is the `id` field (which can be found on each release's Discogs page), while `artist_name` and `release_name` 
are used only to format the notifications you receive.

There are a number of extra attributes that can be optionally included for each release. The combination of all 
attributes applied to a given release are used as a filter, so you will only be notified if all conditions 
are met for a given listing item. In the above case, the user is looking for any `VG` or higher 
copies of the `Deep²` release, with no maximum price (implying that there are currently none for sale, and the 
user wants to be notified when one is). For the `Charanjit Singh` release, they are looking for any copies
on sale for less than `€500`. What a bargain.

Note that all attributes relating to media and sleeve characteristics also have global values (the setting 
of which will be outlined below). This means that, if you mostly want the same conditions for all records
you're searching for, you _do not_ need to specify those in every release within your `wantlist.json` file. 
You can set these values once, globally, and then you set values for specific releases inside your `wantlist.json`
only if they differ from your global settings. The values given for a specific release in your 
`wantlist.json` will override your global values.

The possible optional attributes are as follows:
* `price_threshold`: maximum allowable price (excluding shipping)
* `min_media_condition`: minimum allowable media condition (one of `'P'`, `'F'`, `'G'`, `'G+'`, `'VG'`, `'VG+'`
, `'NM'`, or `'M'`)
* `min_sleeve_condition`: minimum allowable sleeve condition (one of `'P'`, `'F'`, `'G'`, `'G+'`, `'VG'`, `'VG+'`
, `'NM'`, or `'M'`)
* `accept_generic_sleeve`: boolean indicating whether you want to accept a generic sleeve
* `accept_no_sleeve`: boolean indicating whether you want to accept no sleeve
* `accept_ungraded_sleeve`: boolean indicating whether you want to accept an ungraded sleeve

## Usage

As of now, discogs_alert can only be run as a python process. The minimal command required to run the 
discogs_alert service is

```
$ python -m discogs_alert -dt <discogs_access_token> -pt <pushbullet_token> --list-id 12345678
```

where the two _required_ arguments are the values of the two tokens you created earlier, and --list-id 
specifies the ID of your discogs list. This command starts the discogs_alert service, after which it 
regularly pulls the releases from your list, checks their availability on the Discogs marketplace, and 
sends you a notification if any release has gone on sale matching your conditions. You should leave 
the service running in the background at all times to be most effective. Please note that you can add to 
or change the contents of your wantlist while the service is running. The new list of releases will 
come into effect the next time the service runs (i.e. within the next minute).

As an alternative to using a Discogs list id, you can specify the path to a local 
```wantlist.json``` file (explained below). The service works exactly the same in this case, except 
that it pulls releases to look for from that file rather than from a Discogs list. It is required that you 
use exactly one of these two options.

Each time one of your wanted releases is found, your Pushbullet account will be sent a notification 
with the artist and release name, and a URL to the marketplace listing. As long as you 
don't delete the push, you will _not_ be sent repeat notifications for the same listing. 
You should test that the notification system is working correctly by putting a release in your
`wantlist.json` that you know is currently for sale. 

If you want further customisation, there are a number of optional arguments and flags with which 
the service can be run. These optional arguments include the global versions of the conditions 
mentioned above (i.e. the global seller, media, and sleeve conditions) that will be applied to all 
releases in your wantlist by default.

For any of the following arguments, you can use either the abbreviated argument indicator 
(prefixed with `-`) or the verbose option (prefixed with `--`). The complete list of options, 
including options and default values, can be accessed at any time by running:
 
```
$ python -m discogs_alert --help
```

Here are the possible arguments:
 
* `-dt` `--discogs-token`: (str) your discogs user access token
* `-pt` `--pushbullet-token`: (str) your pushbullet token
* `-lid` `--list-id`: (int) the ID of your Discogs list (NB: either this or the ```-wp``` option are required). 
*  `-wp` `--wantlist-path`: (Path) the relative or absolute path to your `wantlist.json` file 
(NB: either this or the ```-lid``` option are required)
* `-f` `--frequency`: (int) how often you want the service to run (number of times per hour). 
This value must be in [1, 60]  (default=`60`, meaning the service runs once a minute)
* `-co` `--country`: (str) the country where you are (used for things like computing shipping) 
(default=`'Germany'`)
* `-$` `--currency`: (str) your preferred currency (default=`EUR`)
* `-msr` `--min-seller-rating`: (float) the minimum seller rating you want to accept 
(default=`95`)
* `-mss` `--min-seller-sales`: (float) the minimum number of sales your accept a seller to have 
(default=`None`)
* `-mmc` `--min-media-condition`: (str) minimum allowable media condition, as outlined above 
(default=`'VG+'`)
* `-msc` `--min-sleeve-condition`: (str) minimum allowable sleeve condition, as outlined above 
(default=`'VG+'`)

And here are the possible flags:
* `-ags`, `--accept-generic-sleeve`: (bool) whether or not you want to accept listings with a 
generic sleeve (default=`false`)
* `-ans`, `--accept-no-sleeve`: (bool) whether or not you want to accept listings with 
no sleeve (default=`false`)
* `-aus`, `--accept-ungraded-sleeve`: (bool) whether or not you want to accept listings with an
ungraded sleeve (default=`false`).
* `-V` `--verbose`: (bool) use this flag if you want to run the server in verbose mode, meaning 
it will print updates to the command line as it runs (default=`false`) 
 
### Full Example

To clarify the CLI outlined above, here is a realistic example. In this case, we are replicating a user 
who has their `wantlist.json` on their Desktop, and who wants verbose printouts from 
the service, no minimum seller rating, and a global minimum media condition of `VG`. The 
command to run the service in this case would be
 
```
$ python -m discogs_alert -dt <discogs_access_token> -pt <pushbullet_token> -wp ~/Desktop/wantlist.json --msr None -mmc VG --verbose
```

### Running in the background

Since this is a service that you'll want to leave running all t time, the best thing to 
do is run it in the background. This way you don't need to leave the process active in your terminal. 
The easiest way to do this (on Linux & Mac) is with the `nohup` command

```
$ nohup python -m discogs_alert -dt <discogs_access_token> -pt <pushbullet_token> &
```

As can be seen, you need to put `nohup` before the python command and `&` after it. All console output 
generated by the service will be saved to a text file named `nohup.out`.

When you run this command, it will return a PID (process ID). You will need this to stop the 
process in the future, which you can easily do by running `$ kill <PID>`. If you forget the 
PID, you can still terminate the service by running

```
$ kill $(ps aux | grep '[p]ython -m discogs_alert' | awk '{print $2}')
```

## Contributing

1. Fork (https://github.com/michaelhball/discogs_alert/fork)
2. Create your feature branch (git checkout -b feature/fooBar)
3. Commit your changes (git commit -am 'Add some fooBar')
4. Push to the branch (git push origin feature/fooBar)
5. Create a new Pull Request

### Setting up the dev environment

Ideally, you should work inside a virtual environment set up for this project. Once that's the case, 
simply run the following two commands to install all dependencies:

* `$ pip install --user poetry`
* `$ poetry install` 

And that's it! Until you want to push your changes and make a PR. When that's the case, you need to run 
the tests to make sure nothing has broken, which you can do by running `$ poetry pytest tests`. 

## Changelog

The complete release history for this project can be found in [CHANGELOG.md](CHANGELOG.md).

## Author

[**Michael Ball**](https://github.com/michaelhball)

<a href="https://mhsb.me" rel="nofollow">
<img alt="home icon" src="https://github.com/michaelhball/discogs_alert/blob/main/img/home.png"/>
</a>

## License

This project is licensed under the GPL License - see the [LICENSE](LICENSE) file for details

## Housekeeping

<div>vinyl icon made by <a href="https://www.flaticon.com/authors/those-icons" title="Those Icons">Those Icons</a> on <a href="https://www.flaticon.com/" title="Flaticon">www.flaticon.com</a></div>
