"""Versioned progress checkpoints, never a suspended scene or battle."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from functools import lru_cache
from pathlib import Path

from drift_with_me.config import load_data_json
from drift_with_me.east_site import SITE_FACTS, EastSiteProgress
from drift_with_me.field_visit import OBSERVATIONS, FieldProgress
from drift_with_me.office import (
    CaseState,
    Classification,
    FieldResult,
    FieldTask,
    OfficePrototype,
)
from drift_with_me.week_cycle import WorkWeek, load_week_office

SAVE_VERSION = 2
MAX_SAVE_BYTES = 64 * 1024
SAVE_KEY = "driftwithme.progress.v1"
FACTS = set(SITE_FACTS.values())


@lru_cache(maxsize=1)
def model_save_limits():
    config = load_data_json("game_config.json")["resources"]
    enemies = {e["id"] for e in load_data_json("prototype_world.json")["enemies"]}
    return config, enemies


def resource_number(value, maximum):
    if type(value) not in (int, float) or not 0 <= value <= maximum or not math.isfinite(value):
        raise ValueError("invalid resource")
    return float(value)


def string_set(value, allowed):
    if not isinstance(value, list) or len(value) != len(set(value)):
        raise ValueError("invalid list")
    if any(not isinstance(v, str) or v not in allowed for v in value):
        raise ValueError("unknown progress")
    return set(value)


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("invalid number")
    return value


def office_snapshot(office):
    data = {
        "index": office.current_index,
        "sessions": {
            key: {
                "state": s.state.value,
                "asked": sorted(s.asked_question_ids),
                "classification": s.selected_classification.value
                if s.selected_classification
                else None,
                "result": {
                    "code": s.field_result.result_code,
                    "facts": list(s.field_result.discovered_fact_ids),
                }
                if s.field_result
                else None,
                "field": {
                    "observations": sorted(s.field_progress.observations),
                    "completed": sorted(s.field_progress.conversations_completed),
                    "positions": dict(s.field_progress.conversation_positions),
                    "enemies": sorted(s.field_progress.enemy_ids),
                    "dealt": sorted(s.field_progress.dealt_target_ids),
                    "interrupted": s.field_progress.interrupted,
                },
            }
            for key, s in office.sessions.items()
        },
    }

    if hasattr(office, "site_progress"):
        sites = office.site_progress
        data["site"] = {
            "facts": sorted(sites.facts),
            "positions": dict(sites.positions),
            "reported": sorted(sites.reported),
        }
    return data


def snapshot(app):
    offices = dict(app.week_office_history)
    offices[app.work_week] = app.office
    return {
        "version": SAVE_VERSION,
        "resources": {"water": app.model.water, "energy": app.model.energy},
        "defeated": sorted(e.id for e in app.model.enemies if e.state == "DEFEATED"),
        "week": [app.work_week.month, app.work_week.number],
        "offices": {f"{w.month}:{w.number}": office_snapshot(o) for w, o in offices.items()},
        "facts": sorted(app.east_site_progress.facts),
        "positions": dict(app.east_site_progress.positions),
        "reported": app.office.complete and app.work_week == WorkWeek(6, 2),
        "seen": sorted(getattr(app, "first_sight_seen", set())),
    }


def restore_office(raw, week):
    office = OfficePrototype.load() if week == WorkWeek() else load_week_office(week)
    week3 = week == WorkWeek(6, 3)
    keys = {"index", "sessions", "site"} if week3 else {"index", "sessions"}
    if office is None or not isinstance(raw, dict) or set(raw) != keys:
        raise ValueError("unsupported office")
    if week3:
        from drift_with_me.week3 import FACTS as W3_FACTS
        from drift_with_me.week3 import LINES, Week3Progress
        from drift_with_me.week3 import SITE_FACTS as W3_SITES

        site = raw["site"]
        if not isinstance(site, dict) or set(site) != {"facts", "positions", "reported"}:
            raise ValueError("invalid week3 record")
        facts = string_set(site["facts"], W3_FACTS)
        reported = string_set(site["reported"], facts)
        positions = site["positions"]
        if not isinstance(positions, dict) or any(
            k not in W3_SITES
            or type(v) is not int
            or not 0 <= v < len(LINES[k])
            or W3_SITES[k] in facts
            for k, v in positions.items()
        ):
            raise ValueError("invalid week3 conversation")
        office.site_progress = Week3Progress(facts, dict(positions), reported)
        office.refresh_reports()
    index = integer(raw["index"], 0, len(office.cases))
    if not isinstance(raw["sessions"], dict) or set(raw["sessions"]) != set(office.sessions):
        raise ValueError("case mismatch")
    for case in office.cases:
        entry = raw["sessions"][case.case_id]
        if not isinstance(entry, dict) or set(entry) != {
            "state",
            "asked",
            "classification",
            "result",
            "field",
        }:
            raise ValueError("invalid case")
        s = office.sessions[case.case_id]
        s.state = CaseState(entry["state"])
        s.asked_question_ids = string_set(entry["asked"], {q.question_id for q in case.questions})
        s.memo_facts = [
            f
            for q in case.questions
            if q.question_id in s.asked_question_ids
            for f in q.memo_updates
        ]
        s.selected_classification = (
            Classification(entry["classification"]) if entry["classification"] is not None else None
        )
        s.pending_dialogue_steps.clear()
        s.pending_question_id = None
        s.dialogue.clear()
        s.active_dialogue_line_count = 0
        s.completed_dialogue_turn_ids.clear()
        f = entry["field"]
        if (
            not isinstance(f, dict)
            or set(f)
            != {"observations", "completed", "positions", "enemies", "dealt", "interrupted"}
            or type(f["interrupted"]) is not bool
        ):
            raise ValueError("invalid field")
        observed = string_set(f["observations"], {v[0] for v in OBSERVATIONS.values()})
        completed = string_set(f["completed"], set(OBSERVATIONS))
        positions = f["positions"]
        if not isinstance(positions, dict) or any(
            k not in OBSERVATIONS or type(v) is not int or not 0 <= v <= 20
            for k, v in positions.items()
        ):
            raise ValueError("invalid conversation")
        enemies = string_set(f["enemies"], {"urchin_abnormal_04"})
        dealt = string_set(f["dealt"], {"urchin_abnormal_04"})
        s.field_progress = FieldProgress(
            observations={k: text for k, text in OBSERVATIONS.values() if k in observed},
            conversations_completed=completed,
            conversation_positions=dict(positions),
            enemy_ids=enemies,
            dealt_target_ids=dealt,
            interrupted=f["interrupted"],
        )
        if case.case_id != "OFF-PROT-003" and s.field_progress.can_report:
            raise ValueError("foreign field facts")
        result = entry["result"]
        if result is not None:
            if (
                case.field_task is None
                or not isinstance(result, dict)
                or set(result) != {"code", "facts"}
            ):
                raise ValueError("invalid report")
            if case.case_id == "OFF-JUN-W3-SAGAN":
                if (
                    result["code"] != "WEEK3_CONFIRMED"
                    or string_set(result["facts"], W3_FACTS) != office.site_progress.facts
                ):
                    raise ValueError("invalid week3 report")
                code, facts, lines = (
                    "WEEK3_CONFIRMED",
                    tuple(sorted(office.site_progress.facts)),
                    (),
                )
            elif case.case_id == "OFF-JUN-W2-HERO":
                if (
                    result["code"] != "EAST_SITE_CONFIRMED"
                    or string_set(result["facts"], FACTS) != FACTS
                ):
                    raise ValueError("incomplete east report")
                code, facts, lines = "EAST_SITE_CONFIRMED", tuple(sorted(FACTS)), ()
            else:
                code, facts, lines = s.field_progress.report()
                if result["code"] != code or string_set(result["facts"], set(facts)) != set(facts):
                    raise ValueError("report mismatch")
            s.field_result = FieldResult(case.field_task.task_id, case.case_id, code, facts, lines)
        if s.state == CaseState.FIELD_RETURNED and s.field_result is None:
            raise ValueError("missing report")
        if s.state in {CaseState.FIELD_ACTIVE, CaseState.FIELD_CHECK_REQUIRED} and (
            case.field_task is None or s.field_result is not None
        ):
            raise ValueError("invalid task")
    office.current_index = index
    current = office.current_case
    s = office.current_session
    if current and s:
        state = s.state
        if state in {CaseState.NEW, CaseState.HEARING, CaseState.READY_TO_CLASSIFY}:
            s.state = CaseState.NEW
            office.begin_current_case()
            s.state = CaseState.HEARING if not s.asked_question_ids else CaseState.READY_TO_CLASSIFY
        elif state == CaseState.FIELD_ACTIVE:
            definition = current.field_task
            office.active_field_task = FieldTask(
                definition.task_id,
                current.case_id,
                definition.location_id,
                definition.title,
                definition.objective,
                tuple(f.line for f in s.memo_facts),
                definition.completion_condition_id,
            )
            s.field_task_id = definition.task_id
        elif state == CaseState.FIELD_RETURNED:
            definition = current.field_task
            office.active_field_task = FieldTask(
                definition.task_id,
                current.case_id,
                definition.location_id,
                definition.title,
                definition.objective,
                tuple(f.line for f in s.memo_facts),
                definition.completion_condition_id,
            )
            result = s.field_result
            s.state = CaseState.FIELD_ACTIVE
            if not office.complete_field_task(result):
                raise ValueError("invalid returned checkpoint")
        elif state in {CaseState.CLOSED_COUNTER, CaseState.REFERRED, CaseState.WAITING_DOCUMENTS}:
            script = office.current_counter_script
            if script:
                office._start_script_turns(
                    s, current.visitor.name, script.resolution.turns, s.asked_question_ids
                )
    if index == len(office.cases) and any(
        s.state != CaseState.RESOLVED for s in office.sessions.values()
    ):
        raise ValueError("unfinished office")
    if week3:
        sites = office.site_progress
        if any(
            office.sessions[c.case_id].state != CaseState.RESOLVED
            for c in office.cases[: min(index, 3)]
        ):
            raise ValueError("week3 order mismatch")
        if index >= 4 and office.sessions["OFF-JUN-W3-SAGAN"].field_result is None:
            raise ValueError("unconfirmed week3 return")
        if index == 4 and "hatch_matched" not in sites.facts:
            raise ValueError("unconfirmed hatch report")
        if index == 6 and (sites.facts != W3_FACTS or sites.reported != W3_FACTS):
            raise ValueError("unfinished week3 reports")
    return office


def decode(text):
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_SAVE_BYTES:
        raise ValueError("save too large")
    envelope = json.loads(text)
    if not isinstance(envelope, dict) or set(envelope) != {"payload", "sha256"}:
        raise ValueError("unknown schema")
    payload = envelope["payload"]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(canonical.encode()).hexdigest() != envelope["sha256"]:
        raise ValueError("damaged save")
    base_keys = {"version", "week", "offices", "facts", "positions", "reported", "seen"}
    if (
        not isinstance(payload, dict)
        or type(payload.get("version")) is not int
        or payload["version"] not in (1, SAVE_VERSION)
    ):
        raise ValueError("unsupported version")
    version = payload["version"]
    expected_keys = base_keys if version == 1 else base_keys | {"resources", "defeated"}
    if set(payload) != expected_keys:
        raise ValueError("unknown schema")
    w = payload["week"]
    if not isinstance(w, list) or len(w) != 2 or integer(w[0], 6, 6) != 6:
        raise ValueError("unsupported week")
    week = WorkWeek(6, integer(w[1], 1, 3))
    if (
        not isinstance(payload["offices"], dict)
        or set(payload["offices"]) - {"6:1", "6:2", "6:3"}
        or f"6:{week.number}" not in payload["offices"]
    ):
        raise ValueError("invalid history")
    offices = {
        WorkWeek(6, int(k[-1])): restore_office(v, WorkWeek(6, int(k[-1])))
        for k, v in payload["offices"].items()
    }
    facts = string_set(payload["facts"], FACTS)
    positions = payload["positions"]
    if not isinstance(positions, dict) or any(
        k not in SITE_FACTS or type(v) is not int or v not in (0, 1) or SITE_FACTS[k] in facts
        for k, v in positions.items()
    ):
        raise ValueError("invalid site conversation")
    if type(payload["reported"]) is not bool or payload["reported"] != (
        week == WorkWeek(6, 2) and offices[week].complete
    ):
        raise ValueError("report mismatch")
    hero = offices.get(WorkWeek(6, 2))
    if hero:
        result = hero.sessions["OFF-JUN-W2-HERO"].field_result
        if result and facts != FACTS:
            raise ValueError("lost site facts")
        construction = hero.sessions["OFF-JUN-W2-CONSTRUCTION"]
        if construction.state in {CaseState.CLOSED_COUNTER, CaseState.RESOLVED} and result is None:
            raise ValueError("unconfirmed construction")
    seen = string_set(payload["seen"], {"normal", "abnormal"})
    config, known_enemies = model_save_limits()
    dealt = {
        target
        for office in offices.values()
        for session in office.sessions.values()
        for target in session.field_progress.dealt_target_ids
    }
    if version == 1:
        # Legacy snapshots never contained resources or general enemy state.
        # Preserve every fact and infer permanent resolution only from authored reports.
        resources = {"water": float(config["water_start"]), "energy": float(config["energy_start"])}
        defeated = dealt
    else:
        raw_resources = payload["resources"]
        if not isinstance(raw_resources, dict) or set(raw_resources) != {"water", "energy"}:
            raise ValueError("invalid resources")
        resources = {
            "water": resource_number(raw_resources["water"], config["water_max"]),
            "energy": resource_number(raw_resources["energy"], config["energy_max"]),
        }
        defeated = string_set(payload["defeated"], known_enemies)
        if not dealt <= defeated:
            raise ValueError("resolved enemy returned")
    return week, offices, EastSiteProgress(facts, dict(positions)), seen, resources, defeated


def encode(payload):
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return json.dumps(
        {"payload": payload, "sha256": hashlib.sha256(canonical.encode()).hexdigest()},
        ensure_ascii=False,
    )


class ProgressStore:
    def __init__(self, path=None, browser_storage=None, enabled=True):
        self.enabled = enabled
        self.path = Path(path) if path else Path.home() / ".driftwithme" / "progress-v1.json"
        self.browser = browser_storage
        self.session = None
        self.message = ""
        self.available = True
        self.has_record = False
        self.write_protected = False
        self.new_game_authorized = False
        if enabled and browser_storage is None and sys.platform == "emscripten":
            try:
                from js import localStorage

                self.browser = localStorage
            except Exception:
                self.available = False
                self.message = "保存を利用できません。この間だけ続けられます"

    def read_raw(self, backup=False):
        if not self.enabled or not self.available:
            return self.session
        if self.browser is not None:
            value = self.browser.getItem(SAVE_KEY + (".backup" if backup else ""))
            return value if isinstance(value, str) else None
        path = self.path.with_suffix(".backup") if backup else self.path
        if path.exists() and path.stat().st_size > MAX_SAVE_BYTES:
            raise ValueError("save too large")
        return path.read_text(encoding="utf-8") if path.exists() else None

    def authorize_new_game(self):
        # Called only after the title's explicit new-game confirmation.
        self.write_protected = False
        self.new_game_authorized = True

    def load(self):
        if self.write_protected and self.session is not None:
            return decode(self.session)
        try:
            raw = self.read_raw()
            self.has_record = raw is not None
            if raw is None:
                return None
            result = decode(raw)
            if json.loads(raw)["payload"]["version"] == 1:
                self.message = "古い保存を引き継ぎます。水と電力は初期量です"
            return result
        except Exception:
            self.write_protected = True
            self.message = "保存を読み込めません。前の記録を確認します"
            try:
                backup = self.read_raw(backup=True)
                if backup:
                    result = decode(backup)
                    self.message = "前の保存で再開できます。保存はこの間だけです"
                    return result
            except Exception:
                pass
            self.message = "保存を読み込めません。新しく始められます"
            return None

    def write(self, payload):
        text = encode(payload)
        try:
            decode(text)
        except Exception:
            self.message = "この進行は保存できません。前の記録を残します"
            return False
        self.session = text
        if not self.enabled:
            return False
        if self.write_protected:
            self.message = "元の保存を残すため、保存できません。この間だけ続けられます"
            return False
        if not self.available:
            self.message = "保存できません。この間だけ続けられます"
            return False
        try:
            try:
                old = self.read_raw()
            except (ValueError, UnicodeError):
                if not self.new_game_authorized:
                    self.write_protected = True
                    self.message = "元の保存を残すため、保存できません。この間だけ続けられます"
                    return False
                old = None
            if old == text:
                return True
            # Preserve the last known valid record before replacing the main slot.
            if old:
                try:
                    decode(old)
                except Exception:
                    if not self.new_game_authorized:
                        self.write_protected = True
                        self.message = "元の保存を残すため、保存できません。この間だけ続けられます"
                        return False
                    old = None
            if self.browser is not None:
                if old:
                    self.browser.setItem(SAVE_KEY + ".backup", old)
                self.browser.setItem(SAVE_KEY, text)
            else:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                if old:
                    self.path.with_suffix(".backup").write_text(old, encoding="utf-8")
                temp = self.path.with_suffix(".tmp")
                with temp.open("w", encoding="utf-8") as f:
                    f.write(text)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp, self.path)
            self.new_game_authorized = False
            self.message = "保存しました"
            return True
        except Exception:
            self.available = False
            self.message = "保存できません。この間だけ続けられます"
            return False
