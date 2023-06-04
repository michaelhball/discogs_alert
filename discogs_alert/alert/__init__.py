import enum
from typing import Any, Dict

from discogs_alert.alert.base import Alerter
from discogs_alert.alert.pushbullet import PushbulletAlerter
from discogs_alert.alert.telegram import TelegramAlerter


@enum.unique
class AlerterType(enum.IntEnum):
    PUSHBULLET = enum.auto()
    TELEGRAM = enum.auto()


def get_alerter(alerter_type: AlerterType, alerter_kwargs: Dict[str, Any]) -> Alerter:
    if alerter_type == AlerterType.PUSHBULLET:
        alerter_cls = PushbulletAlerter
    elif alerter_type == AlerterType.TELEGRAM:
        alerter_cls = TelegramAlerter
    else:
        raise ValueError("`alerter_type` must be a valid AlerterType value")

    return alerter_cls(**alerter_kwargs)
