from aiohttp import ClientSession
import aiohttp
import logging
from typing import Generator, TypedDict

from . import site_details as sd
from .site_list import SiteListItem

from ..errors import AuthenticationError, ConnectionError

_LOGGER = logging.getLogger(__name__)

API_APP_ID = "zHtVqXt8k4yFyk2QGmgp48D9xZr2G94xWYnF4dak"
API_BASE_URL = "https://cloud.plejd.com"
API_LOGIN_URL = "/parse/login"
API_SITE_LIST_URL = "/parse/functions/getSiteList"
API_SITE_DETAILS_URL = "/parse/functions/getSiteById"


headers = {
    "X-Parse-Application-Id": API_APP_ID,
    "Content-Type": "application/json",
}


class PlejdSiteSummary(TypedDict):
    title: str
    deviceCount: int
    siteId: str


class PlejdEntityData(TypedDict):
    address: int
    deviceAddress: int
    device: sd.Device
    plejdDevice: sd.PlejdDevice
    settings: sd.PlejdDeviceOutputSetting | sd.PlejdDeviceInputSetting
    room: sd.Room
    motion: bool | None


class PlejdSceneData(TypedDict):
    scene: sd.Scene
    index: int


async def _set_session_token(session: ClientSession, username: str, password: str):
    resp = await session.post(
        API_LOGIN_URL,
        json={"username": username, "password": password},
    )
    if resp.status != 200:
        data = await resp.json()
        if data.get("code", 0) == 101:
            raise AuthenticationError("Invalid username/password")
        else:
            _LOGGER.debug("Authentication failed for unknown reason. No internet?")
            raise ConnectionError
    data = await resp.json()
    user = sd.User(**data)
    session.headers["X-Parse-Session-Token"] = user.sessionToken


class PlejdCloudSite:
    def __init__(self, username: str, password: str, siteId: str, **_):
        self.username = username
        self.password = password
        self.siteId = siteId
        self.details: sd.SiteDetails = None
        self._details_raw: str | None = None

    @staticmethod
    async def verify_credentials(username, password) -> bool:
        async with ClientSession(base_url=API_BASE_URL, headers=headers) as session:
            await _set_session_token(session, username, password)
            return True

    @staticmethod
    async def get_sites(username: str, password: str) -> list[PlejdSiteSummary]:
        try:
            async with ClientSession(base_url=API_BASE_URL, headers=headers) as session:
                await _set_session_token(session, username, password)
                resp = await session.post(API_SITE_LIST_URL, raise_for_status=True)
                data = await resp.json()
                sites = [SiteListItem(**s) for s in data["result"]]
                return [
                    {
                        "siteId": site.site.siteId,
                        "title": site.site.title,
                        "deviceCount": len(site.plejdDevice),
                    }
                    for site in sites
                ]
        except aiohttp.ClientError as err:
            raise ConnectionError from err

    async def get_details(self) -> None:
        try:
            async with ClientSession(base_url=API_BASE_URL, headers=headers) as session:
                await _set_session_token(session, self.username, self.password)
                resp = await session.post(
                    API_SITE_DETAILS_URL,
                    params={"siteId": self.siteId},
                    raise_for_status=True,
                )
                data = await resp.json()
                self._details_raw = data["result"][0]
                self.details = sd.SiteDetails(**data["result"][0])
        except aiohttp.ClientError as err:
            raise ConnectionError from err

    async def load_site_details(self, backup=None) -> None:
        try:
            await self.get_details()
        except (AuthenticationError, ConnectionError) as err:
            if backup:
                _LOGGER.debug("Loading site data failed. Reverting to back-up.")
                self._details_raw = backup
                self.details = sd.SiteDetails(**backup)
            else:
                raise err

        _LOGGER.debug("Site data loaded")
        _LOGGER.debug(("Mesh Devices:", self.mesh_devices))

    async def get_raw_details(self) -> str | None:
        try:
            await self.get_details()
        except (AuthenticationError, ConnectionError):
            pass
        return self._details_raw

    @classmethod
    async def create(
        cls, username: str, password: str, siteId: str
    ) -> "PlejdCloudSite":
        self = PlejdCloudSite(username, password, siteId)
        await self.get_details()
        return self

    @property
    def cryptokey(self) -> str:
        if not self.details:
            raise RuntimeError("No site details have been fetched")
        return self.details.plejdMesh.cryptoKey

    @property
    def mesh_devices(self) -> set[str]:
        if not self.details:
            raise RuntimeError("No site details have been fetched")
        retval = set()
        for device in self.details.devices:
            retval.add(device.deviceId)
        return retval

    @property
    def outputs(self) -> Generator[PlejdEntityData, None, None]:
        details = self.details
        if not details:
            raise RuntimeError("No site details have been fetched")

        for deviceId, outputs in details.outputAddress.items():
            plejdDevice = details.find_plejdDevice(deviceId)
            firstDevice = details.find_device(deviceId=deviceId)
            deviceAddress = details.deviceAddress.get(deviceId)

            for output, address in outputs.items():
                output = int(output)

                settings = details.find_outputSettings(deviceId, output)
                if not settings:
                    continue

                device = details.find_device(objectId=settings.deviceParseId)

                room = details.find_room(device.roomId)

                rxAddress = details.rxAddress.get(deviceId, {}).get(str(output), -1)

                yield {
                    "address": address,
                    "deviceAddress": deviceAddress,
                    "device": device,
                    "plejdDevice": plejdDevice,
                    "rxAddress": rxAddress,
                    "settings": settings,
                    "room": room,
                    "first_device": firstDevice,
                }

    @property
    def inputs(self) -> Generator[PlejdSceneData, None, None]:
        details = self.details
        if not details:
            raise RuntimeError("No site details have been fetched")

        for deviceId, inputs in details.inputAddress.items():
            plejdDevice = details.find_plejdDevice(deviceId)
            firstDevice = details.find_device(deviceId=deviceId)
            deviceAddress = details.deviceAddress.get(deviceId)

            for input, address in inputs.items():
                input = int(input)

                settings = details.find_inputSettings(deviceId, input)
                if not settings:
                    continue

                if motionSensor := details.find_motionSensorData(deviceId, input):
                    device = details.find_device(objectId=motionSensor.deviceParseId)
                else:
                    device = details.find_device(deviceId=settings.deviceId)

                room = details.find_room(device.roomId)

                yield {
                    "address": address,
                    "deviceAddress": deviceAddress,
                    "device": device,
                    "plejdDevice": plejdDevice,
                    "settings": settings,
                    "room": room,
                    "motion": bool(motionSensor),
                    "rxAddress": -1,
                    "first_device": firstDevice,
                }

    @property
    def scenes(self) -> Generator[dict, None, None]:
        if not self.details:
            raise RuntimeError("No site details have been fetched")

        details = self.details
        for scene in details.scenes:
            yield {"scene": scene, "index": details.sceneIndex.get(scene.sceneId, -1)}
