import json
import time

from pathlib import Path

from discogs_alert.client import AnonClient, UserTokenClient
from discogs_alert.notify import send_pushbullet_push
from discogs_alert.utils import convert_currency, get_currency_rates, CONDITIONS

__all__ = ['loop']


def loop(pushbullet_token, list_id, wantlist_path, user_agent, discogs_token, country, currency, min_seller_rating,
         min_seller_sales, min_media_condition, min_sleeve_condition, accept_generic_sleeve, accept_no_sleeve,
         accept_ungraded_sleeve, verbose=False):
    """ Event loop, each time this is called we query the discogs marketplace for all items in wantlist. """

    start_time = time.time()
    if verbose:
        print("\nrunning loop")

    currency_rates = get_currency_rates(currency)
    mmc = CONDITIONS[min_media_condition]
    msc = CONDITIONS[min_sleeve_condition]

    try:
        client_anon = AnonClient(user_agent)
        user_token_client = UserTokenClient(user_agent, discogs_token)

        if list_id is not None:
            wantlist = user_token_client.get_list(list_id).get('items')
        else:
            wantlist = json.load(Path(wantlist_path).open('r'))
        for wanted_release in wantlist:
            release_id = wanted_release.get("id")

            # parameter values for current release only (if set by user)
            temp_mmc = wanted_release.get('min_media_condition')
            temp_msc = wanted_release.get('min_sleeve_condition')
            temp_ags = wanted_release.get('accept_generic_sleeve')
            temp_ans = wanted_release.get('accept_no_sleeve')
            temp_aus = wanted_release.get('accept_ungraded_sleeve')
            price_threshold = wanted_release.get('price_threshold')

            valid_listings = []
            release_stats = user_token_client.get_release_stats(release_id)
            if release_stats:
                if release_stats.get("num_for_sale") > 0 and not release_stats.get("blocked_from_sale"):
                    for listing in client_anon.get_marketplace_listings(release_id):

                        # verify availability
                        if listing.get('availability') == f'Unavailable in {country}':
                            continue

                        # verify seller conditions
                        if listing.get('seller_avg_rating') is not None:  # None if new seller
                            if min_seller_rating is not None and listing['seller_avg_rating'] < min_seller_rating:
                                continue
                        if min_seller_sales is not None and listing['seller_num_ratings'] < min_seller_sales:
                            continue

                        # verify media condition
                        this_iter_mmc = CONDITIONS[temp_mmc] if temp_mmc is not None else mmc
                        if CONDITIONS[listing['media_condition']] < this_iter_mmc:
                            continue

                        # verify sleeve condition
                        ags = temp_ags if temp_ags is not None else accept_generic_sleeve
                        if not ags and listing['sleeve_condition'] == "Generic":
                            continue
                        ans = temp_ans if temp_ans is not None else accept_no_sleeve
                        if not ans and listing['sleeve_condition'] == "No Cover" or listing['sleeve_condition'] is None:
                            continue
                        aus = temp_aus if temp_aus is not None else accept_ungraded_sleeve
                        if not aus and listing['sleeve_condition'] == "Not Graded":
                            continue
                        this_iter_msc = CONDITIONS[temp_msc] if temp_msc is not None else msc
                        if CONDITIONS[listing['sleeve_condition']] < this_iter_msc:
                            continue

                        # convert listing price & shipping --> base currency
                        price = listing['price']
                        if price['currency'] != currency:
                            converted_price = convert_currency(price.get('currency'), price.get('value'),
                                                               currency_rates)
                            listing['price']['currency'] = currency
                            listing['price']['value'] = converted_price

                        shipping = price.get('shipping')
                        if shipping is not None:
                            if shipping.get('currency') != currency:
                                converted_shipping = convert_currency(shipping.get('currency'), shipping.get('value'),
                                                                      currency_rates)
                                listing['price']['shipping'] = {'currency': currency, 'value': converted_shipping}

                        # use price threshold if we have one
                        total_price = float(listing['price']['value'])
                        if price_threshold is not None and total_price > price_threshold:
                            continue

                        valid_listings.append(listing)

            else:
                # here if something went wrong getting release stats
                continue

            # if we found something, send notification
            if len(valid_listings) > 0:
                listing_to_post = valid_listings[0]
                if list_id is not None:
                    m_title = f"Now For Sale: {wanted_release['display_title']}"
                else:
                    m_title = f"Now For Sale: {wanted_release['release_name']} — {wanted_release['artist_name']}"
                m_body = f"Listing available: https://www.discogs.com/sell/item/{listing_to_post['id']}"
                send_pushbullet_push(pushbullet_token, m_title, m_body, verbose=verbose)

    except Exception as e:
        print(e)  # don't raise error (in case it's just temporary loss of internet connection) – need better solution

    if verbose:
        print(f'\t took {time.time() - start_time}')
