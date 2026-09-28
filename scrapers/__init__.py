from .croma import CromaScraper
from .reliancedigital import RelianceDigitalScraper
from .vijaysales import VijaySalesScraper

# Adding a new retailer = write a subclass of BaseScraper implementing
# _search_live(), then register it here. Nothing else in the app needs
# to change (aggregator iterates this registry).
SCRAPER_REGISTRY = {
    "croma": CromaScraper,
    "vijaysales": VijaySalesScraper,
    "reliancedigital": RelianceDigitalScraper,
}
