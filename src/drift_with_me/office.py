from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from drift_with_me import config


class Classification(StrEnum):
    COUNTER_COMPLETE = "COUNTER_COMPLETE"
    REFER_OTHER = "REFER_OTHER"
    MISSING_DOCUMENTS = "MISSING_DOCUMENTS"
    FIELD_CHECK = "FIELD_CHECK"


CLASSIFICATION_ORDER: tuple[Classification, ...] = (
    Classification.COUNTER_COMPLETE,
    Classification.REFER_OTHER,
    Classification.MISSING_DOCUMENTS,
    Classification.FIELD_CHECK,
)


class CaseState(StrEnum):
    NEW = "NEW"
    HEARING = "HEARING"
    READY_TO_CLASSIFY = "READY_TO_CLASSIFY"
    CLASSIFIED = "CLASSIFIED"
    CLOSED_COUNTER = "CLOSED_COUNTER"
    REFERRED = "REFERRED"
    WAITING_DOCUMENTS = "WAITING_DOCUMENTS"
    FIELD_CHECK_REQUIRED = "FIELD_CHECK_REQUIRED"
    FIELD_ACTIVE = "FIELD_ACTIVE"
    FIELD_RETURNED = "FIELD_RETURNED"
    RESOLVED = "RESOLVED"


@dataclass(frozen=True)
class MemoFact:
    fact_id: str
    label: str
    value: str

    @property
    def line(self) -> str:
        return f"{self.label}: {self.value}" if self.value else self.label


@dataclass(frozen=True)
class QuestionDefinition:
    question_id: str
    button_label: str
    jack_text: str
    visitor_reply: str
    answer_summary: str
    memo_updates: tuple[MemoFact, ...]


@dataclass(frozen=True)
class CounterDialogueTurn:
    turn_id: str
    jack_text: str
    visitor_reply: str
    required_question_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CounterResolutionDefinition:
    classification: Classification
    required_question_ids: tuple[str, ...]
    missing_feedback: str
    turns: tuple[CounterDialogueTurn, ...]


@dataclass(frozen=True)
class CounterFieldReturnDefinition:
    preamble: tuple[CounterDialogueTurn, ...]
    empty_report_text: str
    closing: tuple[CounterDialogueTurn, ...]


@dataclass(frozen=True)
class CounterScriptDefinition:
    case_id: str
    opening: tuple[CounterDialogueTurn, ...]
    after_question: dict[str, tuple[CounterDialogueTurn, ...]]
    resolution: CounterResolutionDefinition
    field_return: CounterFieldReturnDefinition | None
    feedback: dict[Classification, str]


@dataclass(frozen=True)
class VisitorDefinition:
    visitor_id: str
    name: str
    kind: str
    portrait_id: str


@dataclass(frozen=True)
class FieldTaskDefinition:
    task_id: str
    location_id: str
    title: str
    objective: str
    completion_condition_id: str


@dataclass(frozen=True)
class CaseDefinition:
    case_id: str
    title: str
    visitor: VisitorDefinition
    initial_purpose: str
    document_status: str
    questions: tuple[QuestionDefinition, ...]
    expected_classification: Classification
    field_task: FieldTaskDefinition | None


@dataclass(frozen=True)
class DialogueLine:
    speaker: str
    text: str


@dataclass(frozen=True)
class DialogueStep:
    step_id: str
    lines: tuple[DialogueLine, ...]


@dataclass(frozen=True)
class FieldTask:
    task_id: str
    case_id: str
    location_id: str
    title: str
    objective: str
    memo_lines: tuple[str, ...]
    completion_condition_id: str
    return_state: str = "OFFICE_FIELD_RETURN"


@dataclass(frozen=True)
class FieldResult:
    task_id: str
    case_id: str
    result_code: str
    discovered_fact_ids: tuple[str, ...]
    report_lines: tuple[str, ...]


@dataclass
class CaseSession:
    case_id: str
    asked_question_ids: set[str] = field(default_factory=set)
    memo_facts: list[MemoFact] = field(default_factory=list)
    dialogue: list[DialogueLine] = field(default_factory=list)
    active_dialogue_line_count: int = 0
    pending_dialogue_steps: list[DialogueStep] = field(default_factory=list)
    completed_dialogue_turn_ids: set[str] = field(default_factory=set)
    pending_question_id: str | None = None
    selected_question_id: str | None = None
    selected_classification: Classification | None = None
    state: CaseState = CaseState.NEW
    feedback: str = ""
    field_task_id: str | None = None
    field_result: FieldResult | None = None


CLASSIFICATION_RESULT_STATES: dict[Classification, CaseState] = {
    Classification.COUNTER_COMPLETE: CaseState.CLOSED_COUNTER,
    Classification.REFER_OTHER: CaseState.REFERRED,
    Classification.MISSING_DOCUMENTS: CaseState.WAITING_DOCUMENTS,
    Classification.FIELD_CHECK: CaseState.FIELD_CHECK_REQUIRED,
}

CLASSIFICATION_SUCCESS_FEEDBACK: dict[Classification, str] = {
    Classification.COUNTER_COMPLETE: "窓口で手続きを完了できます。",
    Classification.REFER_OTHER: "担当窓口をご案内します。",
    Classification.MISSING_DOCUMENTS: "不足書類をご案内し、再来所をお願いします。",
    Classification.FIELD_CHECK: "現地確認案件として登録します。",
}

CLASSIFICATION_RECONSIDER_FEEDBACK: dict[Classification, str] = {
    Classification.COUNTER_COMPLETE: "本人確認済みで、窓口で完了できる案件です。",
    Classification.REFER_OTHER: "住民課の手続きに当たるか、もう一度確認しましょう。",
    Classification.MISSING_DOCUMENTS: "添付書類の有無をもう一度確認しましょう。",
    Classification.FIELD_CHECK: "窓口だけで事実を確認できるか、もう一度考えましょう。",
}


class OfficePrototype:
    def __init__(
        self,
        cases: tuple[CaseDefinition, ...],
        counter_scripts: dict[str, CounterScriptDefinition] | None = None,
    ) -> None:
        if not cases:
            raise ValueError("office prototype requires at least one case")
        case_ids = tuple(case.case_id for case in cases)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("office case ids must be unique")
        self.cases = cases
        self.counter_scripts = counter_scripts or {}
        self.sessions = {case.case_id: CaseSession(case.case_id) for case in cases}
        self.current_index = 0
        self.active_field_task: FieldTask | None = None
        self.begin_current_case()

    @classmethod
    def load(cls) -> OfficePrototype:
        cases = parse_case_definitions(config.load_data_json("office_cases.json"))
        scripts = parse_counter_script_definitions(
            config.load_data_json("office_counter_scripts.json"),
            cases,
        )
        return cls(cases, scripts)

    @property
    def complete(self) -> bool:
        return self.current_index >= len(self.cases)

    @property
    def current_case(self) -> CaseDefinition | None:
        return None if self.complete else self.cases[self.current_index]

    @property
    def current_session(self) -> CaseSession | None:
        case = self.current_case
        return None if case is None else self.sessions[case.case_id]

    @property
    def current_counter_script(self) -> CounterScriptDefinition | None:
        case = self.current_case
        return None if case is None else self.counter_scripts.get(case.case_id)

    def active_dialogue_lines(self) -> tuple[DialogueLine, ...]:
        session = self.current_session
        if session is None or session.active_dialogue_line_count <= 0:
            return ()
        return tuple(session.dialogue[-session.active_dialogue_line_count :])

    def has_pending_dialogue_step(self) -> bool:
        session = self.current_session
        return bool(session and session.pending_dialogue_steps)

    def advance_dialogue_step(self) -> bool:
        session = self.current_session
        if session is None or not session.pending_dialogue_steps:
            return False
        self._show_dialogue_step(session, session.pending_dialogue_steps.pop(0))
        return True

    def _show_dialogue_step(self, session: CaseSession, step: DialogueStep) -> None:
        session.dialogue.extend(step.lines)
        session.active_dialogue_line_count = len(step.lines)
        session.completed_dialogue_turn_ids.add(step.step_id)

    @staticmethod
    def _step_from_turn(turn: CounterDialogueTurn, visitor_name: str) -> DialogueStep:
        return DialogueStep(
            step_id=turn.turn_id,
            lines=(
                DialogueLine("Jack", turn.jack_text),
                DialogueLine(visitor_name, turn.visitor_reply),
            ),
        )

    def _eligible_steps(
        self,
        session: CaseSession,
        visitor_name: str,
        turns: tuple[CounterDialogueTurn, ...],
        completed_question_ids: set[str],
    ) -> list[DialogueStep]:
        return [
            self._step_from_turn(turn, visitor_name)
            for turn in turns
            if turn.turn_id not in session.completed_dialogue_turn_ids
            and set(turn.required_question_ids) <= completed_question_ids
        ]

    def _start_script_turns(
        self,
        session: CaseSession,
        visitor_name: str,
        turns: tuple[CounterDialogueTurn, ...],
        completed_question_ids: set[str],
    ) -> bool:
        steps = self._eligible_steps(
            session,
            visitor_name,
            turns,
            completed_question_ids,
        )
        if not steps:
            return False
        self._show_dialogue_step(session, steps[0])
        session.pending_dialogue_steps.extend(steps[1:])
        return True

    def _queue_script_turns(
        self,
        session: CaseSession,
        visitor_name: str,
        turns: tuple[CounterDialogueTurn, ...],
        completed_question_ids: set[str],
    ) -> None:
        session.pending_dialogue_steps.extend(
            self._eligible_steps(
                session,
                visitor_name,
                turns,
                completed_question_ids,
            )
        )

    def begin_current_case(self) -> None:
        case = self.current_case
        session = self.current_session
        if case is None or session is None or session.state != CaseState.NEW:
            return
        session.state = CaseState.HEARING
        script = self.current_counter_script
        if script is not None and self._start_script_turns(
            session,
            case.visitor.name,
            script.opening,
            set(),
        ):
            return
        session.dialogue.append(DialogueLine(case.visitor.name, case.initial_purpose))
        session.active_dialogue_line_count = 1

    def ask_question(self, question_id: str) -> bool:
        case = self.current_case
        session = self.current_session
        if case is None or session is None:
            return False
        if session.pending_dialogue_steps or session.pending_question_id is not None:
            return False
        if session.state not in {CaseState.HEARING, CaseState.READY_TO_CLASSIFY}:
            return False
        question = next(
            (item for item in case.questions if item.question_id == question_id),
            None,
        )
        if question is None or question_id in session.asked_question_ids:
            return False
        session.selected_question_id = question_id
        session.pending_question_id = question_id
        session.dialogue.extend(
            (
                DialogueLine("Jack", question.jack_text),
                DialogueLine(case.visitor.name, question.visitor_reply),
            )
        )
        session.active_dialogue_line_count = 2
        script = self.current_counter_script
        if script is not None:
            self._queue_script_turns(
                session,
                case.visitor.name,
                script.after_question.get(question_id, ()),
                {*session.asked_question_ids, question_id},
            )
        return True

    def complete_pending_question(self) -> str | None:
        case = self.current_case
        session = self.current_session
        if (
            case is None
            or session is None
            or session.pending_question_id is None
            or session.pending_dialogue_steps
        ):
            return None
        question_id = session.pending_question_id
        question = next(
            (item for item in case.questions if item.question_id == question_id),
            None,
        )
        if question is None:
            session.pending_question_id = None
            return None
        session.pending_question_id = None
        session.asked_question_ids.add(question_id)
        known_fact_ids = {fact.fact_id for fact in session.memo_facts}
        session.memo_facts.extend(
            fact for fact in question.memo_updates if fact.fact_id not in known_fact_ids
        )
        session.state = CaseState.READY_TO_CLASSIFY
        session.feedback = ""
        return question_id

    def classify(self, classification: Classification | str) -> bool:
        case = self.current_case
        session = self.current_session
        if case is None or session is None:
            return False
        if session.pending_dialogue_steps or session.pending_question_id is not None:
            return False
        if session.state not in {CaseState.HEARING, CaseState.READY_TO_CLASSIFY}:
            return False
        selected = Classification(classification)
        session.selected_classification = selected
        script = self.current_counter_script
        if selected != case.expected_classification:
            session.feedback = (
                script.feedback.get(
                    selected,
                    CLASSIFICATION_RECONSIDER_FEEDBACK[case.expected_classification],
                )
                if script is not None
                else CLASSIFICATION_RECONSIDER_FEEDBACK[case.expected_classification]
            )
            session.state = (
                CaseState.READY_TO_CLASSIFY if session.asked_question_ids else CaseState.HEARING
            )
            return False
        if (
            script is not None
            and not set(script.resolution.required_question_ids) <= session.asked_question_ids
        ):
            session.feedback = script.resolution.missing_feedback
            session.state = (
                CaseState.READY_TO_CLASSIFY if session.asked_question_ids else CaseState.HEARING
            )
            return False
        session.state = CaseState.CLASSIFIED
        session.feedback = (
            script.feedback.get(selected, CLASSIFICATION_SUCCESS_FEEDBACK[selected])
            if script is not None
            else CLASSIFICATION_SUCCESS_FEEDBACK[selected]
        )
        session.state = CLASSIFICATION_RESULT_STATES[selected]
        if script is not None:
            self._start_script_turns(
                session,
                case.visitor.name,
                script.resolution.turns,
                set(session.asked_question_ids),
            )
        return True

    def prepare_field_task(self) -> FieldTask | None:
        case = self.current_case
        session = self.current_session
        if (
            case is None
            or session is None
            or session.state != CaseState.FIELD_CHECK_REQUIRED
            or case.field_task is None
            or session.pending_dialogue_steps
            or session.pending_question_id is not None
        ):
            return None
        definition = case.field_task
        task = FieldTask(
            task_id=definition.task_id,
            case_id=case.case_id,
            location_id=definition.location_id,
            title=definition.title,
            objective=definition.objective,
            memo_lines=tuple(fact.line for fact in session.memo_facts),
            completion_condition_id=definition.completion_condition_id,
        )
        session.field_task_id = task.task_id
        session.state = CaseState.FIELD_ACTIVE
        self.active_field_task = task
        return task

    def prepare_debug_field_task(self) -> FieldTask | None:
        field_case_index = next(
            (
                index
                for index, case in enumerate(self.cases)
                if case.expected_classification == Classification.FIELD_CHECK
                and case.field_task is not None
            ),
            None,
        )
        if field_case_index is None:
            return None

        self.current_index = field_case_index
        case = self.current_case
        if case is None:
            return None

        session = CaseSession(case.case_id)
        session.asked_question_ids = {question.question_id for question in case.questions}
        known_fact_ids: set[str] = set()
        for question in case.questions:
            for fact in question.memo_updates:
                if fact.fact_id in known_fact_ids:
                    continue
                known_fact_ids.add(fact.fact_id)
                session.memo_facts.append(fact)
        if case.questions:
            session.selected_question_id = case.questions[-1].question_id
        session.selected_classification = Classification.FIELD_CHECK
        session.state = CaseState.FIELD_CHECK_REQUIRED
        session.feedback = ""
        self.sessions[case.case_id] = session
        self.active_field_task = None
        return self.prepare_field_task()

    def complete_field_task(self, result: FieldResult) -> bool:
        session = self.current_session
        case = self.current_case
        task = self.active_field_task
        if (
            case is None
            or session is None
            or task is None
            or session.state != CaseState.FIELD_ACTIVE
        ):
            return False
        if result.task_id != task.task_id or result.case_id != task.case_id:
            return False
        session.field_result = result
        session.state = CaseState.FIELD_RETURNED
        session.feedback = "結果を記録しました。"
        self.active_field_task = None
        script = self.current_counter_script
        if script is not None and script.field_return is not None:
            field_return = script.field_return
            steps = self._eligible_steps(
                session,
                case.visitor.name,
                field_return.preamble,
                set(session.asked_question_ids),
            )
            report_lines = result.report_lines or (field_return.empty_report_text,)
            steps.extend(
                DialogueStep(
                    step_id=f"{result.task_id}:report:{index}",
                    lines=(DialogueLine("確認記録", line),),
                )
                for index, line in enumerate(report_lines)
                if f"{result.task_id}:report:{index}" not in session.completed_dialogue_turn_ids
            )
            steps.extend(
                self._eligible_steps(
                    session,
                    case.visitor.name,
                    field_return.closing,
                    set(session.asked_question_ids),
                )
            )
            if steps:
                self._show_dialogue_step(session, steps[0])
                session.pending_dialogue_steps.extend(steps[1:])
        return True

    def advance_case(self) -> bool:
        session = self.current_session
        if session is None:
            return False
        if session.pending_dialogue_steps or session.pending_question_id is not None:
            return False
        if session.state not in {
            CaseState.CLOSED_COUNTER,
            CaseState.REFERRED,
            CaseState.WAITING_DOCUMENTS,
            CaseState.FIELD_RETURNED,
        }:
            return False
        session.state = CaseState.RESOLVED
        self.current_index += 1
        self.begin_current_case()
        return True


def parse_case_definitions(raw: dict[str, Any]) -> tuple[CaseDefinition, ...]:
    cases: list[CaseDefinition] = []
    for item in raw.get("cases", ()):
        expected = Classification(str(item["expected_classification"]))
        field_raw = item.get("field_task")
        field_task = None
        if field_raw is not None:
            field_task = FieldTaskDefinition(
                task_id=str(field_raw["task_id"]),
                location_id=str(field_raw["location_id"]),
                title=str(field_raw["title"]),
                objective=str(field_raw["objective"]),
                completion_condition_id=str(field_raw["completion_condition_id"]),
            )
        if (expected == Classification.FIELD_CHECK) != (field_task is not None):
            raise ValueError(
                f"case {item['case_id']} must define field_task exactly for FIELD_CHECK"
            )
        questions: list[QuestionDefinition] = []
        for question in item.get("questions", ()):
            memo_updates = tuple(
                parse_memo_fact(str(question["id"]), index, str(line))
                for index, line in enumerate(question.get("memo", ()))
            )
            questions.append(
                QuestionDefinition(
                    question_id=str(question["id"]),
                    button_label=str(question["label"]),
                    jack_text=str(question["jack"]),
                    visitor_reply=str(question["reply"]),
                    answer_summary=str(question.get("answer_summary", question["reply"])),
                    memo_updates=memo_updates,
                )
            )
        visitor = item["visitor"]
        cases.append(
            CaseDefinition(
                case_id=str(item["case_id"]),
                title=str(item["title"]),
                visitor=VisitorDefinition(
                    visitor_id=str(visitor["id"]),
                    name=str(visitor["name"]),
                    kind=str(visitor["kind"]),
                    portrait_id=str(visitor["portrait_id"]),
                ),
                initial_purpose=str(item["initial_purpose"]),
                document_status=str(item["document_status"]),
                questions=tuple(questions),
                expected_classification=expected,
                field_task=field_task,
            )
        )
    return tuple(cases)


def parse_counter_script_definitions(
    raw: dict[str, Any],
    cases: tuple[CaseDefinition, ...],
) -> dict[str, CounterScriptDefinition]:
    case_by_id = {case.case_id: case for case in cases}
    scripts: dict[str, CounterScriptDefinition] = {}
    turn_ids: set[str] = set()
    for item in raw.get("cases", ()):
        case_id = str(item["case_id"])
        if case_id in scripts or case_id not in case_by_id:
            raise ValueError(f"unknown or duplicate counter script case: {case_id}")
        case = case_by_id[case_id]
        question_ids = {question.question_id for question in case.questions}
        opening = parse_counter_dialogue_turns(item.get("opening", ()), turn_ids)
        after_question: dict[str, tuple[CounterDialogueTurn, ...]] = {}
        for question_id, turns_raw in item.get("after_question", {}).items():
            question_id = str(question_id)
            if question_id not in question_ids:
                raise ValueError(f"unknown scripted question {case_id}:{question_id}")
            after_question[question_id] = parse_counter_dialogue_turns(turns_raw, turn_ids)

        resolution_raw = item["resolution"]
        resolution_classification = Classification(str(resolution_raw["classification"]))
        if resolution_classification != case.expected_classification:
            raise ValueError(f"counter resolution mismatch for {case_id}")
        required_question_ids = tuple(
            str(value) for value in resolution_raw.get("requires_completed_questions", ())
        )
        if not set(required_question_ids) <= question_ids:
            raise ValueError(f"unknown resolution question for {case_id}")
        resolution = CounterResolutionDefinition(
            classification=resolution_classification,
            required_question_ids=required_question_ids,
            missing_feedback=str(resolution_raw.get("if_requirements_missing", "")),
            turns=parse_counter_dialogue_turns(resolution_raw.get("turns", ()), turn_ids),
        )

        field_return_raw = item.get("field_return")
        field_return = None
        if field_return_raw is not None:
            if case.field_task is None:
                raise ValueError(f"field return script without field task for {case_id}")
            field_return = CounterFieldReturnDefinition(
                preamble=parse_counter_dialogue_turns(
                    field_return_raw.get("preamble", ()), turn_ids
                ),
                empty_report_text=str(
                    field_return_raw.get("empty_report_text", "現地確認の詳細記録はありません。")
                ),
                closing=parse_counter_dialogue_turns(field_return_raw.get("closing", ()), turn_ids),
            )

        feedback = {
            Classification(str(key)): str(value) for key, value in item.get("feedback", {}).items()
        }
        scripts[case_id] = CounterScriptDefinition(
            case_id=case_id,
            opening=opening,
            after_question=after_question,
            resolution=resolution,
            field_return=field_return,
            feedback=feedback,
        )
        for turn in (*opening, *resolution.turns):
            validate_counter_turn_requirements(case_id, turn, question_ids)
        for turns in after_question.values():
            for turn in turns:
                validate_counter_turn_requirements(case_id, turn, question_ids)
        if field_return is not None:
            for turn in (*field_return.preamble, *field_return.closing):
                validate_counter_turn_requirements(case_id, turn, question_ids)

    if set(scripts) != set(case_by_id):
        missing = sorted(set(case_by_id) - set(scripts))
        raise ValueError(f"missing counter scripts: {', '.join(missing)}")
    return scripts


def parse_counter_dialogue_turns(
    turns_raw: Any,
    known_turn_ids: set[str],
) -> tuple[CounterDialogueTurn, ...]:
    turns: list[CounterDialogueTurn] = []
    for raw in turns_raw:
        turn_id = str(raw["turn_id"])
        if turn_id in known_turn_ids:
            raise ValueError(f"duplicate counter dialogue turn: {turn_id}")
        known_turn_ids.add(turn_id)
        turns.append(
            CounterDialogueTurn(
                turn_id=turn_id,
                jack_text=str(raw["jack"]),
                visitor_reply=str(raw["reply"]),
                required_question_ids=tuple(
                    str(value) for value in raw.get("requires_completed_questions", ())
                ),
            )
        )
    return tuple(turns)


def validate_counter_turn_requirements(
    case_id: str,
    turn: CounterDialogueTurn,
    question_ids: set[str],
) -> None:
    if not set(turn.required_question_ids) <= question_ids:
        raise ValueError(f"unknown turn requirement for {case_id}:{turn.turn_id}")


def parse_memo_fact(question_id: str, index: int, line: str) -> MemoFact:
    label, separator, value = line.partition(":")
    return MemoFact(
        fact_id=f"{question_id}:{index}",
        label=label.strip(),
        value=value.strip() if separator else "",
    )
