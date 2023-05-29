import logging
import re

import dacite
from bs4 import BeautifulSoup

from discogs_alert import entities as da_entities
from discogs_alert.util import constants as dac

logger = logging.getLogger(__name__)


class ParsingException(Exception):
    ...


class PriceParsingException(ParsingException):
    ...


CURRENCY_REGEX = r".*?(?:[\£\$\€\¥]{1})"


def _parse_price_string(price_string: str) -> tuple[dac.CURRENCIES, float]:
    """TODO: docstring"""

    price_currency, price_value = None, None
    try:
        price_currency = re.findall(CURRENCY_REGEX, price_string)[0]
        price_value = price_string.replace(price_currency, "")
    except IndexError:
        for currency in dac.NON_SYMBOL_CURRENCIES:
            if currency in price_string:
                price_currency = currency
                price_value = price_string.replace(currency, "")

    if price_currency is None:
        raise PriceParsingException(f"Couldn't parse {price_string}")

    return dac.CURRENCIES[price_currency], float(price_value)


def scrape_listings_from_marketplace(response_content: str, release_id: int) -> da_entities.Listings:
    """Takes response from marketplace get request (for single release) and parses
    the important listing information.

    Args:
        response_content: content of response from release marketplace GET request
        release_id: the ID of the release, used only for informative logging

    Returns: List of `Listing` objects containing information about each listing for sale.
    """

    listings = []

    soup = BeautifulSoup(response_content, "html.parser")

    listings_table = soup.find("table", class_="mpitems")

    # each row is a single listing
    rows = listings_table.find("tbody").find_all("tr")
    for row in rows:
        listing = {}

        item_desc_cell = row.find("td", class_="item_description")
        seller_info_cell = row.find("td", class_="seller_info")
        item_price_cell = row.find("td", class_="item_price")

        # get the listing ID
        listing_url = item_desc_cell.find("a")["href"]
        listing["id"] = int(listing_url.split("/")[-1].split("?")[0])

        paragraphs = item_desc_cell.find_all("p")
        num_paragraphs = len(paragraphs)

        # extract listing availability. If there are 4 paragraphs, the first is a
        # hidden para containing the string "Unavailable in <country>"
        listing["availability"] = None
        if num_paragraphs == 4:
            listing["availability"] = paragraphs[0].contents[0].strip()

        item_condition_para = item_desc_cell.find("p", class_="item_condition")

        # extract conditions of media (always listed) and sleeve (optional)
        conditions = (da_entities.CONDITION_PARSER.get(s) for s in item_condition_para.stripped_strings)
        conditions = [c for c in conditions if c is not None]
        # in case of missing sleeve condition
        conditions.append(da_entities.CONDITION.NOT_GRADED)
        listing["media_condition"] = conditions[0]
        listing["sleeve_condition"] = conditions[1]

        # the seller's comment is the last paragraph (doesn't have a nice class name)
        seller_comment = paragraphs[-1].contents[0].strip()
        listing["comment"] = seller_comment

        # extract seller info (num ratings, average rating, & country ships from)
        is_new_seller = str(seller_info_cell.find_all("span")[1].contents[0]).strip() == "New seller"
        if is_new_seller:
            listing["seller_num_ratings"] = 0
            listing["seller_avg_rating"] = None
        else:
            # the first 'a' element is the link to then seller, this one is the link to their reviewings
            # we just extract the text content from that link
            seller_num_ratings_elt = seller_info_cell.find_all("a")[1].contents[0]
            listing["seller_num_ratings"] = int(seller_num_ratings_elt.split()[0].replace(",", "").strip())

            # the seller rating is the second bold thing (their name is also in bold).
            seller_avg_rating_elt = seller_info_cell.find_all("strong")[1].contents[0]
            listing["seller_avg_rating"] = float(seller_avg_rating_elt.strip().split("%")[0])

        try:
            listing["seller_ships_from"] = seller_info_cell.find("span", text="Ships From:").parent.contents[1].strip()
        except IndexError:
            # if we get an IndexError here it means the listing had no "Ships From:" country, => we don't continue
            # parsing. The only times I've seen such listings in the past were scams...
            continue

        # extract price & shipping information
        price_spans = item_price_cell.find("span", class_="price")
        price_string: str = (
            [elt for elt in price_spans.contents if elt.name is None][0].strip().replace("+", "").replace(",", "")
        )
        try:
            currency, value = _parse_price_string(price_string)
            listing["price"] = {"currency": currency, "value": value}
        except PriceParsingException:
            raise ParsingException(f"Couldn't parse currency from price_string {price_string} for release {release_id}")

        shipping_string = item_price_cell.find("span", class_="item_shipping").contents[0].strip().replace("+", "")
        shipping_currency_matches = re.findall(CURRENCY_REGEX, shipping_string)
        shipping_currency = shipping_currency_matches[0] if len(shipping_currency_matches) > 0 else None
        if shipping_currency is not None:
            shipping_string = shipping_string.replace(shipping_currency, "").replace(",", "")
            listing["price"]["shipping"] = {
                "currency": dac.CURRENCIES[shipping_currency],
                "value": float(shipping_string),
            }

        listings.append(dacite.from_dict(da_entities.Listing, listing))

    return sorted(listings, key=lambda x: x.price.value)
