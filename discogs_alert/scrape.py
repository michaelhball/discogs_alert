import logging
import re
from typing import Optional

import dacite
from bs4 import BeautifulSoup, Tag

from discogs_alert import entities as da_entities
from discogs_alert.util import constants as dac

logger = logging.getLogger(__name__)


class ParsingException(Exception):
    ...


class PriceParsingException(ParsingException):
    ...


CURRENCY_REGEX = r".*?(?:[\£\$\€\¥]{1})"


def _parse_price_string(price_string: str) -> tuple[str, float]:
    """Split a Discogs price string like ``"€10.50"`` or ``"USD 12.00"`` into
    ``(currency_code, value)``.

    Discogs renders prices either with a symbol prefix (`€`, `£`, `$`, `¥`, plus
    qualified variants like `A$`, `CA$`, `R$`) or with a 3-letter ISO code prefix
    (e.g. `SEK 100.00`) when the symbol is ambiguous. We try the symbol form
    first via `CURRENCY_REGEX`, then fall back to scanning for a known ISO code.

    Args:
        price_string: a stripped, comma-free price representation.

    Returns:
        ``(iso_code, numeric_value)``.

    Raises:
        PriceParsingException: if neither a known symbol nor an ISO code is found,
        or if the numeric portion can't be parsed as a float.
    """

    price_currency, price_value = None, None
    try:
        price_currency = re.findall(CURRENCY_REGEX, price_string)[0]
        price_value = price_string.replace(price_currency, "")
    except IndexError:
        for currency in dac.NON_SYMBOL_CURRENCIES:
            if currency in price_string:
                price_currency = currency
                price_value = price_string.replace(currency, "")
                break

    if price_currency is None:
        raise PriceParsingException(f"Couldn't parse {price_string}")

    try:
        numeric_value = float(price_value)
    except (TypeError, ValueError) as exc:
        raise PriceParsingException(f"Couldn't parse numeric value from {price_string!r}") from exc

    return dac.CURRENCIES[price_currency], numeric_value


def _first_text(elt: Optional[Tag]) -> str:
    """Return the first stripped text child of `elt`, or ``""`` if there isn't one.

    Defensive replacement for ``elt.contents[0].strip()`` which IndexErrors on
    empty tags (e.g. ``<p></p>``).
    """

    if elt is None:
        return ""
    text = elt.get_text(strip=True) if isinstance(elt, Tag) else str(elt).strip()
    return text


def _parse_shipping(shipping_text: str) -> Optional[dict]:
    """Try hard to extract a shipping price + currency from the (often messy)
    Discogs shipping span text.

    Returns ``{"currency": <iso>, "value": <float>}`` or ``None`` if the text
    has no parseable price (e.g. ``"+free shipping"``, ``"+about shipping"``).

    Handles symbol-prefixed amounts and ISO-code-prefixed amounts.
    """

    cleaned = shipping_text.strip().replace("+", "").replace(",", "").strip()
    if not cleaned:
        return None

    # Drop common noise words so the remainder is easier to parse.
    for word in ("shipping", "about", "free"):
        cleaned = cleaned.replace(word, "")
    cleaned = cleaned.strip()

    if not cleaned:
        return None

    try:
        currency, value = _parse_price_string(cleaned)
        return {"currency": currency, "value": value}
    except PriceParsingException:
        return None


def scrape_listings_from_marketplace(response_content: str, release_id: int) -> da_entities.Listings:
    """Takes response from marketplace get request (for single release) and parses
    the important listing information.

    Args:
        response_content: content of response from release marketplace GET request
        release_id: the ID of the release, used only for informative logging

    Returns:
        List of `Listing` objects containing information about each listing for sale.
        Listings the parser can't fully understand are skipped (and logged) rather
        than crashing the whole batch.
    """

    listings: da_entities.Listings = []

    soup = BeautifulSoup(response_content, "html.parser")
    listings_table = soup.find("table", class_="mpitems")
    if listings_table is None:
        logger.info("No mpitems table found for release %s; returning empty list", release_id)
        return listings

    tbody = listings_table.find("tbody")
    if tbody is None:
        return listings

    for row in tbody.find_all("tr"):
        try:
            listing = _parse_listing_row(row, release_id)
        except (ParsingException, IndexError, AttributeError, ValueError) as exc:
            logger.warning("Skipping a listing for release %s: %s", release_id, exc)
            continue
        if listing is not None:
            listings.append(listing)

    return sorted(listings, key=lambda x: x.price.value)


def _parse_listing_row(row: Tag, release_id: int) -> Optional[da_entities.Listing]:
    """Parse one ``<tr>`` of the marketplace listings table into a `Listing`.

    Returns `None` if the row isn't a real listing (e.g. doesn't carry a
    "Ships From:" tag — that's typically scam-flagged listings we should skip
    quietly).
    """

    listing: dict = {}

    item_desc_cell = row.find("td", class_="item_description")
    seller_info_cell = row.find("td", class_="seller_info")
    item_price_cell = row.find("td", class_="item_price")
    if item_desc_cell is None or seller_info_cell is None or item_price_cell is None:
        return None

    # Listing ID — derived from the listing's link.
    anchor = item_desc_cell.find("a")
    if anchor is None or "href" not in anchor.attrs:
        return None
    listing_url = anchor["href"]
    listing["id"] = int(listing_url.split("/")[-1].split("?")[0])

    paragraphs = item_desc_cell.find_all("p")
    num_paragraphs = len(paragraphs)

    # When `paragraphs` has 4 entries, the first is a hidden "Unavailable in
    # <country>" notice; otherwise the listing is available everywhere.
    listing["availability"] = None
    if num_paragraphs == 4:
        listing["availability"] = _first_text(paragraphs[0]) or None

    item_condition_para = item_desc_cell.find("p", class_="item_condition")
    if item_condition_para is None:
        return None

    conditions = [
        da_entities.CONDITION_PARSER[s]
        for s in item_condition_para.stripped_strings
        if s in da_entities.CONDITION_PARSER
    ]
    if not conditions:
        return None
    # If sleeve condition is missing, fall back to NOT_GRADED.
    conditions.append(da_entities.CONDITION.NOT_GRADED)
    listing["media_condition"] = conditions[0]
    listing["sleeve_condition"] = conditions[1]

    # Seller's comment is the last paragraph; safe to be empty.
    listing["comment"] = _first_text(paragraphs[-1]) if paragraphs else ""

    # Seller metadata — second span is either "New seller" or contains the rating.
    spans = seller_info_cell.find_all("span")
    is_new_seller = len(spans) >= 2 and _first_text(spans[1]) == "New seller"
    if is_new_seller:
        listing["seller_num_ratings"] = 0
        listing["seller_avg_rating"] = None
    else:
        anchors = seller_info_cell.find_all("a")
        strongs = seller_info_cell.find_all("strong")
        if len(anchors) < 2 or len(strongs) < 2:
            return None
        ratings_text = _first_text(anchors[1])
        try:
            listing["seller_num_ratings"] = int(ratings_text.split()[0].replace(",", ""))
        except (IndexError, ValueError):
            return None
        rating_text = _first_text(strongs[1])
        try:
            listing["seller_avg_rating"] = float(rating_text.strip().split("%")[0])
        except (IndexError, ValueError):
            return None

    ships_from_label = seller_info_cell.find("span", string="Ships From:")
    if ships_from_label is None or ships_from_label.parent is None:
        # No "Ships From:" — typically a scam listing; skip quietly.
        return None
    try:
        listing["seller_ships_from"] = ships_from_label.parent.contents[1].strip()
    except IndexError:
        return None

    # Price & shipping.
    price_span = item_price_cell.find("span", class_="price")
    if price_span is None:
        return None
    price_text_pieces = [elt for elt in price_span.contents if elt.name is None]
    if not price_text_pieces:
        return None
    price_string = price_text_pieces[0].strip().replace("+", "").replace(",", "")
    try:
        currency, value = _parse_price_string(price_string)
    except PriceParsingException as exc:
        raise ParsingException(
            f"Couldn't parse price {price_string!r} for release {release_id}"
        ) from exc
    listing["price"] = {"currency": currency, "value": value}

    shipping_span = item_price_cell.find("span", class_="item_shipping")
    if shipping_span is not None:
        shipping_pieces = [elt for elt in shipping_span.contents if elt.name is None]
        if shipping_pieces:
            shipping = _parse_shipping(shipping_pieces[0])
            if shipping is not None:
                listing["price"]["shipping"] = shipping

    return dacite.from_dict(da_entities.Listing, listing)
