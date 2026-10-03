"""Generator registry: name -> callable(brief, params, seed) -> list[placement]."""
from .beam import BeamParams, beam_search
from .multilevel import beam_multilevel
from .treemap import treemap
from .cpsat import cpsat_generator
from .dual import NotPlanar, WillNotTile, dual_generator


def _beam(brief, params, seed):
    p = BeamParams(**(params or {}))
    if (brief.levels or 1) > 1 or brief.envelope:
        return beam_multilevel(brief, p, seed)
    return beam_search(brief, p, seed)


class GeneratorUnsupported(ValueError):
    """The generator cannot handle this kind of brief (M7.5)."""


# What each generator can do; the API and the UI read this.
CAPABILITIES = {
    "treemap": {"multi_level": False},
    "beam": {"multi_level": True},
    "cpsat": {"multi_level": True},
    "dual": {"multi_level": False},
}


def unsupported_reason(name: str, brief) -> str | None:
    caps = CAPABILITIES.get(name)
    if caps and not caps["multi_level"] and (brief.levels or 1) > 1:
        return f"{name} is single-level only"
    return None


def _treemap(brief, params, seed):
    reason = unsupported_reason("treemap", brief)
    if reason:
        raise GeneratorUnsupported(reason)
    return treemap(brief, params, seed)


def _dual(brief, params, seed):
    reason = unsupported_reason("dual", brief)
    if reason:
        raise GeneratorUnsupported(reason)
    try:
        return dual_generator(brief, params, seed)
    except (NotPlanar, WillNotTile) as e:
        raise GeneratorUnsupported(f"dual: {e}") from e


GENERATORS = {"treemap": _treemap, "beam": _beam, "cpsat": cpsat_generator, "dual": _dual}
