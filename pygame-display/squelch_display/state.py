"""State model — populated from IPC JSON messages sent by the CLI plugin."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class UnitInfo:
    unitId: int
    tag: Optional[str] = None
    emergency: bool = False


@dataclass
class CallInfo:
    systemId: int
    systemLabel: str
    talkgroupId: int
    tgLabel: Optional[str] = None
    tgName: Optional[str] = None
    tgGroup: Optional[str] = None
    tgGroupTag: Optional[str] = None
    freq: Optional[float] = None
    emergency: bool = False
    encrypted: bool = False
    startTime: Optional[int] = None
    units: List[UnitInfo] = field(default_factory=list)


@dataclass
class DisplayState:
    connected: bool = False
    mode: str = 'live'
    playing: bool = False
    paused: bool = False
    elapsed: float = 0.0
    queueLen: int = 0
    volume: int = 100
    lfActive: bool = False
    holdSys: Optional[int] = None
    holdTg: Optional[int] = None
    avoidCount: int = 0
    call: Optional[CallInfo] = None

    def update(self, msg: dict) -> None:
        self.connected  = msg.get('connected',  self.connected)
        self.mode       = msg.get('mode',       self.mode)
        self.playing    = msg.get('playing',    self.playing)
        self.paused     = msg.get('paused',     self.paused)
        self.elapsed    = msg.get('elapsed',    self.elapsed)
        self.queueLen   = msg.get('queueLen',   self.queueLen)
        self.volume     = msg.get('volume',     self.volume)
        self.lfActive   = msg.get('lfActive',   self.lfActive)
        self.holdSys    = msg.get('holdSys',    self.holdSys)
        self.holdTg     = msg.get('holdTg',     self.holdTg)
        self.avoidCount = msg.get('avoidCount', self.avoidCount)

        raw = msg.get('call')
        if raw is None:
            self.call = None
        else:
            units = [
                UnitInfo(
                    unitId=u['unitId'],
                    tag=u.get('tag'),
                    emergency=u.get('emergency', False),
                )
                for u in raw.get('units', [])
            ]
            self.call = CallInfo(
                systemId=raw.get('systemId', 0),
                systemLabel=raw.get('systemLabel', ''),
                talkgroupId=raw.get('talkgroupId', 0),
                tgLabel=raw.get('tgLabel'),
                tgName=raw.get('tgName'),
                tgGroup=raw.get('tgGroup'),
                tgGroupTag=raw.get('tgGroupTag'),
                freq=raw.get('freq'),
                emergency=raw.get('emergency', False),
                encrypted=raw.get('encrypted', False),
                startTime=raw.get('startTime'),
                units=units,
            )
