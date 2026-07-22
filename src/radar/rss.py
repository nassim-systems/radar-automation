from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

from .domain import RawItem


def parse_rss(feed_path: Path) -> list[RawItem]:
    tree = ET.parse(feed_path)
    root = tree.getroot()

    channel = root.find("channel") or root
    items = channel.findall("item")

    results = []

    for item in items:
        pub = item.find("pubDate")
        if pub is None or not pub.text:
            # ignore items without pubDate
            continue

        # Convert pubDate string -> datetime
        try:
            published_at = parsedate_to_datetime(pub.text)
        except Exception:
            continue

        raw = RawItem(
            source="rss",
            external_id=item.findtext("guid") or item.findtext("link"),
            title=item.findtext("title") or "",
            url=item.findtext("link") or "",
            published_at=published_at,
            summary=item.findtext("description") or None,
        )

        results.append(raw)

    return results
