# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

* Different notification options (SMS, Email, Slack)
* Seller location controls (blacklists & whitelists)
* Filter options when using a discogs list (equivalent functionality to wantlist.json)

## [0.0.9] — 2022.04.20

### Fixed
* currency API bug
* Japanese Yen shipping currency parsing bug
* Major bug in checking whether `conditions_satisfied`
* several `scrape.py` bugs
* removed noisy webdriver-manager logs

### Added
* Docker support!
* Documentation for running as a cron job
* Scraping robustness improvements
* Better within-loop logging

## [0.0.7] — 2022.02.18

### Fixed
* Fixed fake-useragent HTML-parsing bug
* Fixed Discogs-list-as-wantlist functionality

### Added
* _Major_ codebase refactor
* Updated dependencies

## [0.0.6] — 2021.08.08

### Fixed
* 3rd party exchange rate API service shut down; now using a new one
* Fixed bug converting currencies for item values >1000

## [0.0.5] — 2021.05.17
### Fixed
* Fixed 403 authentication bug (by modifying clients to use rotating user-agents + Selenium)

## [0.0.3] — 2021.04.26
### Added
* Added option to load wantlist from a Discogs list (rather than from ```wantlist.json``` file).

### Fixed
* Fixed 403 authentication bug (caused by not passing user agent correctly w. marketplace queries)
* Fixed bug when release has no sleeve condition

## [0.0.2] - 2021-02-19
### Added
* Python program that runs a service on a schedule. The service: 
  * reads wanted releases from a JSON file
  * searches for them on the Discogs marketplace at regular intervals
  * notifies user using Pushbullet if any of their records are available  
  * allows for custom filters both globally and per-release, specifying seller criteria 
  or criteria about the media/sleeve of a release 

[Unreleased]: https://github.com/michaelhball/discogs_alert/compare/v0.0.2...HEAD
[0.0.2]: https://github.com/michaelhball/discogs_alert/releases/tag/v0.0.2
