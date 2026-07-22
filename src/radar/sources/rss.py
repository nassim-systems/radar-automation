from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from xml.etree import ElementTree as ET

from radar.domain import RawItem


def parse_rss(feed_xml: str) -> list[RawItem]:
    root = ET.fromstring(feed_xml)
    channel = root.find("channel")
    if channel is None:
        channel = root
    items: list[RawItem] = []

    for element in channel.findall("item"):
        title = (element.findtext("title") or "").strip()
        link = (element.findtext("link") or "").strip()
        guid = (element.findtext("guid") or "").strip()
        pub_date_text = (element.findtext("pubDate") or "").strip()
        summary = (element.findtext("description") or None)

        if not pub_date_text:
            continue

        published_at = parsedate_to_datetime(pub_date_text)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        else:
            published_at = published_at.astimezone(timezone.utc)
        external_id = guid or link

        items.append(
            RawItem(
                source="rss",
                external_id=external_id,
                title=title,
                url=link,
                published_at=published_at,
                summary=summary,
            )
        )

    return items


class RssSource:
    def __init__(self, name: str, url: str, fetcher: Callable[[str], str]):
        self.name = name
        self.url = url
        self.fetcher = fetcher

    def fetch(self) -> list[RawItem]:
        feed_xml = self.fetcher(self.url)
        return parse_rss(feed_xml)
