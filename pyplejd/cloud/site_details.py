try:
    from pydantic.v1 import BaseModel
except ImportError:
    from pydantic import BaseModel
from .. import const


# Parameters are read from my own test site data. There may be more or fewer parameters in some objects
# Most things not currently used by pyplejd in any way is currently commented out.


class PlejdObject(BaseModel):  # TODO
    # createdAt: str
    # updatedAt: str
    # ACL: dict
    objectId: str


class Pointer(BaseModel):
    __type = "Pointer"
    className: str
    objectId: str


class User(PlejdObject):
    profileName: str
    # isInstaller: bool = False
    email: str
    locale: str = "en"
    username: str
    # hasIntegration: bool = False
    # emailVerified: bool = True
    # profile: dict = {}
    # _failed_login_count: int = 0
    sessionToken: str = None


class Site(PlejdObject):
    # installers: list[str] = []
    title: str
    siteId: str
    version: int
    # plejdMesh: Pointer # Pointer to SiteData.plejdMesh
    # astroTable: dict
    # city: str
    # coordinates: dict
    # country: str
    # deviceAstroTable: dict
    # zipCode: str
    # previousOwners: list[str] = []


class PlejdMesh(PlejdObject):
    siteId: str
    plejdMeshId: str
    meshKey: str
    cryptoKey: str
    # site: Pointer # Pointer to SiteData.site


class Room(PlejdObject):
    siteId: str
    roomId: str
    title: str
    category: str
    # imageHash: int


class Scene(PlejdObject):
    title: str
    sceneId: str
    siteId: str
    hiddenFromSceneList: bool = False
    # settings: str = ""


class Device(PlejdObject):
    deviceId: str
    siteId: str
    title: str
    traits: int
    hiddenFromRoomList: bool = False
    roomId: str | None = ""
    hiddenFromIntegrations: bool = False
    outputType: str | None = None


class Firmware(PlejdObject):  # TODO
    notes: str
    # data: dict
    # metaData: dict
    # meshCommands: dict
    version: str
    # buildTime: int
    # firmwareApi: str


class PlejdDevice(PlejdObject):
    deviceId: str
    siteId: str
    # installer: Pointer
    # dirtyInstall: bool
    # dirtyUpdate: bool
    # dirtyClock: bool
    # dirtySettings: bool
    hardwareId: str
    faceplateId: str | None = "0"
    firmware: Firmware
    # coordinates: dict = None
    # predefinedLoad: dict = None
    # diagnostics: str
    isFellowshipFollower: bool = False


class PlejdDeviceInputSetting(PlejdObject):
    deviceId: str
    siteId: str
    input: int
    motionSensorData: dict | None
    buttonType: str = ""
    # dimSpeed: int = 0
    # doubleSidedDirectionButton: bool = False
    # singleClick: str | None = None
    # doubleClick: str | None = None


class PredefinedLoad(PlejdObject):
    loadType: str
    # title_en: str
    # description_en: str
    # title_sv: str
    # description_sv: str
    # titleKey: str
    # descriptionKey: str
    # predefinedLoadData: str
    # defaultDimCurve: dict
    # allowedDimCurves: dict


class ColorTemperature(BaseModel):
    minTemperature: int
    maxTemperature: int
    # slewRate: int
    # minTemperatureLimit: int
    # maxTemperatureLimit: int
    behavior: str
    # startTemperature: int


class CoverableSettings(BaseModel):
    # coverableMovementDirection: str
    # coverableTiltTime: int
    coverableTiltStart: int | None = None
    coverableTiltEnd: int | None = None
    # coverablePostRunTime: int
    # coverableCalibration: dict


class PlejdDeviceOutputSetting(PlejdObject):
    deviceId: str
    siteId: str
    output: int | None = None
    deviceParseId: str
    # dimMin: int
    # dimMax: int
    # dimStart: int
    dimCurve: str | None = None
    # outputSpeed: float
    # outputStartTime: int
    # curveRectification: bool
    # curveLogarithm: int
    # curveSinusCompensation: int
    # bootState: str
    predefinedLoad: PredefinedLoad | None = None
    colorTemperature: ColorTemperature | None = None
    coverableSettings: CoverableSettings | None = None
    # minimumRelayOffTime: int = None


class MotionSensor(PlejdObject):
    deviceId: str
    siteId: str
    input: int | None = None
    deviceParseId: str
    # dirty: bool
    # dirtyRemove: bool
    # active: bool


class SceneStep(PlejdObject):
    sceneId: str
    siteId: str
    deviceId: str
    state: str
    value: int
    # dirty: bool
    # dirtyRemoved: bool
    # output: int


class SitePermission(PlejdObject):
    siteId: str
    userId: str
    user: User
    locked: bool
    isOwner: bool
    isInstaller: bool
    isUser: bool
    site: Site


class SiteDetails(BaseModel):
    site: Site
    plejdMesh: PlejdMesh
    rooms: list[Room]
    scenes: list[Scene]
    devices: list[Device]
    plejdDevices: list[PlejdDevice]
    # gateways: list
    # resourceSets: list
    # timeEvents: list
    # sceneSteps: list[SceneStep]
    # astroEvents: list
    inputSettings: list[PlejdDeviceInputSetting]
    outputSettings: list[PlejdDeviceOutputSetting]
    motionSensors: list[MotionSensor] | None = None
    rxAddress: dict[str, dict[str, int]] | None
    # stateTimers: dict
    # sitePermission: SitePermission
    inputAddress: dict[str, dict[str, int]]
    outputAddress: dict[str, dict[str, int]]
    deviceAddress: dict[str, int]
    outputGroups: dict[str, dict[str, list[int]]]
    roomAddress: dict[str, int]
    sceneIndex: dict[str, int]
    deviceLimit: int

    def find_plejdDevice(self, deviceId: str) -> PlejdDevice:
        for d in self.plejdDevices:
            if d.deviceId == deviceId:
                return d

    def find_outputSettings(
        self, deviceId: str, output: int
    ) -> PlejdDeviceOutputSetting:
        for d in self.outputSettings:
            if d.deviceId == deviceId and d.output == output:
                return d

    def find_inputSettings(self, deviceId, input: int) -> PlejdDeviceInputSetting:
        for d in self.inputSettings:
            if d.deviceId == deviceId and d.input == input:
                return d

    def find_motionSensorData(self, deviceId: str | None, input: int) -> MotionSensor:
        if not self.motionSensors:
            return None
        for d in self.motionSensors:
            if d.deviceId == deviceId and d.input == input:
                return d

    def find_device(
        self, deviceId: str | None = None, objectId: str | None = None
    ) -> Device:
        for d in self.devices:
            if objectId is not None and d.objectId == objectId:
                return d
            if deviceId is not None and d.deviceId == deviceId:
                return d

    def find_room(self, roomId: str) -> Room:
        for r in self.rooms:
            if r.roomId == roomId:
                return r
