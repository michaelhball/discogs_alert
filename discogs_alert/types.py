import enum
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@enum.unique
class CONDITION(enum.IntEnum):
    GENERIC: -1
    POOR = 0
    FAIR = 1
    GOOD = 2
    GOOD_PLUS = 3
    VERY_GOOD = 4
    VERY_GOOD_PLUS = 5
    NEAR_MINT = 6
    MINT = 7


CONDITION_PARSER = {
    "Generic": CONDITION.GENERIC,
    "Poor (P)": CONDITION.POOR,
    "Fair (F)": CONDITION.FAIR,
    "Good (G)": CONDITION.GOOD,
    "Good Plus (G+)": CONDITION.GOOD_PLUS,
    "Very Good (VG)": CONDITION.VERY_GOOD,
    "Very Good Plus (VG+)": CONDITION.VERY_GOOD_PLUS,
    "Near Mint (NM or M-)": CONDITION.NEAR_MINT,
    "Mint (M)": CONDITION.MINT,
}


@dataclass
class SellerFilters:
    min_seller_rating: Optional[float] = None
    min_seller_sales: Optional[int] = None


@dataclass
class RecordFilters:
    min_media_condition: Optional[CONDITION] = None
    min_sleeve_condition: Optional[CONDITION] = None
    accept_generic_sleeve: Optional[bool] = None
    accept_no_sleeve: Optional[bool] = None
    accept_ungraded_sleeve: Optional[bool] = None


@dataclass
class Release:
    """An entity that represents a record the user is searching for."""

    id: int
    comment: str

    # artist & track name
    display_title: str

    # optional args from from `wantlist.json`
    # TODO: convert these to a `RecordFilters` object ??
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


@dataclass
class UserList:
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


@dataclass
class Shipping:
    currency: str
    value: float


@dataclass
class ListingPrice:
    currency: str
    value: float
    shipping: Optional[Shipping] = None


@dataclass
class Listing:
    """An entity that represents a specific instance of a record for sale (found on the marketplace)"""

    id: int
    availability: str
    media_condition: CONDITION
    sleeve_condition: CONDITION
    comment: str
    seller_num_ratings: int
    seller_avg_rating: Optional[float]  # None if new seller
    seller_ships_from: str
    price: ListingPrice


Listings = List[Listing]


CURRENCY_CHOICES = {
    "EUR",
    "GBP",
    "HKD",
    "IDR",
    "ILS",
    "DKK",
    "INR",
    "CHF",
    "MXN",
    "CZK",
    "SGD",
    "THB",
    "HRK",
    "MYR",
    "NOK",
    "CNY",
    "BGN",
    "PHP",
    "SEK",
    "PLN",
    "ZAR",
    "CAD",
    "ISK",
    "BRL",
    "RON",
    "NZD",
    "TRY",
    "JPY",
    "RUB",
    "KRW",
    "USD",
    "HUF",
    "AUD",
}


CURRENCIES = {
    "€": "EUR",
    "£": "GBP",
    "$": "USD",
    "¥": "JPY",
    "A$": "AUD",
    "CA$": "CAD",
    "MX$": "MXN",
    "NZ$": "NZD",
    "B$": "BRL",
    "CHF": "CHF",
    "SEK": "SEK",
    "ZAR": "ZAR",
}
