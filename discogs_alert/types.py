import enum
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union


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
    accept_generic_sleeve: Optional[bool] = None
    accept_no_sleeve: Optional[bool] = None
    accept_ungraded_sleeve: Optional[bool] = None


@dataclass
class Release:
    """An entity that represents a record the user is searching for."""

    id: int

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


@dataclass
class ListingPrice:
    currency: str
    value: float
    shipping: Optional[ShippingPrice] = None


@dataclass
class Listing:
    """An entity that represents a specific instance of a record for sale (found on the marketplace)"""

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
        # total_price = float(listing.price.value.replace(",", ""))


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
    "R$": "BRL",
    "CHF": "CHF",
    "SEK": "SEK",
    "ZAR": "ZAR",
}


CurrencyRates = Dict[str, Union[int, float]]


COUNTRIES = {
    "AF": "Afghanistan",
    "AL": "Albania",
    "DZ": "Algeria",
    "AS": "American Samoa",
    "AD": "Andorra",
    "AO": "Angola",
    "AI": "Anguilla",
    "AQ": "Antarctica",
    "AG": "Antigua And Barbuda",
    "AR": "Argentina",
    "AM": "Armenia",
    "AW": "Aruba",
    "AU": "Australia",
    "AT": "Austria",
    "AZ": "Azerbaijan",
    "BS": "Bahamas",
    "BH": "Bahrain",
    "BD": "Bangladesh",
    "BB": "Barbados",
    "BY": "Belarus",
    "BE": "Belgium",
    "BZ": "Belize",
    "BJ": "Benin",
    "BM": "Bermuda",
    "BT": "Bhutan",
    "BO": "Bolivia",
    "BA": "Bosnia And Herzegowina",
    "BW": "Botswana",
    "BV": "Bouvet Island",
    "BR": "Brazil",
    "BN": "Brunei Darussalam",
    "BG": "Bulgaria",
    "BF": "Burkina Faso",
    "BI": "Burundi",
    "KH": "Cambodia",
    "CM": "Cameroon",
    "CA": "Canada",
    "CV": "Cape Verde",
    "KY": "Cayman Islands",
    "CF": "Central African Rep",
    "TD": "Chad",
    "CL": "Chile",
    "CN": "China",
    "CX": "Christmas Island",
    "CC": "Cocos Islands",
    "CO": "Colombia",
    "KM": "Comoros",
    "CG": "Congo",
    "CK": "Cook Islands",
    "CR": "Costa Rica",
    "CI": "Cote D`ivoire",
    "HR": "Croatia",
    "CU": "Cuba",
    "CY": "Cyprus",
    "CZ": "Czech Republic",
    "DK": "Denmark",
    "DJ": "Djibouti",
    "DM": "Dominica",
    "DO": "Dominican Republic",
    "TP": "East Timor",
    "EC": "Ecuador",
    "EG": "Egypt",
    "SV": "El Salvador",
    "GQ": "Equatorial Guinea",
    "ER": "Eritrea",
    "EE": "Estonia",
    "ET": "Ethiopia",
    "FK": "Falkland Islands (Malvinas)",
    "FO": "Faroe Islands",
    "FJ": "Fiji",
    "FI": "Finland",
    "FR": "France",
    "GF": "French Guiana",
    "PF": "French Polynesia",
    "TF": "French S. Territories",
    "GA": "Gabon",
    "GM": "Gambia",
    "GE": "Georgia",
    "DE": "Germany",
    "GH": "Ghana",
    "GI": "Gibraltar",
    "GR": "Greece",
    "GL": "Greenland",
    "GD": "Grenada",
    "GP": "Guadeloupe",
    "GU": "Guam",
    "GT": "Guatemala",
    "GN": "Guinea",
    "GW": "Guinea-bissau",
    "GY": "Guyana",
    "HT": "Haiti",
    "HN": "Honduras",
    "HK": "Hong Kong",
    "HU": "Hungary",
    "IS": "Iceland",
    "IN": "India",
    "ID": "Indonesia",
    "IR": "Iran",
    "IQ": "Iraq",
    "IE": "Ireland",
    "IL": "Israel",
    "IT": "Italy",
    "JM": "Jamaica",
    "JP": "Japan",
    "JO": "Jordan",
    "KZ": "Kazakhstan",
    "KE": "Kenya",
    "KI": "Kiribati",
    "KP": "Korea (North)",
    "KR": "Korea (South)",
    "KW": "Kuwait",
    "KG": "Kyrgyzstan",
    "LA": "Laos",
    "LV": "Latvia",
    "LB": "Lebanon",
    "LS": "Lesotho",
    "LR": "Liberia",
    "LY": "Libya",
    "LI": "Liechtenstein",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "MO": "Macau",
    "MK": "Macedonia",
    "MG": "Madagascar",
    "MW": "Malawi",
    "MY": "Malaysia",
    "MV": "Maldives",
    "ML": "Mali",
    "MT": "Malta",
    "MH": "Marshall Islands",
    "MQ": "Martinique",
    "MR": "Mauritania",
    "MU": "Mauritius",
    "YT": "Mayotte",
    "MX": "Mexico",
    "FM": "Micronesia",
    "MD": "Moldova",
    "MC": "Monaco",
    "MN": "Mongolia",
    "MS": "Montserrat",
    "MA": "Morocco",
    "MZ": "Mozambique",
    "MM": "Myanmar",
    "NA": "Namibia",
    "NR": "Nauru",
    "NP": "Nepal",
    "NL": "Netherlands",
    "AN": "Netherlands Antilles",
    "NC": "New Caledonia",
    "NZ": "New Zealand",
    "NI": "Nicaragua",
    "NE": "Niger",
    "NG": "Nigeria",
    "NU": "Niue",
    "NF": "Norfolk Island",
    "MP": "Northern Mariana Islands",
    "NO": "Norway",
    "OM": "Oman",
    "PK": "Pakistan",
    "PW": "Palau",
    "PA": "Panama",
    "PG": "Papua New Guinea",
    "PY": "Paraguay",
    "PE": "Peru",
    "PH": "Philippines",
    "PN": "Pitcairn",
    "PL": "Poland",
    "PT": "Portugal",
    "PR": "Puerto Rico",
    "QA": "Qatar",
    "RE": "Reunion",
    "RO": "Romania",
    "RU": "Russian Federation",
    "RW": "Rwanda",
    "KN": "Saint Kitts And Nevis",
    "LC": "Saint Lucia",
    "VC": "St Vincent/Grenadines",
    "WS": "Samoa",
    "SM": "San Marino",
    "ST": "Sao Tome",
    "SA": "Saudi Arabia",
    "SN": "Senegal",
    "SC": "Seychelles",
    "SL": "Sierra Leone",
    "SG": "Singapore",
    "SK": "Slovakia",
    "SI": "Slovenia",
    "SB": "Solomon Islands",
    "SO": "Somalia",
    "ZA": "South Africa",
    "ES": "Spain",
    "LK": "Sri Lanka",
    "SH": "St. Helena",
    "PM": "St.Pierre",
    "SD": "Sudan",
    "SR": "Suriname",
    "SZ": "Swaziland",
    "SE": "Sweden",
    "CH": "Switzerland",
    "SY": "Syrian Arab Republic",
    "TW": "Taiwan",
    "TJ": "Tajikistan",
    "TZ": "Tanzania",
    "TH": "Thailand",
    "TG": "Togo",
    "TK": "Tokelau",
    "TO": "Tonga",
    "TT": "Trinidad And Tobago",
    "TN": "Tunisia",
    "TR": "Turkey",
    "TM": "Turkmenistan",
    "TV": "Tuvalu",
    "UG": "Uganda",
    "UA": "Ukraine",
    "AE": "United Arab Emirates",
    "UK": "United Kingdom",
    "US": "United States",
    "UY": "Uruguay",
    "UZ": "Uzbekistan",
    "VU": "Vanuatu",
    "VA": "Vatican City State",
    "VE": "Venezuela",
    "VN": "Viet Nam",
    "VG": "Virgin Islands (British)",
    "VI": "Virgin Islands (U.S.)",
    "EH": "Western Sahara",
    "YE": "Yemen",
    "YU": "Yugoslavia",
    "ZR": "Zaire",
    "ZM": "Zambia",
    "ZW": "Zimbabwe",
}
COUNTRY_CHOICES = set(COUNTRIES.keys())
