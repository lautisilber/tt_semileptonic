# coding: utf-8

"""
Column producers related to leptons.
"""
from columnflow.production import Producer, producer
from columnflow.util import maybe_import
from columnflow.columnar_util import set_ak_column

ak = maybe_import("awkward")
np = maybe_import("numpy")


def _muon_masks(events: ak.Array, params) -> dict:
    """
    Per-muon boolean masks from ``cfg.x.lepton_selection.mu``:

    - ``low_pt`` / ``high_pt``: the two pt regimes of a signal muon
      (low-pt: tight ID + PF isolation; high-pt: dedicated high-pt ID);
    - ``tight``: signal muon (``low_pt | high_pt``);
    - ``veto``: an additional, looser muon (``*_addveto`` params) that is *not* a
      signal muon -- used to veto events with a second lepton.
    """
    mu = events.Muon
    eta = abs(mu.eta) < params.max_abseta

    low_pt = (
        eta &
        (mu.pt > params.min_pt.low_pt) &
        (mu.pt <= params.min_pt.high_pt) &
        (mu[params.iso.column] >= params.iso.min_value) &
        mu[params.id.low_pt.column]
    )
    high_pt = (
        eta &
        (mu.pt > params.min_pt.high_pt) &
        (mu[params.id.high_pt.column] == params.id.high_pt.value)
    )
    tight = low_pt | high_pt

    veto = (
        (abs(mu.eta) < params.max_abseta_addveto) &
        (mu.pt > params.min_pt_addveto) &
        mu[params.id_addveto.column] &
        ~tight
    )
    return {"low_pt": low_pt, "high_pt": high_pt, "tight": tight, "veto": veto}


def _electron_masks(events: ak.Array, params) -> dict:
    """
    Per-electron boolean masks from ``cfg.x.lepton_selection.e``, analogous to
    :py:func:`_muon_masks`. The pseudorapidity cut uses the supercluster eta
    (``eta + deltaEtaSC``) and vetoes the barrel-endcap transition region.
    """
    e = events.Electron
    abseta_sc = abs(e.eta + e.deltaEtaSC)
    eta = (
        (abseta_sc < params.max_abseta) &
        ((abs(e.eta) < params.barrel_veto[0]) | (abs(e.eta) > params.barrel_veto[1]))
    )

    low_pt = (
        eta &
        (e.pt > params.min_pt.low_pt) &
        (e.pt <= params.min_pt.high_pt) &
        e[params.mva_id.low_pt]
    )
    high_pt = (
        eta &
        (e.pt > params.min_pt.high_pt) &
        e[params.mva_id.high_pt]
    )
    tight = low_pt | high_pt

    veto = (
        (abseta_sc < params.max_abseta_addveto) &
        (e.pt > params.min_pt_addveto) &
        (e[params.id_addveto.column] >= params.id_addveto.min_value) &
        ~tight
    )
    return {"low_pt": low_pt, "high_pt": high_pt, "tight": tight, "veto": veto}


#: NanoAOD columns read by :py:func:`selected_lepton_jet_mask` (declare in a selector's uses)
lepton_jet_match_columns = {
    "Muon.pass_lepton", "Electron.pass_lepton",
    "Jet.muonIdx1", "Jet.muonIdx2", "Jet.electronIdx1", "Jet.electronIdx2",
}


def selected_lepton_jet_mask(events: ak.Array) -> ak.Array:
    """
    Per-AK4-jet boolean, ``True`` when the jet *is* the event's selected lepton.

    NanoAOD's anti-kt clustering turns an isolated lepton into its own PF jet, so that
    jet must be dropped before counting jets or computing lepton-jet separation. Matches
    ``Jet.{muon,electron}Idx1/2`` (the indices of a jet's leading lepton constituents)
    against the index of the ``pass_lepton`` muon/electron. Requires ``lepton_definition``
    to have run.
    """
    # index of the selected muon / electron, or -1 when there is none. de-optioning here
    # (fill_none) is important: broadcasting a per-event ?int against the jagged Jet array
    # would otherwise make the *whole jet list* nullable (N * option[var * bool]).
    mu_idx = ak.fill_none(ak.firsts(ak.local_index(events.Muon.pass_lepton)[events.Muon.pass_lepton], axis=1), -1)
    e_idx = ak.fill_none(ak.firsts(ak.local_index(events.Electron.pass_lepton)[events.Electron.pass_lepton], axis=1), -1)

    # `Jet.<lep>Idx == -1` means "no matched lepton", so guard on has_mu / has_e to avoid
    # matching every lepton-less jet in the other channel
    has_mu = mu_idx >= 0
    has_e = e_idx >= 0
    is_lepton = (
        (has_mu & ((events.Jet.muonIdx1 == mu_idx) | (events.Jet.muonIdx2 == mu_idx))) |
        (has_e & ((events.Jet.electronIdx1 == e_idx) | (events.Jet.electronIdx2 == e_idx)))
    )
    return ak.fill_none(is_lepton, False)


@producer(
    uses={"event"},
    produces={
        "Muon.pass_lepton", "Electron.pass_lepton",
        "Muon.pass_veto_lepton", "Electron.pass_veto_lepton",
        "channel_id", "pt_regime",
    },
)
def lepton_definition(self: Producer, events: ak.Array, **kwargs) -> ak.Array:
    """
    Single source of truth for "what is a selected lepton" in this analysis. Reads
    ``config_inst.x.lepton_selection`` and writes the columns below (none are NanoAOD
    fields):

    ``Muon.pass_lepton`` / ``Electron.pass_lepton``
        Per-object bool -- the signal lepton definition, with a pt-regime-dependent ID
        (low-pt: an isolated ID; high-pt: a dedicated high-pt ID). This is the primitive
        ("which leptons are good"); ``lepton_selection`` turns it into the object index
        lists ``ReduceEvents`` applies. Transient (not kept past ``ReduceEvents``).

    ``Muon.pass_veto_lepton`` / ``Electron.pass_veto_lepton``
        Per-object bool -- looser leptons (``*_addveto`` params) that are *not* a signal
        lepton, used to veto events containing a second lepton. Transient.

    ``channel_id``
        Per-event ``int8``: ``2`` if the event has exactly one signal muon and no signal
        electron, ``1`` if exactly one signal electron and no signal muon, ``0``
        otherwise. Ids from ``cfg.add_channel``. Kept -- the compact event-level label
        that ``lepton_producer`` and the ``cat_1e`` / ``cat_1m`` categorizers key on.

    ``pt_regime``
        Per-event ``int8``: ``1`` if the event's signal lepton is in the low-pt regime,
        ``2`` if high-pt, ``0`` if undefined (``channel_id == 0``). Kept.
    """
    params = self.config_inst.x.lepton_selection
    mu = _muon_masks(events, params.mu)
    el = _electron_masks(events, params.e)

    events = set_ak_column(events, "Muon.pass_lepton", mu["tight"])
    events = set_ak_column(events, "Electron.pass_lepton", el["tight"])
    events = set_ak_column(events, "Muon.pass_veto_lepton", mu["veto"])
    events = set_ak_column(events, "Electron.pass_veto_lepton", el["veto"])

    n_muon = ak.sum(mu["tight"], axis=1)
    n_electron = ak.sum(el["tight"], axis=1)

    ch_e = self.config_inst.get_channel("e").id
    ch_mu = self.config_inst.get_channel("mu").id

    # exactly one signal lepton of a single flavour -> that channel, otherwise 0
    channel_id = ak.zeros_like(events.event, dtype=np.int8)
    channel_id = ak.where((n_muon == 1) & (n_electron == 0), np.int8(ch_mu), channel_id)
    channel_id = ak.where((n_electron == 1) & (n_muon == 0), np.int8(ch_e), channel_id)
    events = set_ak_column(events, "channel_id", channel_id)

    # pt regime of the single signal lepton of the winning channel (0 if none)
    in_mu = channel_id == ch_mu
    in_e = channel_id == ch_e
    pt_regime = ak.zeros_like(events.event, dtype=np.int8)
    pt_regime = ak.where(in_mu & (ak.sum(mu["low_pt"], axis=1) == 1), np.int8(1), pt_regime)
    pt_regime = ak.where(in_mu & (ak.sum(mu["high_pt"], axis=1) == 1), np.int8(2), pt_regime)
    pt_regime = ak.where(in_e & (ak.sum(el["low_pt"], axis=1) == 1), np.int8(1), pt_regime)
    pt_regime = ak.where(in_e & (ak.sum(el["high_pt"], axis=1) == 1), np.int8(2), pt_regime)
    events = set_ak_column(events, "pt_regime", pt_regime)

    return events


@lepton_definition.init
def lepton_definition_init(self: Producer) -> None:
    # the concrete ID / isolation NanoAOD branch names come from the config, so the
    # column dependencies can only be declared once the config instance is known
    if not getattr(self, "config_inst", None):
        return
    p = self.config_inst.x.lepton_selection
    # pt/eta/phi/mass: NanoAOD (vector) behavior needs the full Lorentz vector for
    # `events.Muon.pt` / `events.Electron.pt` to work (columnflow convention)
    self.uses |= {
        f"{p.mu.column}.{f}" for f in {
            "pt", "eta", "phi", "mass",
            p.mu.iso.column,
            p.mu.id.low_pt.column,
            p.mu.id.high_pt.column,
            p.mu.id_addveto.column,
        }
    }
    self.uses |= {
        f"{p.e.column}.{f}" for f in {
            "pt", "eta", "phi", "mass", "deltaEtaSC",
            p.e.mva_id.low_pt,
            p.e.mva_id.high_pt,
            p.e.id_addveto.column,
        }
    }


@producer(
    uses={
        "channel_id",
        "Electron.pt", "Electron.eta", "Electron.phi", "Electron.mass",
        "Muon.pt", "Muon.eta", "Muon.phi", "Muon.mass",
    },
    produces={
        "Lepton.*",
    },
)
def lepton_producer(self: Producer, events: ak.Array, **kwargs) -> ak.Array:
    """
    Choose either muon or electron as the main lepton per event
    based on `channel_id` information and write it to a new column
    `Lepton`.
    """

    # extract only LV columns
    muon = events.Muon[["pt", "eta", "phi", "mass"]]
    electron = events.Electron[["pt", "eta", "phi", "mass"]]

    # choose either muons or electrons based on channel ID
    lepton = ak.concatenate([
        ak.mask(muon, events.channel_id == 2),
        ak.mask(electron, events.channel_id == 1),
    ], axis=1)

    # if more than one lepton, choose the first
    lepton = ak.firsts(lepton, axis=1)

    # if no lepton, ensure optional type is on fields
    # and not on record itself, and fill with zeroes
    lepton = ak.merge_option_of_records(lepton)
    lepton = ak.fill_none(lepton, 0)

    # attach lorentz vector behavior to lepton
    lepton = ak.with_name(lepton, "PtEtaPhiMLorentzVector")

    # commit lepton to events array
    events = set_ak_column(events, "Lepton", lepton)

    return events
