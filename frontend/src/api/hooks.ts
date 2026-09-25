import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type {
  ActivityByUserOut, ActivityItem, AdminSummary, Attachment, AuditPage, AutomationBacklog, CaseExplorerPage, CasePage, Catalog, Coverage, CustomField, DashboardOut, DefectReport, DigestPreview, Distribution, DuplicateGroup, FlakyCase, GroupAdmin, HistoryEntry, JiraIssue, Milestone, MilestoneProgress, NeverRunCase, NotificationPreference, PassTrendWeek, Project, ProjectGroupAccess, ProjectMember, ProjectStats, Result, RolesResponse, Run, RunSummary, SectionNode, SeriesPoint, SubscriptionList, Suite, SyncChanges, SyncStatusOut, Test, TestCase, TestDetail, TestPage, TodayOut, TodoItem, User, UserAccess, UserAdmin,
} from './types'

/** Lookup tables change about twice a year; keep them for the session. */
const STATIC = { staleTime: 60 * 60 * 1000 }

export const useMe = () =>
  useQuery({ queryKey: ['me'], queryFn: () => api.get<User>('/api/auth/me') })

export const useCatalog = () =>
  useQuery({ queryKey: ['catalog'], queryFn: () => api.get<Catalog>('/api/catalog'), ...STATIC })

export const useUsers = () =>
  useQuery({ queryKey: ['users'], queryFn: () => api.get<User[]>('/api/users'), ...STATIC })

export const useProjects = () =>
  useQuery({ queryKey: ['projects'], queryFn: () => api.get<Project[]>('/api/projects'), ...STATIC })

export const useSuite = (suiteId?: number, projectId?: number) => {
  const { data } = useSuites(projectId)
  return data?.find((s) => s.id === suiteId)
}

export const useSuites = (projectId?: number) =>
  useQuery({
    queryKey: ['suites', projectId],
    queryFn: () => api.get<Suite[]>(`/api/projects/${projectId}/suites`),
    enabled: !!projectId,
  })

export const useSections = (suiteId?: number) =>
  useQuery({
    queryKey: ['sections', suiteId],
    queryFn: () => api.get<SectionNode[]>(`/api/suites/${suiteId}/sections`),
    enabled: !!suiteId,
  })

export const useMilestones = (projectId?: number) =>
  useQuery({
    queryKey: ['milestones', projectId],
    queryFn: () => api.get<Milestone[]>(`/api/projects/${projectId}/milestones`),
    enabled: !!projectId,
  })

export function useCases(params: {
  suiteId?: number
  sectionId?: number | null
  q?: string
  typeId?: number
  priorityId?: number
  createdBy?: number
  field?: string
  value?: string
  sort?: string
  offset?: number
  limit?: number
}) {
  const {
    suiteId, sectionId, q, typeId, priorityId, createdBy, field, value,
    sort = 'section', offset = 0, limit = 100,
  } = params
  const search = new URLSearchParams({
    offset: String(offset), limit: String(limit), sort,
  })
  if (sectionId) search.set('section_id', String(sectionId))
  if (q) search.set('q', q)
  if (typeId) search.set('type_id', String(typeId))
  if (priorityId) search.set('priority_id', String(priorityId))
  if (createdBy) search.set('created_by', String(createdBy))
  if (field && value) { search.set('field', field); search.set('value', value) }
  return useQuery({
    queryKey: ['cases', suiteId, sectionId, q, typeId, priorityId, createdBy,
               field, value, sort, offset, limit],
    queryFn: () => api.get<CasePage>(`/api/suites/${suiteId}/cases?${search}`),
    enabled: !!suiteId,
    placeholderData: (prev) => prev,
  })
}

export interface SavedFilterRow {
  id: number
  name: string
  suite_id: number | null
  criteria: Record<string, unknown>
  is_shared: boolean
  mine: boolean
}

export const useSavedFilters = (projectId?: number) =>
  useQuery({
    queryKey: ['filters', projectId],
    queryFn: () => api.get<SavedFilterRow[]>(`/api/filters?project_id=${projectId}`),
    enabled: !!projectId,
  })

export function useSaveFilter(projectId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post('/api/filters', body),
    onSuccess: () => client.invalidateQueries({ queryKey: ['filters', projectId] }),
  })
}

export function useDeleteFilter(projectId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.del(`/api/filters/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ['filters', projectId] }),
  })
}

export function useCopyMoveCases() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ mode, body }: { mode: 'copy' | 'move'; body: Record<string, unknown> }) =>
      api.post<{ copied?: number; moved?: number }>(`/api/cases/bulk-${mode}`, body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['cases'] })
      client.invalidateQueries({ queryKey: ['sections'] })
    },
  })
}

export function useBulkUpdateCases() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<{ updated: number }>('/api/cases/bulk-update', body),
    onSuccess: () => client.invalidateQueries({ queryKey: ['cases'] }),
  })
}

export function useBulkStatus(runId?: number | null) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<{ updated: number }>(`/api/runs/${runId}/bulk-status`, body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['tests', runId] })
      client.invalidateQueries({ queryKey: ['run-summary', runId] })
    },
  })
}

/** Hand a selection of tests to someone (null takes it away). */
export function useBulkAssign(runId?: number | null) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { test_ids: number[]; assignedto_id: number | null }) =>
      api.post<{ updated: number }>(`/api/runs/${runId}/bulk-assign`, body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['tests', runId] })
      client.invalidateQueries({ queryKey: ['todo'] })
      client.invalidateQueries({ queryKey: ['today'] })
    },
  })
}

export const useCase = (caseId?: number | null) =>
  useQuery({
    queryKey: ['case', caseId],
    queryFn: () => api.get<TestCase>(`/api/cases/${caseId}`),
    enabled: !!caseId,
  })

export const useCaseHistory = (caseId?: number | null) =>
  useQuery({
    queryKey: ['case-history', caseId],
    queryFn: () => api.get<HistoryEntry[]>(`/api/cases/${caseId}/history`),
    enabled: !!caseId,
  })

export function useUpdateCase() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Record<string, unknown> }) =>
      api.patch<TestCase>(`/api/cases/${id}`, patch),
    onSuccess: (updated) => {
      client.setQueryData(['case', updated.id], updated)
      client.invalidateQueries({ queryKey: ['cases'] })
      client.invalidateQueries({ queryKey: ['case-history', updated.id] })
    },
  })
}

export const useAuditLog = (params: {
  action?: string; entityType?: string; userId?: number; days: number
  offset: number
}) =>
  useQuery({
    queryKey: ['audit', params],
    queryFn: () => {
      const query = new URLSearchParams({
        days: String(params.days), offset: String(params.offset), limit: '100',
      })
      if (params.action) query.set('action', params.action)
      if (params.entityType) query.set('entity_type', params.entityType)
      if (params.userId) query.set('user_id', String(params.userId))
      return api.get<AuditPage>(`/api/admin/audit?${query}`)
    },
    placeholderData: (prev) => prev,
  })

/* ---- case library health ------------------------------------------------- */

/** Passing 0 days parks the query; the tab that is not open costs nothing. */
export const useFlakyTests = (projectId?: number, days = 90) =>
  useQuery({
    queryKey: ['flaky', projectId, days],
    queryFn: () => api.get<{ days: number; items: FlakyCase[] }>(
      `/api/projects/${projectId}/reports/flaky?days=${days}&limit=100`),
    enabled: !!projectId && days > 0,
    // an aggregate over a year of results; not worth refetching on focus
    staleTime: 5 * 60 * 1000,
    placeholderData: (prev) => prev,
  })

export const useDuplicateCases = (projectId?: number) =>
  useQuery({
    queryKey: ['duplicates', projectId],
    queryFn: () => api.get<{ items: DuplicateGroup[] }>(
      `/api/projects/${projectId}/reports/duplicates?limit=100`),
    enabled: !!projectId,
    staleTime: 5 * 60 * 1000,
  })

export const useNeverRunCases = (projectId?: number) =>
  useQuery({
    queryKey: ['never-run', projectId],
    queryFn: () => api.get<{
      total: number; offset: number; limit: number; items: NeverRunCase[]
    }>(`/api/projects/${projectId}/reports/never-run?limit=100`),
    enabled: !!projectId,
    staleTime: 5 * 60 * 1000,
  })

export const useAutomationBacklog = (projectId?: number) =>
  useQuery({
    queryKey: ['automation-backlog', projectId],
    queryFn: () => api.get<AutomationBacklog>(
      `/api/projects/${projectId}/reports/automation-backlog?limit=100`),
    enabled: !!projectId,
    staleTime: 5 * 60 * 1000,
  })

/** Who produced what, by account. Aggregates 1.09M results; keep it. */
export const useActivityByUser = (days: number, projectId?: number) =>
  useQuery({
    queryKey: ['activity-by-user', days, projectId],
    queryFn: () => {
      const query = new URLSearchParams({ days: String(days) })
      if (projectId) query.set('project_id', String(projectId))
      return api.get<ActivityByUserOut>(`/api/activity-by-user?${query}`)
    },
    staleTime: 5 * 60 * 1000,
    placeholderData: (prev) => prev,
  })

/** The landing page's whole payload in one call. */
export const useToday = () =>
  useQuery({
    queryKey: ['today'],
    queryFn: () => api.get<TodayOut>('/api/today'),
    // it is the first thing drawn after a login; keep it fresh but cheap
    staleTime: 60 * 1000,
  })

/** TestRail sync health; refreshed while the admin page is open, and
 *  every few seconds while a pass is queued or running so the button's
 *  outcome shows up without a reload. */
export const useSyncStatus = () =>
  useQuery({
    queryKey: ['sync-status'],
    queryFn: () => api.get<SyncStatusOut>('/api/admin/sync'),
    refetchInterval: (query) =>
      query.state.data?.runs.some((r) => r.status === 'queued' || r.status === 'running')
        ? 5_000 : 60_000,
  })

/** What one sync pass brought in; fetched when its row is opened. */
export const useSyncChanges = (syncId: number | null) =>
  useQuery({
    queryKey: ['sync-changes', syncId],
    queryFn: () => api.get<SyncChanges>(`/api/admin/sync/${syncId}/changes`),
    enabled: syncId != null,
    staleTime: 5 * 60 * 1000,
  })

/** Ask the sync service for a pass now; it picks the request up within
 *  TESTRAIL_SYNC_POLL seconds. */
export const useRequestSync = () => {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ id: number; status: string }>('/api/admin/sync', {}),
    onSettled: () => client.invalidateQueries({ queryKey: ['sync-status'] }),
  })
}

/** Withdraw a request that has not started yet. */
export const useCancelSync = () => {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.del(`/api/admin/sync/${id}`),
    onSettled: () => client.invalidateQueries({ queryKey: ['sync-status'] }),
  })
}

/* ---- personal settings --------------------------------------------------- */

export const useNotificationPreferences = () =>
  useQuery({
    queryKey: ['notification-preferences'],
    queryFn: () => api.get<NotificationPreference[]>(
      '/api/notifications/preferences'),
  })

export function useSavePreference() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: NotificationPreference | {
      kind: string; in_app: boolean; email: boolean
    }) => api.put('/api/notifications/preferences', body),
    onSuccess: () => client.invalidateQueries({
      queryKey: ['notification-preferences'] }),
  })
}

export const useSubscriptions = () =>
  useQuery({
    queryKey: ['report-subscriptions'],
    queryFn: () => api.get<SubscriptionList>('/api/report-subscriptions'),
  })

export function useSaveSubscription() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post('/api/report-subscriptions', body),
    onSuccess: () => client.invalidateQueries({
      queryKey: ['report-subscriptions'] }),
  })
}

export function useDeleteSubscription() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.del(`/api/report-subscriptions/${id}`),
    onSuccess: () => client.invalidateQueries({
      queryKey: ['report-subscriptions'] }),
  })
}

/** What a digest would say right now; sends nothing and records nothing. */
export function usePreviewSubscription() {
  return useMutation({
    mutationFn: (id: number) =>
      api.post<DigestPreview>(`/api/report-subscriptions/${id}/preview`, {}),
  })
}

/* ---- attachments ------------------------------------------------------- */

export const useAttachments = (entityType: string, entityId?: number | null) =>
  useQuery({
    queryKey: ['attachments', entityType, entityId],
    queryFn: () => api.get<Attachment[]>(
      `/api/attachments?entity_type=${entityType}&entity_id=${entityId}`),
    enabled: !!entityId,
  })

export function useUploadAttachment(entityType: string, entityId?: number | null,
                                    projectId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => api.upload<Attachment>('/api/attachments', file, {
      entity_type: entityType, entity_id: entityId ?? undefined, project_id: projectId,
    }),
    onSuccess: () => client.invalidateQueries({
      queryKey: ['attachments', entityType, entityId] }),
  })
}

export function useDeleteAttachment(entityType: string, entityId?: number | null) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.del(`/api/attachments/${id}`),
    onSuccess: () => client.invalidateQueries({
      queryKey: ['attachments', entityType, entityId] }),
  })
}

/** Every project at once; the per-project overview is a different call. */
export const useDashboard = (days: number) =>
  useQuery({
    queryKey: ['dashboard', days],
    queryFn: () => api.get<DashboardOut>(`/api/dashboard?days=${days}`),
    // a whole-instance roll-up over 1M tests: worth keeping for a few minutes
    staleTime: 5 * 60 * 1000,
    placeholderData: (prev) => prev,
  })

export const useProjectStats = (projectId?: number) =>
  useQuery({
    queryKey: ['stats', projectId],
    queryFn: () => api.get<ProjectStats>(`/api/projects/${projectId}/stats`),
    enabled: !!projectId,
  })

export const useActivity = (projectId?: number) =>
  useQuery({
    queryKey: ['activity', projectId],
    queryFn: () => api.get<ActivityItem[]>(`/api/projects/${projectId}/activity?limit=20`),
    enabled: !!projectId,
  })

export const useRuns = (projectId?: number, archived = false, q = '') =>
  useQuery({
    queryKey: ['runs', projectId, archived, q],
    queryFn: () => {
      const params = new URLSearchParams({ limit: '300' })
      if (archived) params.set('archived', 'true')
      if (q) params.set('q', q)
      return api.get<Run[]>(`/api/projects/${projectId}/runs?${params}`)
    },
    enabled: !!projectId,
    placeholderData: (prev) => prev,
  })

/** Rows per page on the runs screen. */
export const RUN_PAGE = 200

/**
 * The runs screen, a page at a time. It used to fetch one fixed batch of
 * 300 and say nothing about the rest, so a project with 374 live runs
 * showed 300 of them and hid the oldest 74.
 */
export const useRunPages = (projectId?: number, archived = false, q = '') =>
  useInfiniteQuery({
    // projectId second, so the existing ['runs', projectId] invalidations reach it
    queryKey: ['runs', projectId, 'pages', archived, q],
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({
        limit: String(RUN_PAGE), offset: String(pageParam) })
      if (archived) params.set('archived', 'true')
      if (q) params.set('q', q)
      return api.get<Run[]>(`/api/projects/${projectId}/runs?${params}`)
    },
    initialPageParam: 0,
    getNextPageParam: (last, pages) =>
      last.length < RUN_PAGE ? undefined : pages.length * RUN_PAGE,
    enabled: !!projectId,
    placeholderData: (prev) => prev,
  })

export const useRunSummary = (runId?: number | null) =>
  useQuery({
    queryKey: ['run-summary', runId],
    queryFn: () => api.get<RunSummary>(`/api/runs/${runId}/summary`),
    enabled: !!runId,
  })

export const useTests = (runId?: number | null, params: {
  statusId?: number | null
  assignee?: number | null
  q?: string
  offset?: number
  limit?: number
} = {}) =>
  useQuery({
    queryKey: ['tests', runId, params],
    queryFn: () => {
      const query = new URLSearchParams({
        offset: String(params.offset ?? 0),
        limit: String(params.limit ?? 200),
      })
      if (params.statusId != null) query.set('status_id', String(params.statusId))
      if (params.assignee != null) query.set('assignedto_id', String(params.assignee))
      if (params.q) query.set('q', params.q)
      return api.get<TestPage>(`/api/runs/${runId}/tests?${query}`)
    },
    enabled: !!runId,
    placeholderData: (prev) => prev,
  })

export const useResults = (testId?: number | null) =>
  useQuery({
    queryKey: ['results', testId],
    queryFn: () => api.get<Result[]>(`/api/tests/${testId}/results`),
    enabled: !!testId,
  })

export const useTest = (testId?: number | null) =>
  useQuery({
    queryKey: ['test', testId],
    queryFn: () => api.get<TestDetail>(`/api/tests/${testId}`),
    enabled: !!testId,
  })

/** Reassigning a single test, for when somebody picks up a colleague's work. */
export function useUpdateTest(runId?: number | null) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ testId, patch }: { testId: number; patch: Record<string, unknown> }) =>
      api.patch<Test>(`/api/tests/${testId}`, patch),
    onSuccess: (test) => {
      client.invalidateQueries({ queryKey: ['test', test.id] })
      client.invalidateQueries({ queryKey: ['tests', runId] })
      client.invalidateQueries({ queryKey: ['todo'] })
    },
  })
}

export function useAddResult(runId?: number | null) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ testId, body }: { testId: number; body: Record<string, unknown> }) =>
      api.post<Result>(`/api/tests/${testId}/results`, body),

    /**
     * The row changes colour before the request leaves.
     *
     * Somebody working a 200-test run gives a verdict every few seconds. A
     * grid that waits for the round trip each time turns that rhythm into
     * stop-start, and the wait is the thing people describe as "slow" long
     * after the server has stopped being the reason.
     */
    onMutate: async ({ testId, body }) => {
      const status = body.status_id
      if (typeof status !== 'number') return {}
      await client.cancelQueries({ queryKey: ['tests', runId] })
      const previous = client.getQueriesData<TestPage>({
        queryKey: ['tests', runId] })
      for (const [key, page] of previous) {
        if (!page) continue
        client.setQueryData<TestPage>(key, {
          ...page,
          items: page.items.map((t) =>
            t.id === testId ? { ...t, status_id: status } : t),
        })
      }
      return { previous }
    },

    // the server refused it; put the grid back rather than leaving a lie
    onError: (_err, _vars, context) => {
      for (const [key, page] of context?.previous ?? []) {
        client.setQueryData(key, page)
      }
    },

    onSettled: (result) => {
      if (result) {
        client.invalidateQueries({ queryKey: ['results', result.test_id] })
        client.invalidateQueries({ queryKey: ['test', result.test_id] })
      }
      client.invalidateQueries({ queryKey: ['tests', runId] })
      client.invalidateQueries({ queryKey: ['run-summary', runId] })
    },
  })
}


/* ---- deleting and reshaping --------------------------------------------- */

export function useDeleteRun(projectId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (runId: number) => api.del(`/api/runs/${runId}`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['runs', projectId] })
      client.invalidateQueries({ queryKey: ['stats', projectId] })
    },
  })
}

export function useDeletePlan(projectId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (planId: number) => api.del(`/api/plans/${planId}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ['plans', projectId] }),
  })
}

export function useDeleteMilestone(projectId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.del(`/api/milestones/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ['milestones', projectId] }),
  })
}

export function useSaveSection(suiteId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Record<string, unknown> }) =>
      api.patch(`/api/sections/${id}`, patch),
    onSuccess: () => client.invalidateQueries({ queryKey: ['sections', suiteId] }),
  })
}

export function useDeleteSection(suiteId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.del(`/api/sections/${id}`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['sections', suiteId] })
      client.invalidateQueries({ queryKey: ['cases'] })
    },
  })
}

export function useSaveSuite(projectId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Record<string, unknown> }) =>
      api.patch(`/api/suites/${id}`, patch),
    onSuccess: () => client.invalidateQueries({ queryKey: ['suites', projectId] }),
  })
}

export function useDeleteSuite(projectId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.del(`/api/suites/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ['suites', projectId] }),
  })
}

export function useDeleteResult(testId?: number | null, runId?: number | null) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.del(`/api/results/${id}`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['results', testId] })
      client.invalidateQueries({ queryKey: ['test', testId] })
      client.invalidateQueries({ queryKey: ['tests', runId] })
      client.invalidateQueries({ queryKey: ['run-summary', runId] })
    },
  })
}

/** Cases added to or dropped from a run that already exists. */
export function useRunMembership(runId?: number | null) {
  const client = useQueryClient()
  const done = () => {
    client.invalidateQueries({ queryKey: ['tests', runId] })
    client.invalidateQueries({ queryKey: ['run-summary', runId] })
  }
  return {
    add: useMutation({
      mutationFn: (caseIds: number[]) =>
        api.post<{ added: number; skipped: number }>(
          `/api/runs/${runId}/tests`, { case_ids: caseIds }),
      onSuccess: done,
    }),
    remove: useMutation({
      mutationFn: (testIds: number[]) =>
        api.del<{ removed: number }>(`/api/runs/${runId}/tests`,
                                     { case_ids: testIds }),
      onSuccess: done,
    }),
  }
}

/* ---- spreadsheet import -------------------------------------------------- */

export interface ImportReport {
  headers: string[]
  mapping: Record<string, string>
  total_rows: number
  would_create: number
  new_sections: string[]
  skipped: string[]
  sample: { title: string; section: string; steps: number }[]
  created: number
}

export const useImportTargets = () =>
  useQuery({
    queryKey: ['import-targets'],
    queryFn: () => api.get<{
      builtin: { key: string; label: string }[]
      custom: { key: string; label: string; field_type: string }[]
    }>('/api/import/targets'),
    ...STATIC,
  })

export function useImportCases(suiteId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ file, mapping, sectionId, dryRun }: {
      file: File
      mapping?: Record<string, string>
      sectionId?: number
      dryRun: boolean
    }) => api.upload<ImportReport>(`/api/suites/${suiteId}/import`, file, {
      dry_run: dryRun ? 'true' : 'false',
      ...(mapping ? { mapping_json: JSON.stringify(mapping) } : {}),
      ...(sectionId ? { section_id: sectionId } : {}),
    }),
    onSuccess: (report) => {
      if (report.created) {
        client.invalidateQueries({ queryKey: ['sections', suiteId] })
        client.invalidateQueries({ queryKey: ['cases'] })
        client.invalidateQueries({ queryKey: ['suites'] })
      }
    },
  })
}


/* ---- projects and membership ------------------------------------------- */

export function useSaveProject() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: Record<string, unknown> }) =>
      id ? api.patch<Project>(`/api/projects/${id}`, body)
         : api.post<Project>('/api/projects', body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['projects'] })
      client.invalidateQueries({ queryKey: ['admin-summary'] })
    },
  })
}

export const useMembers = (projectId?: number) =>
  useQuery({
    queryKey: ['members', projectId],
    queryFn: () => api.get<ProjectMember[]>(`/api/projects/${projectId}/members`),
    enabled: !!projectId,
  })

/** Anything that changes who may see what: the lists built on access, and
 *  the per-user explanation on the admin page, all have to be refetched. */
function invalidateAccess(client: ReturnType<typeof useQueryClient>, projectId?: number) {
  client.invalidateQueries({ queryKey: ['members', projectId] })
  client.invalidateQueries({ queryKey: ['project-groups', projectId] })
  client.invalidateQueries({ queryKey: ['user-access'] })
  client.invalidateQueries({ queryKey: ['admin-groups'] })
  client.invalidateQueries({ queryKey: ['projects'] })
}

export function useSaveMember(projectId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { user_id: number; role_id: number }) =>
      api.put(`/api/projects/${projectId}/members`, body),
    onSuccess: () => invalidateAccess(client, projectId),
  })
}

export function useRemoveMember(projectId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (userId: number) =>
      api.del(`/api/projects/${projectId}/members/${userId}`),
    onSuccess: () => invalidateAccess(client, projectId),
  })
}

export const useProjectGroups = (projectId?: number) =>
  useQuery({
    queryKey: ['project-groups', projectId],
    queryFn: () => api.get<ProjectGroupAccess[]>(`/api/projects/${projectId}/groups`),
    enabled: !!projectId,
  })

export function useSaveProjectGroup(projectId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { group_id: number; role_id: number }) =>
      api.put(`/api/projects/${projectId}/groups`, body),
    onSuccess: () => invalidateAccess(client, projectId),
  })
}

export function useRemoveProjectGroup(projectId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (groupId: number) =>
      api.del(`/api/projects/${projectId}/groups/${groupId}`),
    onSuccess: () => invalidateAccess(client, projectId),
  })
}

/** Set a project's default access; null = everyone on their global role. */
export function useSetDefaultAccess(projectId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (roleId: number | null) =>
      api.patch<Project>(`/api/projects/${projectId}`, { default_role_id: roleId }),
    onSuccess: () => invalidateAccess(client, projectId),
  })
}

export const useUserAccess = (userId?: number | null) =>
  useQuery({
    queryKey: ['user-access', userId],
    queryFn: () => api.get<UserAccess>(`/api/admin/users/${userId}/access`),
    enabled: !!userId,
  })

/** A link with which the person sets their own password; e-mailed when
 *  SMTP is configured, returned either way for the administrator to copy. */
export function useInviteUser() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (userId: number) => api.post<{
      link: string; emailed: boolean; detail: string | null; expires_in_days: number
    }>(`/api/admin/users/${userId}/invite`, {}),
    onSuccess: () => client.invalidateQueries({ queryKey: ['audit'] }),
  })
}

export const useAdminGroups = () =>
  useQuery({
    queryKey: ['admin-groups'],
    queryFn: () => api.get<GroupAdmin[]>('/api/admin/groups'),
    retry: false,
  })

export function useSaveGroup() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: { name?: string; user_ids?: number[] } }) =>
      id ? api.patch<GroupAdmin>(`/api/admin/groups/${id}`, body)
         : api.post<GroupAdmin>('/api/admin/groups', body),
    onSuccess: () => invalidateAccess(client),
  })
}

export function useDeleteGroup() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.del(`/api/admin/groups/${id}`),
    onSuccess: () => invalidateAccess(client),
  })
}


// --- writes -----------------------------------------------------------------

export function useCreateMilestone(projectId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<Milestone>(`/api/projects/${projectId}/milestones`, body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['milestones', projectId] })
      client.invalidateQueries({ queryKey: ['stats', projectId] })
    },
  })
}

export function useUpdateMilestone(projectId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Record<string, unknown> }) =>
      api.patch<Milestone>(`/api/milestones/${id}`, patch),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['milestones', projectId] })
      client.invalidateQueries({ queryKey: ['stats', projectId] })
    },
  })
}

export function useCreateRun(projectId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<Run>(`/api/projects/${projectId}/runs`, body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['runs', projectId] })
      client.invalidateQueries({ queryKey: ['stats', projectId] })
    },
  })
}

export function useCreateCase(suiteId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<TestCase>('/api/cases', body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['cases'] })
      client.invalidateQueries({ queryKey: ['sections', suiteId] })
    },
  })
}

export function useCreateSection(suiteId?: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post('/api/sections', body),
    onSuccess: () => client.invalidateQueries({ queryKey: ['sections', suiteId] }),
  })
}

// --- to-do & reports --------------------------------------------------------

export const useTodo = () =>
  useQuery({ queryKey: ['todo'], queryFn: () => api.get<TodoItem[]>('/api/todo') })

/** The case library across a whole project, filtered: where reports land. */
export const useCaseExplorer = (projectId: number | undefined,
                                filters: Record<string, string>) =>
  useQuery({
    queryKey: ['explore', projectId, filters],
    queryFn: () => api.get<CaseExplorerPage>(
      `/api/projects/${projectId}/cases?`
      + new URLSearchParams(filters).toString()),
    enabled: !!projectId,
    // the counts move with every result posted; a stale page here is worse
    // than a slow one, because people act on "never run"
    staleTime: 30 * 1000,
  })

export const useDistribution = (projectId?: number, by: 'type' | 'priority' = 'type') =>
  useQuery({
    queryKey: ['dist', projectId, by],
    queryFn: () => api.get<Distribution>(
      `/api/projects/${projectId}/reports/property-distribution?by=${by}`),
    enabled: !!projectId,
  })

export const useCoverage = (projectId?: number) =>
  useQuery({
    queryKey: ['coverage', projectId],
    queryFn: () => api.get<Coverage>(`/api/projects/${projectId}/reports/coverage`),
    enabled: !!projectId,
  })

export const useDefects = (projectId?: number) =>
  useQuery({
    queryKey: ['defects', projectId],
    queryFn: () => api.get<DefectReport>(`/api/projects/${projectId}/reports/defects`),
    enabled: !!projectId,
  })

export const useActivitySeries = (projectId?: number, days = 120) =>
  useQuery({
    queryKey: ['series', projectId, days],
    queryFn: () => api.get<SeriesPoint[]>(
      `/api/projects/${projectId}/reports/activity?days=${days}`),
    enabled: !!projectId,
  })

export const usePassTrend = (projectId?: number, weeks = 26) =>
  useQuery({
    queryKey: ['pass-trend', projectId, weeks],
    queryFn: () => api.get<PassTrendWeek[]>(
      `/api/projects/${projectId}/reports/pass-trend?weeks=${weeks}`),
    enabled: !!projectId,
    placeholderData: (prev) => prev,
  })

export const useMilestoneProgress = (projectId?: number) =>
  useQuery({
    queryKey: ['milestone-progress', projectId],
    queryFn: () => api.get<MilestoneProgress[]>(
      `/api/projects/${projectId}/reports/milestones`),
    enabled: !!projectId,
  })

export const useJiraConfig = () =>
  useQuery({
    queryKey: ['jira-config'],
    queryFn: () => api.get<{ enabled: boolean; base_url: string | null }>('/api/jira/config'),
    ...STATIC,
  })

/** Status and summary for these issue keys, one request for the lot. */
export const useJiraIssues = (keys: string[]) => {
  const { data: config } = useJiraConfig()
  const wanted = [...new Set(keys)].sort().slice(0, 200)
  return useQuery({
    queryKey: ['jira-issues', wanted.join(',')],
    queryFn: () => api.get<Record<string, JiraIssue>>(
      `/api/jira/issues?keys=${encodeURIComponent(wanted.join(','))}`),
    enabled: !!config?.enabled && wanted.length > 0,
    // the server caches for ten minutes too; nobody needs it fresher
    staleTime: 10 * 60 * 1000,
  })
}

// --- admin ------------------------------------------------------------------

export const useAdminSummary = () =>
  useQuery({
    queryKey: ['admin-summary'],
    queryFn: () => api.get<AdminSummary>('/api/admin/summary'),
    retry: false,
  })

export const useAdminUsers = () =>
  useQuery({
    queryKey: ['admin-users'],
    queryFn: () => api.get<UserAdmin[]>('/api/admin/users'),
    retry: false,
  })

export const useRoles = () =>
  useQuery({
    queryKey: ['roles'],
    queryFn: () => api.get<RolesResponse>('/api/admin/roles'),
    retry: false,
  })

export function useSaveRole() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, capabilities }: { id: number; capabilities: string[] }) =>
      api.patch(`/api/admin/roles/${id}`, { capabilities }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['roles'] }),
  })
}

export const useAdminFields = () =>
  useQuery({
    queryKey: ['admin-fields'],
    queryFn: () => api.get<CustomField[]>('/api/admin/fields'),
    retry: false,
  })

export function useSaveUser() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: Record<string, unknown> }) =>
      id ? api.patch<UserAdmin>(`/api/admin/users/${id}`, body)
         : api.post<UserAdmin>('/api/admin/users', body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['admin-users'] })
      client.invalidateQueries({ queryKey: ['admin-summary'] })
      client.invalidateQueries({ queryKey: ['users'] })
      // a new global role changes every project where nothing overrides it
      client.invalidateQueries({ queryKey: ['user-access'] })
    },
  })
}

export function useSaveField() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: Record<string, unknown> }) =>
      id ? api.patch<CustomField>(`/api/admin/fields/${id}`, body)
         : api.post<CustomField>('/api/admin/fields', body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['admin-fields'] })
      client.invalidateQueries({ queryKey: ['catalog'] })
    },
  })
}
