"""Request and response shapes."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORMModel):
    id: int
    name: str
    email: str
    is_active: bool


class ProjectOut(ORMModel):
    id: int
    name: str
    announcement: str | None = None
    is_completed: bool
    suite_mode: int


class SuiteOut(ORMModel):
    id: int
    project_id: int
    name: str
    description: str | None = None
    is_completed: bool
    # filled in by the endpoint; the suite list is useless without them
    section_count: int = 0
    case_count: int = 0
    run_count: int = 0


class SectionOut(ORMModel):
    id: int
    suite_id: int
    parent_id: int | None = None
    name: str
    description: str | None = None
    depth: int
    display_order: int


class SectionNode(SectionOut):
    children: list["SectionNode"] = Field(default_factory=list)
    case_count: int = 0


class StepIn(BaseModel):
    content: str | None = None
    expected: str | None = None
    additional_info: str | None = None
    refs: str | None = None


class StepOut(ORMModel):
    idx: int
    content: str | None = None
    expected: str | None = None
    additional_info: str | None = None
    refs: str | None = None


class CaseOut(ORMModel):
    id: int
    section_id: int
    suite_id: int
    title: str
    template_id: int | None = None
    type_id: int | None = None
    priority_id: int | None = None
    milestone_id: int | None = None
    refs: str | None = None
    estimate: str | None = None
    is_deleted: bool
    created_by: int | None = None
    created_on: datetime | None = None
    updated_by: int | None = None
    updated_on: datetime | None = None
    custom: dict = Field(default_factory=dict)
    steps: list[StepOut] = Field(default_factory=list)


class CaseSummary(ORMModel):
    """The row shape the case grid needs; deliberately narrow."""
    id: int
    section_id: int
    title: str
    type_id: int | None = None
    priority_id: int | None = None
    refs: str | None = None
    updated_on: datetime | None = None


class CaseCreate(BaseModel):
    section_id: int
    title: str
    template_id: int | None = None
    type_id: int | None = None
    priority_id: int | None = None
    milestone_id: int | None = None
    refs: str | None = None
    estimate: str | None = None
    custom: dict = Field(default_factory=dict)
    steps: list[StepIn] = Field(default_factory=list)


class CaseUpdate(BaseModel):
    title: str | None = None
    section_id: int | None = None
    template_id: int | None = None
    type_id: int | None = None
    priority_id: int | None = None
    milestone_id: int | None = None
    refs: str | None = None
    estimate: str | None = None
    custom: dict | None = None
    steps: list[StepIn] | None = None


class Page(BaseModel):
    total: int
    offset: int
    limit: int


class CasePage(Page):
    items: list[CaseSummary]


class TestPage(Page):
    items: list["TestOut"]


class MilestoneOut(ORMModel):
    id: int
    project_id: int
    parent_id: int | None = None
    name: str
    description: str | None = None
    start_on: datetime | None = None
    due_on: datetime | None = None
    completed_on: datetime | None = None
    is_completed: bool
    is_started: bool


class ProjectStats(BaseModel):
    """Headline numbers for the project overview."""
    project_id: int
    suites: int
    sections: int
    cases: int
    runs: int
    active_runs: int
    archived_runs: int = 0
    milestones: int
    open_milestones: int
    tests: int
    by_status: dict[str, int]


class ActivityItem(BaseModel):
    run_id: int
    run_name: str
    test_id: int
    test_title: str
    status_id: int | None = None
    created_on: datetime
    created_by: int | None = None


class RunOut(ORMModel):
    id: int
    project_id: int
    suite_id: int | None = None
    milestone_id: int | None = None
    assignedto_id: int | None = None
    name: str
    description: str | None = None
    is_completed: bool
    config: str | None = None
    created_on: datetime | None = None
    # progress, computed from the tests rather than stored
    is_archived: bool = False
    test_count: int = 0
    passed_count: int = 0
    untested_count: int = 0


class TestOut(ORMModel):
    id: int
    run_id: int
    case_id: int | None = None
    title: str
    status_id: int | None = None
    assignedto_id: int | None = None


class ResultOut(ORMModel):
    id: int
    test_id: int
    status_id: int | None = None
    created_by: int | None = None
    created_on: datetime
    comment: str | None = None
    version: str | None = None
    elapsed: str | None = None
    defects: str | None = None
    custom: dict = Field(default_factory=dict)
    # declared as forward references; the step/attachment shapes are defined
    # below and resolved by the model_rebuild at the end of this module
    step_results: list["StepResultOut"] = Field(default_factory=list)
    attachments: list[dict] = Field(default_factory=list)


class StepResultIn(BaseModel):
    idx: int
    content: str | None = None
    expected: str | None = None
    actual: str | None = None
    status_id: int | None = None


class StepResultOut(ORMModel):
    idx: int
    content: str | None = None
    expected: str | None = None
    actual: str | None = None
    status_id: int | None = None


class ResultCreate(BaseModel):
    status_id: int
    comment: str | None = None
    version: str | None = None
    elapsed: str | None = None
    defects: str | None = None
    assignedto_id: int | None = None
    custom: dict = Field(default_factory=dict)
    # one row per case step, so a tester can say which step broke instead of
    # writing "step 4 failed" into a comment
    step_results: list[StepResultIn] = Field(default_factory=list)
    # ids returned by the attachment upload, linked once the result exists
    attachment_ids: list[str] = Field(default_factory=list)


class TestPatch(BaseModel):
    assignedto_id: int | None = None


class CustomFieldOut(ORMModel):
    id: int
    entity: str
    system_name: str
    label: str
    field_type: str
    is_global: bool
    display_order: int
    # per-project scoping: the UI hides fields a project does not use, the
    # way TestRail only shows the fields assigned to that project
    configs: list = Field(default_factory=list)


class CatalogOut(BaseModel):
    """Everything the UI needs to render a case form, in one call."""
    case_types: list[dict]
    priorities: list[dict]
    statuses: list[dict]
    templates: list[dict]
    case_fields: list[CustomFieldOut]
    result_fields: list[CustomFieldOut]
    field_options: dict[str, list[dict]]


SectionNode.model_rebuild()
ResultOut.model_rebuild()


# --- writes -----------------------------------------------------------------

class MilestoneCreate(BaseModel):
    name: str
    description: str | None = None
    parent_id: int | None = None
    refs: str | None = None
    start_on: datetime | None = None
    due_on: datetime | None = None


class MilestoneUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    parent_id: int | None = None
    refs: str | None = None
    start_on: datetime | None = None
    due_on: datetime | None = None
    is_started: bool | None = None
    is_completed: bool | None = None


class RunCreate(BaseModel):
    suite_id: int
    name: str
    description: str | None = None
    milestone_id: int | None = None
    assignedto_id: int | None = None
    refs: str | None = None
    include_all: bool = True
    # honoured only when include_all is false
    case_ids: list[int] = Field(default_factory=list)
    # narrow the "all cases" selection without listing every id
    section_ids: list[int] = Field(default_factory=list)


class RunUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    milestone_id: int | None = None
    assignedto_id: int | None = None
    is_completed: bool | None = None


class SectionCreate(BaseModel):
    suite_id: int
    name: str
    description: str | None = None
    parent_id: int | None = None


class SectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    # present-but-null is a real value here (move to the root), which is why
    # every writer uses exclude_unset rather than dropping Nones
    parent_id: int | None = None
    display_order: int | None = None


class SuiteUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_completed: bool | None = None


class CaseIds(BaseModel):
    case_ids: list[int] = Field(default_factory=list)


class SuiteCreate(BaseModel):
    name: str
    description: str | None = None


class UserCreate(BaseModel):
    name: str
    email: str
    role_id: int | None = None
    password: str | None = None
    is_active: bool = True


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    role_id: int | None = None
    is_active: bool | None = None
    password: str | None = None


class UserAdminOut(ORMModel):
    id: int
    name: str
    email: str
    is_active: bool
    role_id: int | None = None
    has_password: bool = False
    last_login_at: datetime | None = None


class RoleOut(ORMModel):
    id: int
    name: str
    is_default: bool
    is_project_default: bool


class CustomFieldCreate(BaseModel):
    entity: str = "case"
    system_name: str
    label: str
    description: str | None = None
    field_type: str
    is_global: bool = True
    project_ids: list[int] = Field(default_factory=list)
    options: list[dict] = Field(default_factory=list)


class CustomFieldUpdate(BaseModel):
    label: str | None = None
    description: str | None = None
    is_global: bool | None = None
    project_ids: list[int] | None = None
    options: list[dict] | None = None
    display_order: int | None = None


class TodoItem(BaseModel):
    project_id: int
    project_name: str
    run_id: int
    run_name: str
    test_id: int
    test_title: str
    status_id: int | None = None


class SeriesPoint(BaseModel):
    label: str
    values: dict[str, int]


class DistributionOut(BaseModel):
    title: str
    buckets: list[dict]
    total: int
