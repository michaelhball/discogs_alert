import json
import os

from dotenv import load_dotenv
from pathlib import Path

from client import *


if __name__ == '__main__':
    load_dotenv()

    client = UserTokenClient(os.getenv("USER_AGENT"), os.getenv("USER_TOKEN"))

    want_list = json.load(Path('./wantlist.json').open('r'))
    for wanted_release in want_list.get('notify_on_sight'):
        # print(wanted_release.get('id'))
        release = client.get_release(wanted_release.get("id"))
        print(release)
        break
        # this is all we can get from a release... not the details of the actual listings => I have to use a non-official API
        # print(json.loads(release[0])["num_for_sale"])
        # print(json.loads(release[0])["lowest_price"])

        import requests
        from bs4 import BeautifulSoup

        r = requests.get("https://www.discogs.com/sell/release/1523619?ev=rb")
        # print(r.content)

        # SO I HAVE TO PARSE THE LISTINGS HERE, (HOPEFULLY SORT THIS ALREADY BY PRICE, & THEN I CAN USE THE OFFICIAL
        # ID TO LOOK INTO EACH OF THOSE LISTINGS) --> though Discogs probably makes it very hard to parse this information

        soup = BeautifulSoup(r.content, 'html.parser')
        # print(soup.prettify())
        # print(soup.find_all('table')[2])  # this is the record playlist
        # print(soup.find_all('table')[1])  # table for header information at top of page
        # print(soup.find_all('table')[0])  # header header table (nothing to do with this particular release
        # for a in soup.find_all('a'):
        #     print("\n\n\n\n")
        #     print(a)

        listings_table = soup.find_all('table')[3]
        rows = listings_table.find('tbody').find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            print(cells[0])  # this contains a bunch, + I think the ID that is the primary thing we need
            # print(cells[1])  # this contains all item description details (=> necessary for me to check), though I could just use this bit to get ID and find out condition later
            # print(cells[2])  # contains seller info => could check that star rating is > 99% for example
            # print(cells[3])  # seems empty
            # print(cells[4])  # contains price + link to show shipping methods (need to get this user-specific though)
            # print(cells[5])  # add to cart + other buttons from the RHS
            break
        break
