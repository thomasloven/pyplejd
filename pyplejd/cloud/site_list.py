try:
    from pydantic.v1 import BaseModel
except ImportError:
    from pydantic import BaseModel


class Site(BaseModel):
    siteId: str
    title: str


class SiteListItem(BaseModel):
    site: Site
    plejdDevice: list[str]
    gateway: list
    hasRemoteControlAccess: bool
    sitePermission: dict
