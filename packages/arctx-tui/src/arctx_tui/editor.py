"""Modal editor screens for mutating a ARCTX run from the TUI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from arctx.payload_builder import payload_type_names
from arctx.core.types import JSONValue


TargetKind = Literal["node", "step"]
PayloadOption = tuple[str, str]

NODE_PAYLOAD_KINDS: tuple[PayloadOption, ...] = (
    ("Note", "note"),
    ("Observation", "observation"),
    ("Payload", "payload"),
)
STEP_PAYLOAD_KINDS: tuple[PayloadOption, ...] = (
    ("Experiment", "experiment"),
    ("Suggestion", "suggestion"),
    ("Implementation", "implementation"),
    ("Observation", "observation"),
    ("Payload", "payload"),
)


@dataclass(frozen=True)
class StepFormData:
    input_node_ids: tuple[str, ...]
    payload_type: str
    payload_kind: str
    content: dict[str, JSONValue]


@dataclass(frozen=True)
class PayloadFormData:
    target_kind: TargetKind
    target_id: str
    payload_type: str
    payload_kind: str
    content: dict[str, JSONValue]


@dataclass(frozen=True)
class GitPayloadFormData:
    step_id: str
    commits: tuple[str, ...]


def _parse_json_object(raw: str) -> dict[str, JSONValue]:
    text = raw.strip()
    if not text:
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("JSON must be an object")
    return data


class _FormScreen(ModalScreen):
    """Shared form helpers for small TUI editor dialogs."""

    def _input_value(self, widget_id: str) -> str:
        return self.query_one(f"#{widget_id}", Input).value.strip()

    def _select_value(self, widget_id: str) -> str:
        value = self.query_one(f"#{widget_id}", Select).value
        if value is Select.NULL:
            return ""
        return str(value)

    def _set_error(self, message: str) -> None:
        self.query_one("#form-error", Static).update(message)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        if event.button.id == "submit":
            self._submit()

    def _submit(self) -> None:
        raise NotImplementedError


class StepForm(_FormScreen):
    """Create a step from one or more input nodes."""

    def __init__(self, *, default_node_id: str) -> None:
        super().__init__()
        self._default_node_id = default_node_id

    def compose(self) -> ComposeResult:
        with Container(classes="editor-dialog"):
            yield Label("Create Step", classes="editor-title")
            yield Label("Input nodes")
            yield Input(value=self._default_node_id, id="input-nodes")
            yield Label("Payload type")
            yield Select(
                _payload_type_options("step", include_cut=False),
                value="step_payload",
                allow_blank=False,
                id="payload-type",
            )
            yield Label("Step type")
            yield Select(
                STEP_PAYLOAD_KINDS,
                value="experiment",
                allow_blank=False,
                id="payload-kind",
            )
            yield Label("Content JSON")
            yield Input(value="{}", id="content-json")
            yield Static("", id="form-error")
            with Horizontal(classes="editor-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Create", id="submit", variant="primary")

    def _submit(self) -> None:
        try:
            input_node_ids = tuple(
                node_id.strip()
                for node_id in self._input_value("input-nodes").split(",")
                if node_id.strip()
            )
            if not input_node_ids:
                raise ValueError("Input nodes are required")
            payload_type = self._select_value("payload-type") or "step_payload"
            payload_kind = self._select_value("payload-kind") or "payload"
            content = _parse_json_object(self._input_value("content-json"))
        except Exception as exc:
            self._set_error(str(exc))
            return
        self.dismiss(
            StepFormData(
                input_node_ids=input_node_ids,
                payload_type=payload_type,
                payload_kind=payload_kind,
                content=content,
            )
        )


class PayloadForm(_FormScreen):
    """Attach a payload to the selected node or step."""

    def __init__(self, *, target_kind: TargetKind, target_id: str) -> None:
        super().__init__()
        self._target_kind = target_kind
        self._target_id = target_id

    def compose(self) -> ComposeResult:
        default_payload_type = (
            "node_payload" if self._target_kind == "node" else "step_payload"
        )
        default_payload_kind = "note" if self._target_kind == "node" else "observation"
        payload_kind_options = (
            NODE_PAYLOAD_KINDS
            if self._target_kind == "node"
            else STEP_PAYLOAD_KINDS
        )
        with Container(classes="editor-dialog"):
            yield Label("Attach Payload", classes="editor-title")
            yield Label(f"Target: {self._target_kind} {self._target_id}")
            yield Label("Payload type")
            yield Select(
                _payload_type_options(self._target_kind, include_cut=True),
                value=default_payload_type,
                allow_blank=False,
                id="payload-type",
            )
            yield Label("Type")
            yield Select(
                payload_kind_options,
                value=default_payload_kind,
                allow_blank=False,
                id="payload-kind",
            )
            yield Label("Content JSON")
            yield Input(value="{}", id="content-json")
            yield Static("", id="form-error")
            with Horizontal(classes="editor-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Attach", id="submit", variant="primary")

    def _submit(self) -> None:
        try:
            payload_type = self._select_value("payload-type")
            if not payload_type:
                raise ValueError("Payload type is required")
            payload_kind = self._select_value("payload-kind") or "payload"
            content = _parse_json_object(self._input_value("content-json"))
        except Exception as exc:
            self._set_error(str(exc))
            return
        self.dismiss(
            PayloadFormData(
                target_kind=self._target_kind,
                target_id=self._target_id,
                payload_type=payload_type,
                payload_kind=payload_kind,
                content=content,
            )
        )


def _payload_type_options(
    target_kind: TargetKind,
    *,
    include_cut: bool,
) -> tuple[PayloadOption, ...]:
    candidates: list[PayloadOption] = []
    labels = {
        "node_payload": "NodePayload",
        "step_payload": "StepPayload",
        "cut": "CutPayload",
        "git_change": "GitChangePayload",
    }
    for payload_type in payload_type_names():
        if payload_type == "git_change":
            continue
        if payload_type == "cut" and not include_cut:
            continue
        if target_kind == "node" and payload_type not in {"node_payload", "cut"}:
            continue
        if target_kind == "step" and payload_type not in {"step_payload", "cut"}:
            continue
        label = labels.get(payload_type, payload_type)
        candidates.append((f"{label} ({payload_type})", payload_type))
    return tuple(candidates)


class GitPayloadForm(_FormScreen):
    """Attach Git commits to a step as a GitChangePayload."""

    def __init__(self, *, step_id: str) -> None:
        super().__init__()
        self._step_id = step_id

    def compose(self) -> ComposeResult:
        with Container(classes="editor-dialog"):
            yield Label("Attach Git Payload", classes="editor-title")
            yield Label(f"Step: {self._step_id}")
            yield Label("Commits")
            yield Input(placeholder="HEAD, abc123, ...", id="commits")
            yield Static("", id="form-error")
            with Horizontal(classes="editor-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Attach", id="submit", variant="primary")

    def _submit(self) -> None:
        raw = self._input_value("commits")
        commits = tuple(part for part in raw.replace(",", " ").split() if part)
        if not commits:
            self._set_error("At least one commit is required")
            return
        self.dismiss(GitPayloadFormData(step_id=self._step_id, commits=commits))
