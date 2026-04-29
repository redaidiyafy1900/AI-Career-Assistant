from backend.scraper.shixiseng import ShixisengScraper
from backend.scraper.boss import BossScraper
from backend.scraper.zhilian import ZhilianScraper
from backend.scraper.wuyou import WuyouScraper
from backend.scraper.enterprise import EnterpriseScraper
from backend.scraper.wyu import WyuScraper
from backend.scraper.wyujob import WyuJobScraper

SCRAPER_MAP = {
    "shixiseng": ShixisengScraper,
    "boss": BossScraper,
    "zhilian": ZhilianScraper,
    "wuyou": WuyouScraper,
    "enterprise": EnterpriseScraper,
    "wyu": WyuScraper,
    "wyujob": WyuJobScraper,  # 五邑大学就业信息网
}
