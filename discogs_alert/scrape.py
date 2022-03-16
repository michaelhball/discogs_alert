import re

import dacite
from bs4 import BeautifulSoup

from discogs_alert import types as da_types


def scrape_listings_from_marketplace(response_content: str) -> da_types.Listings:
    """Takes response from marketplace get request (for single release) and parses
    the important listing information.

    Args:
        response_content: content of response from release marketplace GET request

    Returns: List of `Listing` objects containing information about each listing for sale.
    """

    listings = []

    soup = BeautifulSoup(response_content, "html.parser")

    listings_table = soup.find_all("table")[3]  # [2] = tracklist, [1] = top page header info, [0] = header-header
    rows = listings_table.find("tbody").find_all("tr")
    for row in rows:
        listing = {}
        cells = row.find_all("td")

        # extract listing ID
        a_elements = cells[0].find_all("a")
        listing_href = a_elements[0]["href"]
        listing["id"] = int(listing_href.split("/")[-1].split("?")[0])

        paragraphs = cells[1].find_all("p")
        num_paragraphs = len(paragraphs)

        # extract listing availability
        listing["availability"] = None
        if num_paragraphs == 4:
            listing["availability"] = paragraphs[0].contents[0].strip()

        # extract media & sleeve condition
        condition_idx = 1 if num_paragraphs == 3 else 2
        condition_paragraph = paragraphs[condition_idx]

        media_condition_tooltips = condition_paragraph.find(class_="media-condition-tooltip")
        media_condition = media_condition_tooltips.get("data-condition")
        listing["media_condition"] = da_types.CONDITION_PARSER[media_condition]

        sleeve_condition_spans = condition_paragraph.find("span", class_="item_sleeve_condition")
        if sleeve_condition_spans is not None:
            sleeve_condition = sleeve_condition_spans.contents[0].strip()
            sleeve_condition = da_types.CONDITION_PARSER[sleeve_condition]
        else:
            sleeve_condition = None
        listing["sleeve_condition"] = sleeve_condition

        seller_comment_idx = 2 if num_paragraphs == 3 else 3
        seller_comment = paragraphs[seller_comment_idx].contents[0].strip()  # TODO: be more sophisticated
        listing["comment"] = seller_comment

        # extract seller info (num ratings, average rating, & country ships from)
        is_new_seller = str(cells[2].find_all("span")[1].contents[0]).strip() == "New seller"
        if is_new_seller:
            listing["seller_num_ratings"] = 0
            listing["seller_avg_rating"] = None
        else:
            seller_num_ratings_elt = cells[2].find_all("a")[1].contents[0]
            if "ratings" in seller_num_ratings_elt:
                seller_num_ratings_elt = seller_num_ratings_elt.replace("ratings", "")
            elif "rating" in seller_num_ratings_elt:
                seller_num_ratings_elt = seller_num_ratings_elt.replace("rating", "")
            listing["seller_num_ratings"] = int(seller_num_ratings_elt.replace(",", "").strip())
            listing["seller_avg_rating"] = float(cells[2].find_all("strong")[1].contents[0].strip().split(".")[0])
        listing["seller_ships_from"] = cells[2].find("span", text="Ships From:").parent.contents[1].strip()

        # extract price & shipping information
        currency_regex = ".*?(?:[\£\$\€]{1})"
        price_spans = cells[4].find("span", class_="price")
        price_string = (
            [elt for elt in price_spans.contents if elt.name is None][0].strip().replace("+", "").replace(",", "")
        )
        price_currency = re.findall(currency_regex, price_string)[0]
        price_string = price_string.replace(price_currency, "")
        listing["price"] = {"currency": da_types.CURRENCIES[price_currency], "value": float(price_string)}

        shipping_string = cells[4].find("span", class_="item_shipping").contents[0].strip().replace("+", "")
        shipping_currency_matches = re.findall(currency_regex, shipping_string)
        shipping_currency = shipping_currency_matches[0] if len(shipping_currency_matches) > 0 else None
        if shipping_currency is not None:
            shipping_string = shipping_string.replace(shipping_currency, "")
            listing["price"]["shipping"] = {
                "currency": da_types.CURRENCIES[shipping_currency],
                "value": float(shipping_string),
            }

        listings.append(dacite.from_dict(da_types.Listing, listing))

    return sorted(listings, key=lambda x: x.price.value)
