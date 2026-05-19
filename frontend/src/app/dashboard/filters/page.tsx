"use client";

import {
  useEffect,
  useReducer,
  useRef,
  useState,
  type RefObject,
} from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Field,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupText,
  InputGroupTextarea,
} from "@/components/ui/input-group";
import {
  useArchiveFilter,
  useCreateOnboardingGeneration,
  useFeedbackStatus,
  useFilters,
  useJob,
  useJobsOverview,
  useOnboardingGenerationJob,
  usePendingFeedbackItems,
  useScholarImportStatus,
  countProposalFilters,
  getAllFiltersFromCache,
  invalidateFeedbackCompletionQueries,
  useProcessFeedback,
  usePromoteDraftFilters,
  useRestoreFilter,
  useUpdateFilter,
} from "@/hooks/use-queries";
import {
  api,
  FeedbackItem,
  FeedbackStatus,
  FilterResponse,
} from "@/lib/api";
import {
  Archive,
  Check,
  ChevronDown,
  ChevronRight,
  GraduationCap,
  Loader2,
  Pencil,
  RotateCcw,
  Send,
  StickyNote,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";

const MAX_INPUT_CHARS = 2000;
const FEEDBACK_TIMESTAMP_FORMATTER = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

type ScholarImportStep =
  | "input"
  | "verifying"
  | "verified"
  | "importing"
  | "polling"
  | "done"
  | "error";
type ScholarProfile = {
  author_id: string;
  name: string;
  affiliations: string[];
  paper_count: number | null;
};
type ScholarImportState = {
  url: string;
  step: ScholarImportStep;
  profile: ScholarProfile | null;
  error: string | null;
};
type ScholarImportAction =
  | { type: "set-url"; url: string }
  | { type: "verify-start" }
  | { type: "verify-success"; profile: ScholarProfile }
  | { type: "import-start" }
  | { type: "polling" }
  | { type: "done" }
  | { type: "error"; error: string };
type FilterPageState = {
  inputText: string;
  generationJobId: string | null;
  feedbackJobId: string | null;
  feedbackFinalizing: boolean;
  feedbackCompletion: { proposalCount: number; highlight: boolean } | null;
  archivedOpen: boolean;
};
type FilterPageAction =
  | { type: "set-input-text"; value: string }
  | { type: "generation-started"; jobId: string }
  | { type: "feedback-started"; jobId: string }
  | { type: "feedback-finalizing" }
  | { type: "feedback-completed"; proposalCount: number }
  | { type: "feedback-failed" }
  | { type: "feedback-highlight-cleared" }
  | { type: "feedback-completion-dismiss" }
  | { type: "toggle-archived" };

const ACTIVE_SCHOLAR_IMPORT_STATUSES = new Set(["pending", "queued", "running"]);

function formatFeedbackTimestamp(value: string) {
  return FEEDBACK_TIMESTAMP_FORMATTER.format(new Date(value));
}

function feedbackItemTimestamp(item: FeedbackItem) {
  return formatFeedbackTimestamp(item.updated_at || item.created_at);
}

function FilterModeBadge({
  mode,
}: {
  mode?: FilterResponse["definition"]["mode"];
}) {
  const normalizedMode = mode === "claim" ? "claim" : "topic";
  return (
    <Badge variant={normalizedMode === "claim" ? "default" : "secondary"}>
      {normalizedMode === "claim" ? "Claim" : "Topic"}
    </Badge>
  );
}

function scholarImportReducer(
  state: ScholarImportState,
  action: ScholarImportAction
): ScholarImportState {
  switch (action.type) {
    case "set-url":
      return { ...state, url: action.url };
    case "verify-start":
      return { ...state, step: "verifying", error: null };
    case "verify-success":
      return { ...state, step: "verified", profile: action.profile };
    case "import-start":
      return { ...state, step: "importing", error: null };
    case "polling":
      return { ...state, step: "polling" };
    case "done":
      return { ...state, step: "done" };
    case "error":
      return { ...state, step: "error", error: action.error };
  }
}

function filterPageReducer(
  state: FilterPageState,
  action: FilterPageAction
): FilterPageState {
  switch (action.type) {
    case "set-input-text":
      return { ...state, inputText: action.value };
    case "generation-started":
      return { ...state, generationJobId: action.jobId, inputText: "" };
    case "feedback-started":
      return {
        ...state,
        feedbackJobId: action.jobId,
        feedbackFinalizing: false,
        feedbackCompletion: null,
      };
    case "feedback-finalizing":
      return { ...state, feedbackFinalizing: true };
    case "feedback-completed":
      return {
        ...state,
        feedbackJobId: null,
        feedbackFinalizing: false,
        feedbackCompletion: {
          proposalCount: action.proposalCount,
          highlight: action.proposalCount > 0,
        },
      };
    case "feedback-failed":
      return { ...state, feedbackFinalizing: false };
    case "feedback-highlight-cleared":
      return state.feedbackCompletion
        ? {
            ...state,
            feedbackCompletion: { ...state.feedbackCompletion, highlight: false },
          }
        : state;
    case "feedback-completion-dismiss":
      return { ...state, feedbackCompletion: null };
    case "toggle-archived":
      return { ...state, archivedOpen: !state.archivedOpen };
  }
}

function DraftFilterCard({ filter }: { filter: FilterResponse }) {
  const updateFilter = useUpdateFilter();
  const archiveFilter = useArchiveFilter();
  const [draft, setDraft] = useState<{
    name: string;
    description: string;
  } | null>(null);

  const save = async () => {
    if (!draft) return;
    const nextName = draft.name.trim();
    const nextDescription = draft.description.trim();
    if (!nextName || !nextDescription) return;
    await updateFilter.mutateAsync({
      id: filter.id,
      input: {
        definition: {
          ...filter.definition,
          name: nextName,
          description: nextDescription,
          mode: filter.definition.mode || "topic",
        },
      },
    });
    setDraft(null);
  };

  return (
    <Card>
      <CardContent>
        {draft ? (
          <div className="space-y-3">
            <Input
              aria-label="Filter name"
              value={draft.name}
              onChange={(event) =>
                setDraft((current) =>
                  current ? { ...current, name: event.target.value } : current
                )
              }
            />
            <Textarea
              aria-label="Filter description"
              value={draft.description}
              onChange={(event) =>
                setDraft((current) =>
                  current
                    ? { ...current, description: event.target.value }
                    : current
                )
              }
              rows={3}
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={save}
                disabled={updateFilter.isPending}
              >
                <Check className="mr-1 size-3" />
                Save
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setDraft(null)}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium">{filter.name}</p>
                <FilterModeBadge mode={filter.definition.mode} />
              </div>
              <p className="text-sm text-muted-foreground">
                {filter.definition.description}
              </p>
            </div>
            <div className="flex shrink-0 gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="size-7"
                aria-label={`Edit ${filter.name}`}
                onClick={() =>
                  setDraft({
                    name: filter.name,
                    description: filter.definition.description || "",
                  })
                }
              >
                <Pencil className="size-3" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="size-7"
                aria-label={`Remove ${filter.name}`}
                onClick={() => archiveFilter.mutate(filter.id)}
              >
                <Archive className="size-3" />
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ScholarImportSection({
  hasScholarFilters,
}: {
  hasScholarFilters: boolean;
}) {
  const queryClient = useQueryClient();
  const [importId, setImportId] = useState<string | null>(null);
  const [state, dispatch] = useReducer(scholarImportReducer, {
    url: "",
    step: "input",
    profile: null,
    error: null,
  });
  const { data: jobsOverview } = useJobsOverview();
  const activeRecoveredImportJob = jobsOverview?.active.find(
    (entry) => entry.job.kind === "scholar_import" && entry.job.subject_id
  );
  const shouldShowRecentFailure =
    !importId && state.step === "input" && !state.url.trim();
  const recentFailedImportJob = shouldShowRecentFailure
    ? jobsOverview?.recent.find(
        (entry) =>
          entry.job.kind === "scholar_import" &&
          entry.job.status === "failed" &&
          entry.job.subject_id
      )
    : undefined;
  const recoveredImportJob = activeRecoveredImportJob ?? recentFailedImportJob;
  const recoveredImportId = recoveredImportJob?.job.subject_id ?? null;
  const effectiveImportId = importId ?? recoveredImportId;
  const recoveredStatus = importId ? null : recoveredImportJob?.job.status ?? null;
  const isRecoveredActive =
    !!recoveredStatus && ACTIVE_SCHOLAR_IMPORT_STATUSES.has(recoveredStatus);
  const visibleStep =
    isRecoveredActive && state.step === "input" ? "polling" : state.step;
  const isImportInFlight =
    visibleStep === "importing" || visibleStep === "polling";
  const { data: importStatus } = useScholarImportStatus(
    effectiveImportId,
    isImportInFlight
  );

  useEffect(() => {
    if (!effectiveImportId) return;
    const status = importStatus?.status ?? recoveredStatus;
    if (status === "completed" && state.step !== "done") {
      dispatch({ type: "done" });
      queryClient.invalidateQueries({ queryKey: ["filters"] });
    } else if (status === "failed") {
      const error =
        importStatus?.error || recoveredImportJob?.job.error || "Import failed";
      if (state.step !== "error" || state.error !== error) {
        dispatch({ type: "error", error });
      }
    }
  }, [
    effectiveImportId,
    importStatus,
    queryClient,
    recoveredImportJob?.job.error,
    recoveredStatus,
    state.error,
    state.step,
  ]);

  if (hasScholarFilters || state.step === "done") return null;

  const handleVerify = async () => {
    if (!state.url.trim()) return;
    dispatch({ type: "verify-start" });
    try {
      const profile = await api.verifyScholarProfile(state.url);
      dispatch({ type: "verify-success", profile });
    } catch (err) {
      dispatch({
        type: "error",
        error: err instanceof Error ? err.message : "Verification failed",
      });
    }
  };

  const handleImport = async () => {
    if (!state.profile) return;
    dispatch({ type: "import-start" });
    try {
      const result = await api.startScholarImport({
        url: state.url,
        author_id: state.profile.author_id,
        display_name: state.profile.name,
      });
      setImportId(result.id);
      dispatch({ type: "polling" });
    } catch (err) {
      dispatch({
        type: "error",
        error: err instanceof Error ? err.message : "Import failed",
      });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <GraduationCap className="size-4" />
          Semantic Scholar Profile Import
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <Input
            placeholder="Paste Semantic Scholar profile URL..."
            value={state.url}
            onChange={(event) =>
              dispatch({ type: "set-url", url: event.target.value })
            }
            disabled={
              visibleStep === "verifying" ||
              visibleStep === "importing" ||
              visibleStep === "polling"
            }
          />
          {(visibleStep === "input" || visibleStep === "error") && (
            <Button
              size="sm"
              onClick={handleVerify}
              disabled={!state.url.trim()}
            >
              Verify
            </Button>
          )}
        </div>
        {state.error && <p className="text-sm text-destructive">{state.error}</p>}
        {visibleStep === "verifying" && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Verifying profile…
          </div>
        )}
        {visibleStep === "verified" && state.profile && (
          <div className="space-y-2">
            <div className="text-sm">
              <p className="font-medium">{state.profile.name}</p>
              {state.profile.affiliations.length > 0 && (
                <p className="text-muted-foreground">
                  {state.profile.affiliations.join(", ")}
                </p>
              )}
              {state.profile.paper_count != null && (
                <p className="text-muted-foreground">
                  {state.profile.paper_count} papers
                </p>
              )}
            </div>
            <Button size="sm" onClick={handleImport}>
              Import & Generate Filters
            </Button>
          </div>
        )}
        {(visibleStep === "importing" || visibleStep === "polling") && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            {visibleStep === "importing"
              ? "Starting import…"
              : importStatus?.display_name
                ? `Generating filters from publications for ${importStatus.display_name}…`
                : "Generating filters from publications…"}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ProposalCard({
  filter,
  targetFilter,
  onAccept,
  onReject,
}: {
  filter: FilterResponse;
  targetFilter?: FilterResponse;
  onAccept: () => void;
  onReject: () => void;
}) {
  const actionLabel =
    filter.proposed_action === "create"
      ? "New filter"
      : filter.proposed_action === "revise"
        ? "Revise existing filter"
        : "Delete filter";
  const badgeVariant =
    filter.proposed_action === "create"
      ? "default"
      : filter.proposed_action === "delete"
        ? "destructive"
        : "secondary";

  return (
    <Card>
      <CardContent className="space-y-2">
        <div className="flex items-center gap-2">
          <Badge variant={badgeVariant}>{actionLabel}</Badge>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-medium">{filter.name}</p>
          <FilterModeBadge mode={filter.definition.mode} />
        </div>
        {filter.proposed_action !== "delete" && (
          <p className="text-sm text-muted-foreground">
            {filter.definition.description}
          </p>
        )}
        {targetFilter && filter.proposed_action === "revise" && (
          <div className="rounded border p-2 text-xs text-muted-foreground space-y-1">
            <p className="font-medium">Current: {targetFilter.name}</p>
            <p>{targetFilter.definition.description}</p>
          </div>
        )}
        {targetFilter && filter.proposed_action === "delete" && (
          <p className="text-sm text-muted-foreground">
            Will archive: {targetFilter.name}
          </p>
        )}
        <div className="flex gap-2">
          <Button size="sm" onClick={onAccept}>
            <Check className="mr-1 size-3" />
            Accept
          </Button>
          <Button size="sm" variant="ghost" onClick={onReject}>
            Dismiss
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ResearchContextForm({
  inputText,
  status,
  onInputTextChange,
  onSend,
}: {
  inputText: string;
  status: {
    isGenerating: boolean;
    isCreating: boolean;
    canSend: boolean;
  };
  onInputTextChange: (value: string) => void;
  onSend: () => void;
}) {
  return (
    <FieldGroup>
      <Field>
        <FieldLabel htmlFor="filter-context">Research context</FieldLabel>
        <InputGroup>
          <InputGroupTextarea
            id="filter-context"
            value={inputText}
            maxLength={MAX_INPUT_CHARS}
            rows={5}
            placeholder="Add a research direction, question, claim, or context from your current work..."
            onChange={(event) => onInputTextChange(event.target.value)}
            disabled={status.isGenerating}
          />
          <InputGroupAddon align="block-end" className="gap-2 items-end">
            <InputGroupText>
              {inputText.length}/{MAX_INPUT_CHARS}
            </InputGroupText>
            <InputGroupButton
              variant="default"
              size="sm"
              className="ml-auto"
              onClick={onSend}
              disabled={!status.canSend}
            >
              {status.isGenerating || status.isCreating ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Send className="size-4" />
              )}
              Send
            </InputGroupButton>
          </InputGroupAddon>
        </InputGroup>
      </Field>
    </FieldGroup>
  );
}

function DraftFiltersSection({
  filters,
  isGenerating,
  isPromoting,
  onAcceptDrafts,
}: {
  filters: FilterResponse[];
  isGenerating: boolean;
  isPromoting: boolean;
  onAcceptDrafts: () => void;
}) {
  if (filters.length === 0 && !isGenerating) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Draft Filters</h2>
          <p className="text-sm text-muted-foreground">
            Drafts are ignored by daily search until accepted.
          </p>
        </div>
        <Button
          onClick={onAcceptDrafts}
          disabled={filters.length === 0 || isPromoting}
        >
          {isPromoting ? (
            <Loader2 className="mr-2 size-4 animate-spin" />
          ) : (
            <Check className="mr-2 size-4" />
          )}
          Accept Drafts ({filters.length})
        </Button>
      </div>
      {filters.length > 0 ? (
        <div className="space-y-3">
          {filters.map((filter) => (
            <DraftFilterCard key={filter.id} filter={filter} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function FeedbackCompletionBanner({
  proposalCount,
  onDismiss,
}: {
  proposalCount: number;
  onDismiss: () => void;
}) {
  const message =
    proposalCount > 0
      ? `${proposalCount} filter proposal${proposalCount === 1 ? "" : "s"} ready — review below`
      : "Feedback processed. No filter changes were suggested.";

  return (
    <div
      className={`flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm ${
        proposalCount > 0
          ? "border-primary/30 bg-primary/5 text-foreground"
          : "border-border bg-muted/40 text-muted-foreground"
      }`}
      role="status"
      aria-live="polite"
    >
      <span>{message}</span>
      <Button variant="ghost" size="sm" onClick={onDismiss}>
        Dismiss
      </Button>
    </div>
  );
}

function feedbackProcessingLabel(
  status: "queued" | "running" | "failed" | null
): string {
  switch (status) {
    case "queued":
      return "Queued — analyzing feedback…";
    case "running":
      return "Analyzing feedback and drafting filter proposals…";
    case "failed":
      return "Feedback processing failed. Try again.";
    default:
      return "";
  }
}

function FeedbackCard({
  status,
  items,
  isLoadingItems,
  isProcessing,
  processingStatus,
  processingError,
  onProcess,
}: {
  status?: FeedbackStatus;
  items: FeedbackItem[];
  isLoadingItems: boolean;
  isProcessing: boolean;
  processingStatus: "queued" | "running" | "failed" | null;
  processingError?: string | null;
  onProcess: () => void;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  if (!status || (status.pending_votes === 0 && status.pending_notes === 0)) {
    return null;
  }

  const voteItems = items.filter((item) => item.kind === "vote");
  const noteItems = items.filter((item) => item.kind === "note");
  const pendingCount = status.pending_votes + status.pending_notes;

  return (
    <Card>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            className="flex min-w-0 items-center gap-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => setIsExpanded((value) => !value)}
            aria-expanded={isExpanded}
          >
            {isExpanded ? (
              <ChevronDown className="size-4 shrink-0" />
            ) : (
              <ChevronRight className="size-4 shrink-0" />
            )}
            <div className="min-w-0">
              <p className="text-sm font-medium">
                Pending Feedback ({pendingCount})
              </p>
              <p className="text-xs text-muted-foreground">
                {status.pending_votes} vote
                {status.pending_votes !== 1 ? "s" : ""}
                {status.pending_notes > 0 &&
                  `, ${status.pending_notes} note${
                    status.pending_notes !== 1 ? "s" : ""
                  }`}
              </p>
            </div>
          </button>
          <div className="flex shrink-0 items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsExpanded((value) => !value)}
            >
              {isExpanded ? "Hide" : "Show"} Feedback
            </Button>
            <Button size="sm" onClick={onProcess} disabled={isProcessing}>
              {isProcessing ? (
                <Loader2 className="mr-1 size-3 animate-spin" />
              ) : null}
              {isProcessing ? "Processing…" : "Process Feedback"}
            </Button>
          </div>
        </div>

        {processingStatus ? (
          <div
            className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm ${
              processingStatus === "failed"
                ? "border-destructive/50 bg-destructive/5 text-destructive"
                : "border-border bg-muted/40 text-muted-foreground"
            }`}
            role="status"
            aria-live="polite"
          >
            {processingStatus !== "failed" ? (
              <Loader2 className="size-4 shrink-0 animate-spin" />
            ) : null}
            <span>
              {processingError ?? feedbackProcessingLabel(processingStatus)}
            </span>
          </div>
        ) : null}

        {isExpanded ? (
          <div className="space-y-4">
            {isLoadingItems ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                Loading feedback…
              </div>
            ) : null}
            {voteItems.length > 0 ? (
              <FeedbackItemGroup title="Votes" items={voteItems} />
            ) : null}
            {noteItems.length > 0 ? (
              <FeedbackItemGroup title="Notes" items={noteItems} />
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function FeedbackItemGroup({
  title,
  items,
}: {
  title: string;
  items: FeedbackItem[];
}) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium uppercase text-muted-foreground">
        {title}
      </p>
      <div className="divide-y rounded-md border">
        {items.map((item) => (
          <FeedbackItemRow key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}

function FeedbackItemRow({ item }: { item: FeedbackItem }) {
  const isVote = item.kind === "vote";
  const VoteIcon = item.value === "down" ? ThumbsDown : ThumbsUp;
  const voteClass = item.value === "down" ? "text-red-600" : "text-green-600";
  const contextLabel = item.paper_match_id ? "Matched paper" : "Unmatched paper";

  return (
    <div className="flex gap-3 p-3">
      <div className="mt-0.5 shrink-0">
        {isVote ? (
          <VoteIcon className={`size-4 ${voteClass}`} />
        ) : (
          <StickyNote className="size-4 text-muted-foreground" />
        )}
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <Link
            href={`/dashboard/papers/${item.paper_id}`}
            className="truncate text-sm font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {item.paper_title}
          </Link>
          <span className="text-xs text-muted-foreground">
            {feedbackItemTimestamp(item)}
          </span>
        </div>
        {isVote ? (
          <p className="text-xs text-muted-foreground">
            {item.value === "down" ? "Thumbs down" : "Thumbs up"} ·{" "}
            {contextLabel}
            {item.filter_name ? ` · ${item.filter_name}` : ""}
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">
            {item.text}
          </p>
        )}
      </div>
    </div>
  );
}

function ProposalSection(
  {
    filters,
    allFilters,
    onAccept,
    onReject,
    highlighted = false,
    ref,
  }: {
    filters: FilterResponse[];
    allFilters: FilterResponse[];
    onAccept: (filterId: string) => void;
    onReject: (filterId: string) => void;
    highlighted?: boolean;
    ref?: RefObject<HTMLDivElement | null>;
  }
) {
  if (filters.length === 0) return null;

  return (
    <div
      ref={ref}
      className={`space-y-3 rounded-lg transition-shadow duration-500 ${
        highlighted ? "ring-2 ring-primary/40" : ""
      }`}
    >
      <h2 className="text-lg font-semibold">Proposals ({filters.length})</h2>
      {filters.map((filter) => (
        <ProposalCard
          key={filter.id}
          filter={filter}
          targetFilter={
            filter.target_filter_id
              ? allFilters.find((target) => target.id === filter.target_filter_id)
              : undefined
          }
          onAccept={() => onAccept(filter.id)}
          onReject={() => onReject(filter.id)}
        />
      ))}
    </div>
  );
}

function ActiveFiltersSection({
  filters,
  isArchiving,
  onArchive,
}: {
  filters: FilterResponse[];
  isArchiving: boolean;
  onArchive: (filterId: string) => void;
}) {
  if (filters.length === 0) return null;

  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold">Active ({filters.length})</h2>
      {filters.map((filter) => (
        <Card key={filter.id}>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <div className="min-w-0 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle className="text-sm">{filter.name}</CardTitle>
                  <FilterModeBadge mode={filter.definition?.mode} />
                </div>
                <p className="text-sm text-muted-foreground">
                  {filter.definition?.description}
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onArchive(filter.id)}
                disabled={isArchiving}
              >
                <Archive className="mr-1 size-3" />
                Archive
              </Button>
            </div>
          </CardHeader>
        </Card>
      ))}
    </div>
  );
}

function ArchivedFiltersSection({
  filters,
  isOpen,
  isRestoring,
  onToggle,
  onRestore,
}: {
  filters: FilterResponse[];
  isOpen: boolean;
  isRestoring: boolean;
  onToggle: () => void;
  onRestore: (filterId: string) => void;
}) {
  if (filters.length === 0) return null;

  return (
    <div className="space-y-3">
      <button
        type="button"
        className="flex items-center gap-2 text-lg font-semibold text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        onClick={onToggle}
        aria-expanded={isOpen}
      >
        {isOpen ? (
          <ChevronDown className="size-4" />
        ) : (
          <ChevronRight className="size-4" />
        )}
        Archived ({filters.length})
      </button>
      {isOpen &&
        filters.map((filter) => (
          <Card key={filter.id} className="opacity-60">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <CardTitle className="text-sm">{filter.name}</CardTitle>
                    <FilterModeBadge mode={filter.definition?.mode} />
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {filter.definition?.description}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onRestore(filter.id)}
                  disabled={isRestoring}
                >
                  <RotateCcw className="mr-1 size-3" />
                  Restore
                </Button>
              </div>
            </CardHeader>
          </Card>
        ))}
    </div>
  );
}

function useFeedbackProcessingState({
  feedbackJobId,
  feedbackFinalizing,
  dispatch,
}: {
  feedbackJobId: string | null;
  feedbackFinalizing: boolean;
  dispatch: (action: FilterPageAction) => void;
}) {
  const queryClient = useQueryClient();
  const feedbackCompletionHandledRef = useRef<string | null>(null);
  const processFeedback = useProcessFeedback();
  const { data: jobsOverview } = useJobsOverview();
  const { data: feedbackJob } = useJob(feedbackJobId);
  const { data: feedbackStatus } = useFeedbackStatus();
  const hasPendingFeedback = feedbackStatus
    ? feedbackStatus.pending_votes > 0 || feedbackStatus.pending_notes > 0
    : false;
  const { data: pendingFeedbackItems = [], isLoading: isLoadingFeedbackItems } =
    usePendingFeedbackItems(hasPendingFeedback);
  const isFeedbackProcessing =
    processFeedback.isPending ||
    feedbackFinalizing ||
    feedbackJob?.status === "queued" ||
    feedbackJob?.status === "running";
  const feedbackProcessingStatus: "queued" | "running" | "failed" | null =
    feedbackJob?.status === "failed"
      ? "failed"
      : feedbackFinalizing || feedbackJob?.status === "running"
        ? "running"
        : feedbackJob?.status === "queued" || processFeedback.isPending
          ? "queued"
          : null;

  useEffect(() => {
    if (feedbackJobId) return;
    const activeFeedbackJob = jobsOverview?.active.find(
      (entry) => entry.job.kind === "feedback_reflection"
    );
    if (activeFeedbackJob) {
      dispatch({
        type: "feedback-started",
        jobId: activeFeedbackJob.job.id,
      });
    }
  }, [dispatch, feedbackJobId, jobsOverview]);

  useEffect(() => {
    if (!feedbackJobId || !feedbackJob) return;
    if (feedbackJob.status === "queued" || feedbackJob.status === "running") {
      return;
    }
    if (feedbackCompletionHandledRef.current === feedbackJobId) {
      return;
    }

    if (feedbackJob.status === "failed") {
      feedbackCompletionHandledRef.current = feedbackJobId;
      void invalidateFeedbackCompletionQueries(queryClient);
      dispatch({ type: "feedback-failed" });
      return;
    }

    if (feedbackJob.status !== "completed") {
      return;
    }

    let cancelled = false;
    void (async () => {
      dispatch({ type: "feedback-finalizing" });
      if (cancelled) return;
      try {
        await invalidateFeedbackCompletionQueries(queryClient);
      } catch {
        if (!cancelled) {
          dispatch({ type: "feedback-failed" });
        }
        return;
      }
      if (cancelled) return;

      feedbackCompletionHandledRef.current = feedbackJobId;
      dispatch({
        type: "feedback-completed",
        proposalCount: countProposalFilters(getAllFiltersFromCache(queryClient)),
      });
    })();

    return () => {
      cancelled = true;
    };
  }, [dispatch, feedbackJob, feedbackJobId, queryClient]);

  const handleProcessFeedback = async () => {
    if (isFeedbackProcessing) return;
    feedbackCompletionHandledRef.current = null;
    dispatch({ type: "feedback-completion-dismiss" });
    try {
      const result = await processFeedback.mutateAsync();
      dispatch({ type: "feedback-started", jobId: result.job_id });
    } catch {
      // mutation error surfaced via react-query
    }
  };

  return {
    feedbackStatus,
    pendingFeedbackItems,
    isLoadingFeedbackItems,
    isFeedbackProcessing,
    feedbackProcessingStatus,
    feedbackProcessingError: feedbackJob?.error,
    handleProcessFeedback,
  };
}

function EmptyFiltersState({ isVisible }: { isVisible: boolean }) {
  if (!isVisible) return null;

  return (
    <Card>
      <CardContent className="text-center">
        <p className="text-muted-foreground">
          No filters yet. Add research context above to generate filters.
        </p>
      </CardContent>
    </Card>
  );
}

export default function FiltersPage() {
  const queryClient = useQueryClient();
  const proposalsSectionRef = useRef<HTMLDivElement | null>(null);
  const [state, dispatch] = useReducer(filterPageReducer, {
    inputText: "",
    generationJobId: null,
    feedbackJobId: null,
    feedbackFinalizing: false,
    feedbackCompletion: null,
    archivedOpen: false,
  });

  const createGeneration = useCreateOnboardingGeneration();
  const promoteDraftFilters = usePromoteDraftFilters();
  const archiveFilter = useArchiveFilter();
  const restoreFilter = useRestoreFilter();
  const {
    feedbackStatus,
    pendingFeedbackItems,
    isLoadingFeedbackItems,
    isFeedbackProcessing,
    feedbackProcessingStatus,
    feedbackProcessingError,
    handleProcessFeedback,
  } = useFeedbackProcessingState({
    feedbackJobId: state.feedbackJobId,
    feedbackFinalizing: state.feedbackFinalizing,
    dispatch,
  });
  const { data: generationState } = useOnboardingGenerationJob(
    state.generationJobId
  );
  const generationJob = generationState?.job;
  const { data: draftFilters = [] } = useFilters("draft");
  const { data: allFilters = [] } = useFilters();

  const activeFilters = allFilters.filter((filter) => filter.status === "active");
  const archivedFilters = allFilters.filter(
    (filter) => filter.status === "archived"
  );
  const proposalFilters = allFilters.filter(
    (filter) =>
      filter.proposed_action &&
      ["pending_create", "pending_revision", "pending_deletion"].includes(
        filter.status
      )
  );
  const hasScholarFilters = allFilters.some(
    (filter) => filter.source === "scholar"
  );
  const isGenerating =
    generationJob?.status === "queued" || generationJob?.status === "running";
  const canSend =
    !isGenerating &&
    !createGeneration.isPending &&
    state.inputText.length <= MAX_INPUT_CHARS &&
    state.inputText.trim().length > 0;

  useEffect(() => {
    if (!generationState?.items.length) return;
    queryClient.setQueryData<FilterResponse[]>(
      ["filters", "draft"],
      (current = []) => {
        const byId = new Map(current.map((filter) => [filter.id, filter]));
        generationState.items.forEach((filter) => byId.set(filter.id, filter));
        return Array.from(byId.values());
      }
    );
  }, [generationState, queryClient]);

  useEffect(() => {
    if (!state.feedbackCompletion || state.feedbackCompletion.proposalCount === 0) {
      return;
    }
    const frame = requestAnimationFrame(() => {
      proposalsSectionRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [state.feedbackCompletion]);

  useEffect(() => {
    if (!state.feedbackCompletion || state.feedbackCompletion.proposalCount === 0) {
      return;
    }
    const timeout = window.setTimeout(
      () => dispatch({ type: "feedback-highlight-cleared" }),
      2000
    );
    return () => window.clearTimeout(timeout);
  }, [state.feedbackCompletion]);

  const handleSend = async () => {
    if (!canSend) return;
    const result = await createGeneration.mutateAsync({
      input_text: state.inputText,
    });
    dispatch({ type: "generation-started", jobId: result.job_id });
  };

  const handleAcceptDrafts = async () => {
    if (draftFilters.length === 0) return;
    await promoteDraftFilters.mutateAsync(
      draftFilters.map((filter) => filter.id)
    );
  };

  const handleAcceptProposal = async (filterId: string) => {
    try {
      await api.acceptProposal(filterId);
      queryClient.invalidateQueries({ queryKey: ["filters"] });
    } catch {
      // ignore
    }
  };

  const handleRejectProposal = async (filterId: string) => {
    try {
      await api.rejectProposal(filterId);
      queryClient.invalidateQueries({ queryKey: ["filters"] });
    } catch {
      // ignore
    }
  };

  return (
    <div className="flex-1 p-6 space-y-6 max-w-3xl">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Filters</h1>
        <p className="text-sm text-muted-foreground">
          Add research context to generate filters, or review and manage
          existing ones.
        </p>
      </div>

      <ResearchContextForm
        inputText={state.inputText}
        status={{
          isGenerating,
          isCreating: createGeneration.isPending,
          canSend,
        }}
        onInputTextChange={(value) =>
          dispatch({ type: "set-input-text", value })
        }
        onSend={handleSend}
      />

      {generationJob ? (
        <Card>
          <CardContent className="flex items-center gap-2 pt-6 text-sm text-muted-foreground">
            {isGenerating ? <Loader2 className="size-4 animate-spin" /> : null}
            <span>
              {generationJob.status === "running"
                ? "Generating draft filters…"
                : generationJob.status === "queued"
                  ? "Queued…"
                  : generationJob.status}
            </span>
          </CardContent>
        </Card>
      ) : null}

      <DraftFiltersSection
        filters={draftFilters}
        isGenerating={isGenerating}
        isPromoting={promoteDraftFilters.isPending}
        onAcceptDrafts={handleAcceptDrafts}
      />

      <ScholarImportSection hasScholarFilters={hasScholarFilters} />

      <FeedbackCard
        status={feedbackStatus}
        items={pendingFeedbackItems}
        isLoadingItems={isLoadingFeedbackItems}
        isProcessing={isFeedbackProcessing}
        processingStatus={feedbackProcessingStatus}
        processingError={feedbackProcessingError}
        onProcess={handleProcessFeedback}
      />

      {state.feedbackCompletion ? (
        <FeedbackCompletionBanner
          proposalCount={state.feedbackCompletion.proposalCount}
          onDismiss={() => dispatch({ type: "feedback-completion-dismiss" })}
        />
      ) : null}

      <ProposalSection
        ref={proposalsSectionRef}
        filters={proposalFilters}
        allFilters={allFilters}
        highlighted={state.feedbackCompletion?.highlight ?? false}
        onAccept={handleAcceptProposal}
        onReject={handleRejectProposal}
      />

      <ActiveFiltersSection
        filters={activeFilters}
        isArchiving={archiveFilter.isPending}
        onArchive={(filterId) => archiveFilter.mutate(filterId)}
      />

      <ArchivedFiltersSection
        filters={archivedFilters}
        isOpen={state.archivedOpen}
        isRestoring={restoreFilter.isPending}
        onToggle={() => dispatch({ type: "toggle-archived" })}
        onRestore={(filterId) => restoreFilter.mutate(filterId)}
      />

      <EmptyFiltersState
        isVisible={
          activeFilters.length === 0 &&
          archivedFilters.length === 0 &&
          draftFilters.length === 0 &&
          !isGenerating
        }
      />
    </div>
  );
}
