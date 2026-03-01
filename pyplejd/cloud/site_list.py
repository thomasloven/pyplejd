from typing import Optional

from pydantic import BaseModel


class Site(BaseModel):
    siteId: str
    title: Optional[str] = ""


class SiteListItem(BaseModel):
    site: Site
    plejdDevice: list[str]
    gateway: list
    hasRemoteControlAccess: bool
    sitePermission: dict
