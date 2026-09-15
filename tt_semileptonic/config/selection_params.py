# coding: utf-8

"""
Typed selection parameters, stored on the config as ``cfg.x.lepton_selection`` /
``cfg.x.jet_selection`` / ``cfg.x.met_selection`` / ``cfg.x.lepton_jet_iso`` (built in
``config/run3/config_helper.py``) and read by the selectors in ``tt_semileptonic/selection/``
and ``tt_semileptonic/production/lepton.py``.

These replace plain ``DotDict``s: ``order``'s ``cfg.x`` proxy only ever stores/returns a
value by key (see ``order.mixins.AuxDataMixin.get_aux``/``set_aux``), so the value can be
any object -- ``DotDict`` was only ever a convenience for nested dotted access, not
something columnflow/order requires. Attribute names below match the previous ``DotDict``
keys exactly, so the selector call sites (``p.column``, ``p.min_pt.baseline``, ...) are
unchanged.
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class PtRegimeConfig:
    low_pt: float
    high_pt: float


@dataclasses.dataclass(frozen=True)
class MuonIdConfig:
    column: str
    value: bool | int


@dataclasses.dataclass(frozen=True)
class MuonIdRegimeConfig:
    low_pt: MuonIdConfig
    high_pt: MuonIdConfig


@dataclasses.dataclass(frozen=True)
class MuonIsoConfig:
    column: str
    min_value: int


@dataclasses.dataclass(frozen=True)
class MuonSelectionConfig:
    column: str
    min_pt: PtRegimeConfig
    max_abseta: float
    iso: MuonIsoConfig
    id: MuonIdRegimeConfig
    min_pt_addveto: float
    id_addveto: MuonIdConfig
    max_abseta_addveto: float


@dataclasses.dataclass(frozen=True)
class ElectronMvaIdConfig:
    low_pt: str
    high_pt: str


@dataclasses.dataclass(frozen=True)
class ElectronVetoIdConfig:
    column: str
    min_value: int


@dataclasses.dataclass(frozen=True)
class ElectronSelectionConfig:
    column: str
    min_pt: PtRegimeConfig
    max_abseta: float
    barrel_veto: tuple[float, float]
    mva_id: ElectronMvaIdConfig
    min_pt_addveto: float
    id_addveto: ElectronVetoIdConfig
    max_abseta_addveto: float


@dataclasses.dataclass(frozen=True)
class LeptonSelectionConfig:
    mu: MuonSelectionConfig
    e: ElectronSelectionConfig


@dataclasses.dataclass(frozen=True)
class Ak4MinPtConfig:
    baseline: float
    e: tuple[float, float]
    mu: tuple[float, float]


@dataclasses.dataclass(frozen=True)
class BTaggerConfig:
    column: str
    wp: float


@dataclasses.dataclass(frozen=True)
class Ak4JetSelectionConfig:
    column: str
    max_abseta: float
    min_pt: Ak4MinPtConfig
    btagger: BTaggerConfig


@dataclasses.dataclass(frozen=True)
class Ak8MinPtConfig:
    baseline: float
    toptagged: float


@dataclasses.dataclass(frozen=True)
class TopTaggerConfig:
    column: tuple[str, ...]
    wp: float


@dataclasses.dataclass(frozen=True)
class Ak8JetSelectionConfig:
    column: str
    max_abseta: float
    min_pt: Ak8MinPtConfig
    msoftdrop: tuple[float, float]
    toptagger: TopTaggerConfig
    delta_r_lep: float


@dataclasses.dataclass(frozen=True)
class JetSelectionConfig:
    ak4: Ak4JetSelectionConfig
    ak8: Ak8JetSelectionConfig


@dataclasses.dataclass(frozen=True)
class METMinPtConfig:
    e: float
    mu: float


@dataclasses.dataclass(frozen=True)
class METSelectionConfig:
    column: str
    raw_column: str
    min_pt: METMinPtConfig


@dataclasses.dataclass(frozen=True)
class LeptonJetIsoConfig:
    min_pt: float
    min_delta_r: float
    min_pt_rel: float
