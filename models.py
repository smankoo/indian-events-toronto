from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Event:
    source: str
    source_id: str
    title: str
    date: datetime
    time_str: str
    venue: str
    address: str
    city: str
    price: str
    description: str
    image_url: str
    event_url: str
    categories: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    organizer: str = ""
    posted_image_url: str = ""
