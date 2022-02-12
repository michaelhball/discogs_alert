from dataclasses import dataclass
import enum
from typing import Any, Dict, List, NamedTuple, Optional


# TODO: convert all NamedTuples to dataclasses ???


@enum.unique
class CONDITION(enum.IntEnum):
    POOR = 0
    FAIR = 1
    GOOD = 2
    GOOD_PLUS = 3
    VERY_GOOD = 4
    VERY_GOOD_PLUS = 5
    NEAR_MINT = 6
    MINT = 7


@dataclass
class Release:
    id: int
    comment: str

    # artist & track name
    display_title: str

    # optional args from from `wantlist.json`
    min_media_condition: Optional[CONDITION] = None
    min_sleeve_condition: Optional[CONDITION] = None
    accept_generic_sleeve: Optional[bool] = None
    accept_no_sleeve: Optional[bool] = None
    accept_ungraded_sleeve: Optional[bool] = None
    price_threshold: Optional[int] = None

    # optional args from Discogs list
    uri: Optional[str] = None
    resource_url: Optional[str] = None
    image_url: Optional[str] = None
    type: Optional[str] = None
    stats: Optional[Dict] = None


class UserList(NamedTuple):
    id: int
    user: Dict[str, Any]
    name: str
    description: str
    public: bool
    date_added: str
    date_changed: str
    uri: str
    resource_url: str
    image_url: str
    items: List[Release]


@dataclass
class ReleaseStats:
    num_for_sale: int
    lowest_price: Optional[float] = None
    blocked_from_sale: bool = False


class Shipping(NamedTuple):
    currency: str
    value: float


# TODO: put some Optionals in here for stuff that might not exist
class ListingPrice(NamedTuple):
    currency: str
    value: float
    shipping: Shipping


class Listing(NamedTuple):
    id: str
    media_condition: CONDITION
    sleeve_condition: CONDITION
    comment: str
    seller_num_ratings: int
    seller_avg_rating: float
    seller_ships_from: str
    price: ListingPrice
