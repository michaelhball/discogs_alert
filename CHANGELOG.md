# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

* Different notification options (SMS, Email, Slack)
* Seller location controls (blacklists & whitelists)
* Integration with your actual Discogs wantlist (e.g. pulling from one of your discogs lists 
list).
* Ability to run service using Docker or daemon service.
* ... 

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
