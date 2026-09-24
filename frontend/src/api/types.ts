export interface User { id: number; name: string; email: string; is_active: boolean }

export interface Project {
  id: number
  name: string
  announcement: string | null
  is_completed: boolean
  suite_mode: number
}

export interface ProjectMember {
  user_id: number
  role_id: number | null
  name: string
  email: string
}

export interface Suite {
  id: number
  project_id: number
  name: string
  description: string | null
  is_completed: boolean
  section_count: number
  case_count: number
  run_count: number
}

export interface SectionNode {
  id: number
  suite_id: number
  parent_id: number | null
  name: string
  description: string | null
  depth: number
  display_order: number
  case_count: number
  children: SectionNode[]
}

export interface Step {
  idx: number
  content: string | null
  expected: string | null
  additional_info: string | null
  refs: string | null
}

export interface CaseSummary {
  id: number
  section_id: number
  title: string
  type_id: number | null
  priority_id: number | null
  refs: string | null
  updated_on: string | null
}

export interface TestCase extends CaseSummary {
  suite_id: number
  template_id: number | null
  milestone_id: number | null
  estimate: string | null
  is_deleted: boolean
  created_by: number | null
  created_on: string | null
  updated_by: number | null
  custom: Record<string, unknown>
  steps: Step[]
}

export interface DashboardProject {
  project_id: number
  name: string
  is_completed: boolean
  cases: number
  active_runs: number
  tests: number
  passed: number
  failed: number
  untested: number
  pass_rate: number | null
  results_in_window: number
  open_milestones: number
  overdue_milestones: number
}

export interface DashboardOut {
  days: number
  generated_on: string
  totals: {
    projects: number
    cases: number
    active_runs: number
    results_in_window: number
    open_milestones: number
    overdue_milestones: number
  }
  projects: DashboardProject[]
}

export interface NotificationPreference {
  kind: string
  label: string
  in_app: boolean
  email: boolean
}

export interface ReportSubscription {
  id: number
  project_id: number | null
  project_name: string
  kind: string
  kind_label: string
  frequency: string
  hour: number
  weekday: number
  by_email: boolean
  is_active: boolean
  last_sent_on: string | null
}

export interface SubscriptionList {
  kinds: { key: string; label: string }[]
  items: ReportSubscription[]
}

export interface DigestPreview {
  empty: boolean
  subject?: string
  body?: string
  detail?: string
}

export interface FlakyCase {
  case_id: number
  title: string
  suite_id: number
  passed: number
  failed: number
  runs: number
  flip_rate: number
  last_seen: string | null
}

export interface DuplicateGroup {
  section_id: number
  section_name: string
  title: string
  count: number
  case_ids: number[]
}

export interface NeverRunCase {
  case_id: number
  title: string
  section_id: number
  section_name: string
  created_on: string | null
}

export interface AuditEntry {
  id: number
  created_on: string
  user_id: number | null
  user_name: string | null
  action: string
  entity_type: string
  entity_id: string | null
  label: string | null
  project_id: number | null
  project_name: string | null
  detail: Record<string, unknown>
  ip: string | null
}

export interface AuditPage {
  total: number
  offset: number
  limit: number
  items: AuditEntry[]
}

export interface Attachment {
  id: string
  filename: string
  size: number
  content_type: string | null
  created_on?: string | null
  url: string
}

export interface CasePage {
  total: number
  offset: number
  limit: number
  items: CaseSummary[]
}

export interface Milestone {
  id: number
  project_id: number
  parent_id: number | null
  name: string
  description: string | null
  start_on: string | null
  due_on: string | null
  completed_on: string | null
  is_completed: boolean
  is_started: boolean
}

export interface Run {
  id: number
  project_id: number
  suite_id: number | null
  milestone_id: number | null
  assignedto_id: number | null
  name: string
  description: string | null
  is_completed: boolean
  config: string | null
  created_on: string | null
  is_archived: boolean
  test_count: number
  passed_count: number
  untested_count: number
}

export interface ProjectStats {
  project_id: number
  suites: number
  sections: number
  cases: number
  runs: number
  active_runs: number
  archived_runs: number
  milestones: number
  open_milestones: number
  tests: number
  by_status: Record<string, number>
}

export interface ActivityItem {
  run_id: number
  run_name: string
  test_id: number
  test_title: string
  status_id: number | null
  created_on: string
  created_by: number | null
}

export interface Test {
  id: number
  run_id: number
  case_id: number | null
  title: string
  status_id: number | null
  assignedto_id: number | null
}

export interface StepResult {
  idx: number
  content: string | null
  expected: string | null
  actual: string | null
  status_id: number | null
}

export interface TestPage {
  total: number
  offset: number
  limit: number
  items: Test[]
}

export interface Result {
  id: number
  test_id: number
  status_id: number | null
  created_by: number | null
  created_on: string
  comment: string | null
  version: string | null
  elapsed: string | null
  defects: string | null
  custom: Record<string, unknown>
  step_results: StepResult[]
  attachments: Attachment[]
}

/** A test opened on its own: the case steps it was made from come with it. */
export interface TestDetail extends Test {
  refs: string | null
  type_id: number | null
  priority_id: number | null
  custom: Record<string, unknown>
  is_archived: boolean
  steps: {
    idx: number
    content: string | null
    expected: string | null
    additional_info: string | null
    status_id: number | null
  }[]
}

export interface HistoryEntry {
  id: number
  user_id: number | null
  created_on: string
  changes: { field: string; old_text?: string; new_text?: string }[]
  source: string
}

export interface FieldConfig {
  context?: { is_global?: boolean; project_ids?: number[] | null }
  options?: Record<string, unknown>
}

export interface CustomField {
  id: number
  entity: 'case' | 'result'
  system_name: string
  label: string
  field_type: string
  is_global: boolean
  display_order: number
  configs: FieldConfig[]
}

export interface Catalog {
  case_types: { id: number; name: string; is_default: boolean }[]
  priorities: { id: number; name: string; short_name: string | null; priority_level: number }[]
  statuses: { id: number; name: string; label: string; color: string | null; is_untested: boolean }[]
  templates: { id: number; name: string; is_default: boolean }[]
  case_fields: CustomField[]
  result_fields: CustomField[]
  field_options: Record<string, { value: number; label: string }[]>
}

export interface RunSummary {
  run_id: number
  by_status: Record<string, number>
  total: number
}


export interface TodoItem {
  project_id: number
  project_name: string
  run_id: number
  run_name: string
  test_id: number
  test_title: string
  status_id: number | null
}

export interface Distribution {
  title: string
  buckets: { label: string; count: number }[]
  total: number
}

export interface Coverage {
  cases: number
  with_refs: number
  executed: number
  by_suite: { label: string; count: number }[]
}

export interface DefectReport {
  total: number
  items: {
    ref: string
    count: number
    tests: { title: string; run_id: number; run_name: string; status_id: number | null }[]
  }[]
}

export interface SeriesPoint {
  label: string
  values: Record<string, number>
}

export interface Role {
  id: number
  name: string
  is_default: boolean
  is_project_default: boolean
  capabilities: string[]
  customised: boolean
}

export interface RolesResponse {
  capabilities: string[]
  roles: Role[]
}

export interface UserAdmin {
  id: number
  name: string
  email: string
  is_active: boolean
  role_id: number | null
  has_password: boolean
  last_login_at: string | null
}

export interface AdminSummary {
  users: number
  active_users: number
  roles: number
  projects: number
  case_fields: number
  result_fields: number
  case_types: number
  priorities: number
  statuses: number
}
