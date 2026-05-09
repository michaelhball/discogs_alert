"""Domain models for `discogs_alert`.

All entities are pydantic v2 `BaseModel`s. We migrated from `dacite` + dataclass
in #N because:

- `dacite` is slow (~50× slower than pydantic for our shapes).
- `dacite` doesn't auto-coerce ints into IntEnum members; you had to set
  ``cast=[CONDITION]`` at every call site, which we kept forgetting (cf. the
  `get_listing` bug from #86).
- Pydantic gives us validation with sharp error messages whenever Discogs
  changes their JSON shape, instead of silent `KeyError`s deep inside the loop.
- Pydantic supports recursive nested-model parsing out of the box, so the
  ``Listing(**dict)`` flat-construction class of bugs is gone.

Construction: ``Release.model_validate(dict)`` (replaces
``dacite.from_dict(Release, dict)``). Direct kwarg construction
(``Release(id=1, display_title="X", …)``) still works.
"""

from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict

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


class _Base(BaseModel):
    """Shared pydantic config for all of our entities.

    - `extra="ignore"`: API responses contain fields we don't model; drop them
      silently rather than raising (matches the old dacite behaviour).
    - `arbitrary_types_allowed=False`: every field must be a known type; catches
      typos at definition time.
    """

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)


class SellerFilters(_Base):
    min_seller_rating: Optional[float] = None
    min_seller_sales: Optional[int] = None


class RecordFilters(_Base):
    min_media_condition: Optional[CONDITION] = None
    min_sleeve_condition: Optional[CONDITION] = None


class Release(_Base):
    """A record the user is searching for."""

    id: int
    display_title: str

    # Optional per-release filters (from `wantlist.json` keys, or
    # `@key=value` directives in a Discogs list-item comment). Threshold is a
    # float because internal currency conversion produces non-integer values;
    # whole-number inputs (the common case) coerce automatically.
    min_media_condition: Optional[CONDITION] = None
    min_sleeve_condition: Optional[CONDITION] = None
    price_threshold: Optional[float] = None

    # Other fields that come back from the Discogs list API (mostly ignored
    # by us but stored so we can round-trip).
    comment: Optional[str] = None
    uri: Optional[str] = None
    resource_url: Optional[str] = None
    image_url: Optional[str] = None
    type: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None


class UserList(_Base):
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


class ShippingPrice(_Base):
    currency: str
    value: float

    def convert_currency(self, new_currency: str) -> "ShippingPrice":
        if self.currency != new_currency:
            self.value = da_currency.convert_currency(self.value, self.currency, new_currency)
            self.currency = new_currency
        return self


class ListingPrice(_Base):
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


class ReleaseStats(_Base):
    """Lightweight summary returned by ``GET /marketplace/stats/{release_id}``.

    `lowest_price` is the cheapest listing currently for sale, in the user's
    Discogs-account currency setting. Populated only when `num_for_sale > 0`.
    """

    num_for_sale: int
    lowest_price: Optional[ShippingPrice] = None
    blocked_from_sale: bool = False


class Listing(_Base):
    """A specific instance of a record for sale on the Discogs marketplace."""

    id: int
    availability: Optional[str] = None  # absent if the seller didn't set this attribute
    media_condition: CONDITION
    sleeve_condition: CONDITION
    comment: str
    seller_num_ratings: int
    seller_avg_rating: Optional[float] = None  # None if new seller
    seller_ships_from: str
    price: ListingPrice

    @property
    def total_price(self) -> float:
        return self.price.value if self.price.shipping is None else self.price.value + self.price.shipping.value

    @property
    def url(self) -> str:
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
) -> bool:
    """Validate that a given listing satisfies all configured filters, including
    both globals (CLI flags / env vars) and per-release overrides (wantlist.json
    fields or Discogs list comment directives).
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
