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
    jack_text: str
    visitor_reply: str
    memo_updates: tuple[MemoFact, ...]


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
    def __init__(self, cases: tuple[CaseDefinition, ...]) -> None:
        if not cases:
            raise ValueError("office prototype requires at least one case")
        case_ids = tuple(case.case_id for case in cases)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("office case ids must be unique")
        self.cases = cases
        self.sessions = {case.case_id: CaseSession(case.case_id) for case in cases}
        self.current_index = 0
        self.active_field_task: FieldTask | None = None
        self.begin_current_case()

    @classmethod
    def load(cls) -> OfficePrototype:
        return cls(parse_case_definitions(config.load_data_json("office_cases.json")))

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

    def begin_current_case(self) -> None:
        case = self.current_case
        session = self.current_session
        if case is None or session is None or session.state != CaseState.NEW:
            return
        session.state = CaseState.HEARING
        session.dialogue.append(DialogueLine(case.visitor.name, case.initial_purpose))

    def ask_question(self, question_id: str) -> bool:
        case = self.current_case
        session = self.current_session
        if case is None or session is None:
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
        session.asked_question_ids.add(question_id)
        session.dialogue.extend(
            (
                DialogueLine("Jack", question.jack_text),
                DialogueLine(case.visitor.name, question.visitor_reply),
            )
        )
        known_fact_ids = {fact.fact_id for fact in session.memo_facts}
        session.memo_facts.extend(
            fact for fact in question.memo_updates if fact.fact_id not in known_fact_ids
        )
        session.state = CaseState.READY_TO_CLASSIFY
        session.feedback = ""
        return True

    def classify(self, classification: Classification | str) -> bool:
        case = self.current_case
        session = self.current_session
        if case is None or session is None:
            return False
        if session.state not in {CaseState.HEARING, CaseState.READY_TO_CLASSIFY}:
            return False
        selected = Classification(classification)
        session.selected_classification = selected
        if selected != case.expected_classification:
            session.feedback = CLASSIFICATION_RECONSIDER_FEEDBACK[case.expected_classification]
            session.state = (
                CaseState.READY_TO_CLASSIFY if session.asked_question_ids else CaseState.HEARING
            )
            return False
        session.state = CaseState.CLASSIFIED
        session.feedback = CLASSIFICATION_SUCCESS_FEEDBACK[selected]
        session.state = CLASSIFICATION_RESULT_STATES[selected]
        return True

    def prepare_field_task(self) -> FieldTask | None:
        case = self.current_case
        session = self.current_session
        if (
            case is None
            or session is None
            or session.state != CaseState.FIELD_CHECK_REQUIRED
            or case.field_task is None
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

    def complete_field_task(self, result: FieldResult) -> bool:
        session = self.current_session
        task = self.active_field_task
        if session is None or task is None or session.state != CaseState.FIELD_ACTIVE:
            return False
        if result.task_id != task.task_id or result.case_id != task.case_id:
            return False
        session.field_result = result
        session.state = CaseState.FIELD_RETURNED
        session.feedback = "結果を記録しました。"
        self.active_field_task = None
        return True

    def advance_case(self) -> bool:
        session = self.current_session
        if session is None:
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
                    jack_text=str(question["jack"]),
                    visitor_reply=str(question["reply"]),
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


def parse_memo_fact(question_id: str, index: int, line: str) -> MemoFact:
    label, separator, value = line.partition(":")
    return MemoFact(
        fact_id=f"{question_id}:{index}",
        label=label.strip(),
        value=value.strip() if separator else "",
    )
