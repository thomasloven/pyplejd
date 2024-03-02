from aiohttp import ClientSession
import aiohttp
import logging

from .site_details import User, SiteDetails
from .site_list import SiteListItem

from ..interface import PlejdDevice, PlejdScene, PlejdSiteSummary
from .. import const
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
    user = User(**data)
    session.headers["X-Parse-Session-Token"] = user.sessionToken
    return True


class PlejdCloudSite:
    def __init__(self, username: str, password: str, siteId: str, **_):
        self.username = username
        self.password = password
        self.siteId = siteId
        self.details: SiteDetails = None
        self._details_raw = None

    @staticmethod
    async def verify_credentials(username, password) -> bool:
        async with ClientSession(base_url=API_BASE_URL, headers=headers) as session:
            await _set_session_token(session, username, password)
            return True

    @staticmethod
    async def get_sites(username, password) -> list[PlejdSiteSummary]:
        try:
            async with ClientSession(base_url=API_BASE_URL, headers=headers) as session:
                await _set_session_token(session, username, password)
                resp = await session.post(API_SITE_LIST_URL, raise_for_status=True)
                data = await resp.json()
                sites = [SiteListItem(**s) for s in data["result"]]
                return [
                    PlejdSiteSummary(
                        siteId=site.site.siteId,
                        title=site.site.title,
                        deviceCount=len(site.plejdDevice),
                    )
                    for site in sites
                ]
        except aiohttp.ClientError as err:
            raise ConnectionError from err

    async def get_details(self):
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
                self.details = SiteDetails(**data["result"][0])
        except aiohttp.ClientError as err:
            raise ConnectionError from err

    async def load_site_details(self, backup=None):
        try:
            await self.get_details()
        except (AuthenticationError, ConnectionError) as err:
            if backup:
                _LOGGER.debug("Loading site data failed. Reverting to back-up.")
                self._details_raw = backup
                self.details = SiteDetails(**backup)
            else:
                raise err

        _LOGGER.debug("Site data loaded")
        _LOGGER.debug(("Mesh Devices:", self.mesh_devices))

    async def get_raw_details(self):
        try:
            await self.get_details()
        except (AuthenticationError, ConnectionError):
            pass
        return self._details_raw

    @classmethod
    async def create(cls, username, password, siteId):
        self = PlejdCloudSite(username, password, siteId)
        await self.get_details()
        return self

    @property
    def cryptokey(self):
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
    def devices(self) -> list[PlejdDevice]:
        if not self.details:
            raise RuntimeError("No site details have been fetched")
        retval = []
        details = self.details
        for device in details.devices:
            objectId = device.objectId
            deviceId = device.deviceId
            address = details.deviceAddress[deviceId]
            rxaddress = None
            outputType = device.outputType
            inputAddress = []

            plejdDevice = next(
                (d for d in details.plejdDevices if d.deviceId == deviceId), None
            )
            if plejdDevice is None:
                continue
            hardware = const.HARDWARE.get(
                plejdDevice.hardwareId, const.HARDWARE_UNKNOWN
            )

            hardware_name = hardware.name
            if hardware is const.HARDWARE_UNKNOWN:
                hardware_name += f" ({plejdDevice.hardwareId})"

            # dimmable = hardware.dimmable
            # colortemp = hardware.colortemp
            dimmable = bool(device.traits & 0x2)
            colortemp = bool(device.traits & 0x4)

            if outputType is None:
                outputType = hardware.type

            firmware = plejdDevice.firmware.version

            outputSettings = next(
                (s for s in details.outputSettings if s.deviceParseId == objectId),
                None,
            )
            if outputSettings is not None:
                if outputSettings.predefinedLoad is not None:
                    if outputSettings.predefinedLoad.loadType == "No load":
                        continue
                if outputSettings.output is not None:
                    outputs = details.outputAddress.get(deviceId)
                    if outputs:
                        address = outputs[str(outputSettings.output)]
                    if rxaddr := details.rxAddress.get(deviceId):
                        rxaddress = rxaddr[str(outputSettings.output)]
                # if outputSettings.dimCurve is not None:
                #     if outputSettings.dimCurve not in ["NonDimmable", "RelayNormal"]:
                #         dimmable = True
                #     # elif outputSettings.predefinedLoad is not None and outputSettings.predefinedLoad.defaultDimCurve
                #     elif (outputSettings.predefinedLoad is not None and outputSettings.predefinedLoad.loadType in ["DWN", "DALI"]):
                #         dimmable = True
                #     else:
                #         dimmable = False
                colortemp = False
                if (ct := outputSettings.colorTemperature) is not None:
                    if ct.behavior == "adjustable":
                        colortemp = [ct.minTemperature, ct.maxTemperature]


            inputSettings = (s for s in details.inputSettings if s.deviceId == deviceId)
            for inpt in inputSettings:
                if inpt.input is not None:
                    inputs = details.inputAddress.get(deviceId)
                    if inputs:
                        inputAddress.append(inputs[str(inpt.input)])
                if inpt.motionSensorData is not None:
                    outputType = const.MOTION

            room = next((r for r in details.rooms if r.roomId == device.roomId), None)
            if room is not None:
                room = room.title

            retval.append(
                PlejdDevice(
                    objectId=objectId,
                    BLEaddress=deviceId,
                    address=address,
                    rxaddress=rxaddress,
                    inputAddress=inputAddress,
                    name=device.title,
                    hardware=hardware_name,
                    firmware=firmware,
                    outputType=outputType,
                    room=room,
                    dimmable=dimmable,
                    colortemp=colortemp,
                    hidden=device.hiddenFromRoomList
                )
            )
        return retval

    @property
    def scenes(self) -> list[PlejdScene]:
        if not self.details:
            raise RuntimeError("No site details have been fetched")
        retval = []
        details = self.details
        for scene in details.scenes:
            hidden = scene.hiddenFromSceneList
            sceneId = scene.sceneId
            title = scene.title
            index = details.sceneIndex.get(sceneId, -1)
            retval.append(
                PlejdScene(sceneId=sceneId, title=title, index=index, hidden=hidden)
            )

        return retval
