from typing import Dict, Set

AlertDict = Dict[str, Set[str]]


class Alerter:
    def __init__(self):
        ...

    def get_all_alerts(self) -> AlertDict:
        """Returns a list of all alerts previously sent s.t. they can be searched to avoid duplicates."""
        raise NotImplementedError

    def send_alert(self, message_title: str, message_body: str):
        """Returns a list of all alerts previously sent s.t. they can be searched to avoid duplicates."""
        raise NotImplementedError
