"""Persistent UI/session state (perspective person, etc.)."""

from .. import config
from . import errors


def _default_perspective() -> str:
    from ..model import load_model

    model = load_model()
    return model["metadata"].get("focus_person") or ""


def get_state() -> dict:
    state = config.load_state()
    default = _default_perspective()
    perspective = state.get("perspective_person_id") or default
    if not perspective:
        raise errors.NotFoundError("No focus person is configured in family.db.")
    state["perspective_person_id"] = perspective
    state["default_perspective_person_id"] = default
    return state


def set_perspective(person_id: str) -> dict:
    if not person_id:
        raise errors.ValidationError("person_id is required.")
    state = config.load_state()
    state["perspective_person_id"] = person_id
    config.save_state(state)
    return get_state()


def reset_perspective() -> dict:
    default = _default_perspective()
    state = config.load_state()
    state["perspective_person_id"] = default
    config.save_state(state)
    return get_state()
