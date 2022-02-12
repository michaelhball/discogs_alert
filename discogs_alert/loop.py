import json
import time

from pathlib import Path
from requests.exceptions import ConnectionError

from discogs_alert import client as da_client, notify as da_notify, types as da_types, util as da_util


# TODO: move parts of this to separate functions, e.g. the media/sleeve quality part can be one etc.


def loop(
    discogs_token: str,
    pushbullet_token: str,
    list_id: int,
    wantlist_path: str,
    user_agent: str,
    country: str,
    currency: str,
    min_seller_rating: int,
    min_seller_sales: int,
    min_media_condition: da_types.CONDITION,
    min_sleeve_condition: da_types.CONDITION,
    accept_generic_sleeve: bool,
    accept_no_sleeve: bool,
    accept_ungraded_sleeve: bool,
    verbose: bool = False,
):
    """Event loop, each time this is called we query the discogs marketplace for all items in wantlist."""

    start_time = time.time()
    if verbose:
        print("\nrunning loop")

    # TODO: fix this ??
    mmc = da_util.CONDITIONS[min_media_condition]
    msc = da_util.CONDITIONS[min_sleeve_condition]

    try:
        currency_rates = da_util.get_currency_rates(currency)
        client_anon = da_client.AnonClient(user_agent)
        user_token_client = da_client.UserTokenClient(user_agent, discogs_token)

        if list_id is not None:
            wantlist = user_token_client.get_list(list_id).items
        else:
            # TODO: fix this to load things in the correct type
            wantlist = json.load(Path(wantlist_path).open("r"))

        for release in wantlist:
            release = da_types.Release(**release)
            release_id = release.id

            # TODO: clean up this, super non-interpretable as I read through
            # parameter values for current release only (if set by user)
            temp_mmc = release.min_media_condition
            temp_msc = release.min_sleeve_condition
            temp_ags = release.accept_generic_sleeve
            temp_ans = release.accept_no_sleeve
            temp_aus = release.accept_ungraded_sleeve
            price_threshold = release.price_threshold

            valid_listings = []
            release_stats = user_token_client.get_release_stats(release_id)
            print(release_stats)
            return
            if release_stats:
                if release_stats.get("num_for_sale") > 0 and not release_stats.get("blocked_from_sale", False):
                    for listing in client_anon.get_marketplace_listings(release_id):

                        # verify availability
                        if listing.get("availability") == f"Unavailable in {country}":
                            continue

                        # verify seller conditions
                        if listing.get("seller_avg_rating") is not None:  # None if new seller
                            if min_seller_rating is not None and listing["seller_avg_rating"] < min_seller_rating:
                                continue
                        if min_seller_sales is not None and listing["seller_num_ratings"] < min_seller_sales:
                            continue

                        # verify media condition
                        this_iter_mmc = da_util.CONDITIONS[temp_mmc] if temp_mmc is not None else mmc
                        if da_util.CONDITIONS[listing["media_condition"]] < this_iter_mmc:
                            continue

                        ags = temp_ags if temp_ags is not None else accept_generic_sleeve
                        good_generic_sleeve = ags and listing["sleeve_condition"] == "Generic"
                        ans = temp_ans if temp_ans is not None else accept_no_sleeve
                        good_no_sleeve = ans and listing.get("sleeve_condition") in {"No Cover", None}
                        aus = temp_aus if temp_aus is not None else accept_ungraded_sleeve
                        good_ungraded_sleeve = aus and listing.get("sleeve_condition") == "Not Graded"

                        # we only check min_sleeve_condition if we've not't satisfied one of the other conditions
                        if not any({good_generic_sleeve, good_no_sleeve, good_ungraded_sleeve}):
                            this_iter_min_sleeve_condition = (
                                da_util.CONDITIONS[temp_msc] if temp_msc is not None else msc
                            )
                            if da_util.CONDITIONS[listing["sleeve_condition"]] < this_iter_min_sleeve_condition:
                                continue

                        # convert listing price & shipping --> base currency
                        price = listing["price"]
                        print(price)
                        if price["currency"] != currency:
                            converted_price = da_util.convert_currency(
                                price.get("currency"), price.get("value"), currency_rates
                            )
                            listing["price"]["currency"] = currency
                            listing["price"]["value"] = converted_price

                        shipping = price.get("shipping")
                        if shipping is not None:
                            if shipping.get("currency") != currency:
                                converted_shipping = da_util.convert_currency(
                                    shipping.get("currency"), shipping.get("value"), currency_rates
                                )
                                listing["price"]["shipping"] = {"currency": currency, "value": converted_shipping}

                        # use price threshold if we have one
                        total_price = float(listing["price"]["value"].replace(",", ""))
                        if price_threshold is not None and total_price > price_threshold:
                            continue

                        valid_listings.append(listing)

            else:
                # TODO: handle if something went wrong getting release stats
                continue

            # if we found something, send notification
            if len(valid_listings) > 0:
                listing_to_post = valid_listings[0]
                if list_id is not None:
                    m_title = f"Now For Sale: {wanted_release['display_title']}"
                else:
                    m_title = f"Now For Sale: {wanted_release['release_name']} — {wanted_release['artist_name']}"
                m_body = f"Listing available: https://www.discogs.com/sell/item/{listing_to_post['id']}"
                da_notify.send_pushbullet_push(pushbullet_token, m_title, m_body, verbose=verbose)

    except ConnectionError:
        print("ConnectionError: looping will continue as usual")

    if verbose:
        print(f"\t took {time.time() - start_time}")
