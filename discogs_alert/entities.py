import enum
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from discogs_alert.util import currency as da_currency


@enum.unique
class CONDITION(enum.IntEnum):
    NOT_GRADED = -3
    NO_COVER = -2
    GENERIC = -1
    POOR = 0
    FAIR = 1
    GOOD = 2
    GOOD_PLUS = 3
    VERY_GOOD = 4
    VERY_GOOD_PLUS = 5
    NEAR_MINT = 6
    MINT = 7


CONDITION_PARSER = {
    "Not Graded": CONDITION.NOT_GRADED,
    "No Cover": CONDITION.NO_COVER,
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


@dataclass
class Release:
    """An entity that represents a record the user is searching for."""

    id: int

    # artist & track name
    display_title: str

    # optional args from from `wantlist.json`
    min_media_condition: Optional[CONDITION] = None
    min_sleeve_condition: Optional[CONDITION] = None
    price_threshold: Optional[int] = None

    # optional args from Discogs list
    comment: Optional[str] = None
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
class ShippingPrice:
    currency: str
    value: float

    def convert_currency(self, new_currency: str) -> "ShippingPrice":
        if self.currency != new_currency:
            self.value = da_currency.convert_currency(self.value, self.currency, new_currency)
            self.currency = new_currency
        return self


@dataclass
class ListingPrice:
    currency: str
    value: float
    shipping: Optional[ShippingPrice] = None

    def convert_currency(self, new_currency: str) -> "ListingPrice":
        if self.currency != new_currency:
            self.value = da_currency.convert_currency(self.value, self.currency, new_currency)
            self.currency = new_currency
        if self.shipping is not None:
            self.shipping = self.shipping.convert_currency(new_currency)
        return self


@dataclass
class Listing:
    """An entity representing a specific instance of a record for sale on the Discogs marketplace."""

    id: int
    availability: Optional[str]  # sometimes can't be parsed (if the seller didn't set this attribute)
    media_condition: CONDITION
    sleeve_condition: CONDITION
    comment: str
    seller_num_ratings: int
    seller_avg_rating: Optional[float]  # None if new seller
    seller_ships_from: str
    price: ListingPrice

    @property
    def total_price(self) -> float:
        return self.price.value if self.price.shipping is None else self.price.value + self.price.shipping.value

    @property
    def url(self) -> float:
        return f"https://www.discogs.com/sell/item/{self.id}"

    def is_definitely_unavailable(self, country: str) -> bool:
        return self.availability == f"Unavailable in {country}"

    def price_is_above_threshold(self, price_threshold: Optional[float] = None) -> bool:
        return price_threshold is not None and self.total_price > price_threshold

    def convert_currency(self, new_currency: str) -> "Listing":
        self.price = self.price.convert_currency(new_currency)
        return self


Listings = List[Listing]


def conditions_satisfied(
    listing: Listing,
    release: Release,
    seller_filters: SellerFilters,
    record_filters: RecordFilters,
    country_whitelist: Set[str],
    country_blacklist: Set[str],
):
    """Validates that a given listing satisfies all conditions and filters, including both global filters
    (set via environment variables or via the CLI at runtime) and per-release filters (set in wantlist.json).

    Args:
        listing: the listing to validate
        release: the release object, defined by the user, corresponding to the given listing
        seller_filters: the global seller filters
        record_filters: the global record (media & sleeve condition) filters
        country_whitelist: a list of countries from which we will consider listings as valid
        country_blacklist: a list of countries from which to consider listings as invalid

    Returns: True if the given listing satisfies all conditions, False otherwise.
    """

    # verify country whitelist & blacklist, if used
    if country_whitelist and listing.seller_ships_from not in country_whitelist:
        return False
    if country_blacklist and listing.seller_ships_from in country_blacklist:
        return False

    # verify seller conditions
    if (
        listing.seller_avg_rating is not None
        and seller_filters.min_seller_rating is not None
        and listing.seller_avg_rating < seller_filters.min_seller_rating
    ):
        return False
    if (
        seller_filters.min_seller_sales is not None
        and listing.seller_num_ratings is not None
        and listing.seller_num_ratings < seller_filters.min_seller_sales
    ):
        return False

    # verify media condition, either globally or for this specific release
    if listing.media_condition < (release.min_media_condition or record_filters.min_media_condition):
        return False

    # optionally sleeve condition, either globally or for this specific release
    if listing.sleeve_condition < (release.min_sleeve_condition or record_filters.min_sleeve_condition):
        return False

    return True
