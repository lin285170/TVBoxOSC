"""Data models mirroring the TVBoxOSC interface protocol.

These mirror com.github.catvod.bean / com.github.tvbox.osc.bean classes.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class VodInfo:
    """A single content item (剧集/电影/综艺)."""

    vod_id: str = ""
    vod_name: str = ""
    vod_pic: str = ""
    vod_remarks: str = ""
    type_name: str = ""
    vod_year: str = ""
    vod_area: str = ""
    vod_lang: str = ""
    vod_actor: str = ""
    vod_director: str = ""
    vod_content: str = ""
    vod_play_from: str = ""  # play sources, separated by $$$ (源1$$$源2)
    vod_play_url: str = ""   # play urls per source, separated by $$$ ; episodes by #
    vod_play_flag: str = ""
    vod_id_c: str = ""

    @property
    def play_sources(self) -> List[str]:
        """Split `vod_play_from` on $$$ into source names."""
        if not self.vod_play_from:
            return []
        return [s.strip() for s in self.vod_play_from.split("$$$") if s.strip()]

    @property
    def episode_sources(self) -> List[List[str]]:
        """Return per-source episode lists based on `vod_play_url`.

        Format: 源1的集数用#分隔, 源之间用$$$分隔.
        """
        if not self.vod_play_url:
            return []
        result: List[List[str]] = []
        for src in self.vod_play_url.split("$$$"):
            eps = [e.strip() for e in src.split("#") if e.strip()]
            result.append(eps)
        return result


@dataclass
class VodResult:
    """One page of vod list plus the category (class) definitions."""

    total: int = 0
    page: int = 1
    pagecount: int = 1
    limit: int = 0
    classes: List[dict] = field(default_factory=list)
    filters: Optional[dict] = None
    vods: List[VodInfo] = field(default_factory=list)


@dataclass
class VodList:
    """Detail of a single item with its play source + episode grouping."""

    vod: VodInfo = field(default_factory=VodInfo)
    flags: List[str] = field(default_factory=list)  # play_from split into sources
    episodes: List[List[str]] = field(default_factory=list)  # per-source episodes

    @property
    def sources(self) -> List[str]:
        return [f.strip() for f in self.vod.vod_play_from.split("$$$") if f.strip()] if self.vod.vod_play_from else []

    def resolve(self, source_idx: int, url: str) -> str:
        """Return a playable URL, mapping source api play list first item."""
        return url


@dataclass
class SourceBean:
    """One entry in a 配置 sites[] array."""

    key: str = ""
    name: str = ""
    type: int = 1
    api: str = ""
    searchable: int = 1
    quickSearch: int = 1
    filterable: int = 1
    playerUrl: str = ""
    ext: str = ""
    active: bool = True
    home: bool = False

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "type": self.type,
            "api": self.api,
            "searchable": self.searchable,
            "quickSearch": self.quickSearch,
            "filterable": self.filterable,
            "playerUrl": self.playerUrl,
            "ext": self.ext,
            "active": self.active,
            "home": self.home,
        }
