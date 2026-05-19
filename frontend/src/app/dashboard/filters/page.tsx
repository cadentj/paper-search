"use client";

import {
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
  type RefObject,
} from "react";
import { useQueries, useQueryClient } from "@tanstack/react-query";
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
  FieldDescription,
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
  useOnboardingGenerationJob,
  useProcessFeedback,
  usePromoteDraftFilters,
  useRestoreFilter,
  useUpdateFilter,
  useUploadDocument,
} from "@/hooks/use-queries";
import {
  api,
  DocumentProcessingJobResponse,
  DocumentUploadResponse,
  FeedbackStatus,
  FilterResponse,
} from "@/lib/api";
import {
  Archive,
  Check,
  ChevronDown,
  ChevronRight,
  FileText,
  GraduationCap,
  Loader2,
  Pencil,
  Plus,
  RotateCcw,
  Send,
  X,
} from "lucide-react";

const MAX_INPUT_CHARS = 2000;
const BLOCKING_DOCUMENT_STATUSES = new Set(["queued", "processing"]);

type UploadedDocument = DocumentUploadResponse;
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
  documents: UploadedDocument[];
  uploadError: string | null;
  generationJobId: string | null;
  archivedOpen: boolean;
};
type FilterPageAction =
  | { type: "set-input-text"; value: string }
  | { type: "add-documents"; documents: UploadedDocument[] }
  | { type: "remove-document"; id: string }
  | { type: "set-upload-error"; error: string | null }
  | { type: "generation-started"; jobId: string }
  | { type: "toggle-archived" };

function documentStatusLabel(status: string) {
  switch (status) {
    case "queued":
      return "Queued";
    case "processing":
      return "Processing";
    case "ready":
      return "Ready";
    case "needs_ocr":
      return "Needs OCR";
    case "failed":
      return "Failed";
    default:
      return status;
  }
}

function documentJobRefetchInterval(query: {
  state: { data?: DocumentProcessingJobResponse };
}) {
  return query.state.data?.done ? false : 1000;
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
    case "add-documents":
      return { ...state, documents: [...state.documents, ...action.documents] };
    case "remove-document":
      return {
        ...state,
        documents: state.documents.filter(
          (uploadedDocument) => uploadedDocument.id !== action.id
        ),
      };
    case "set-upload-error":
      return { ...state, uploadError: action.error };
    case "generation-started":
      return { ...state, generationJobId: action.jobId, inputText: "" };
    case "toggle-archived":
      return { ...state, archivedOpen: !state.archivedOpen };
  }
}

function DocumentChip({
  uploadedDocument,
  onRemove,
}: {
  uploadedDocument: UploadedDocument;
  onRemove: (id: string) => void;
}) {
  const isRunning = BLOCKING_DOCUMENT_STATUSES.has(uploadedDocument.status);

  return (
    <div className="flex min-w-0 items-center gap-2 rounded-md border bg-background px-2 py-1 text-sm">
      {isRunning ? (
        <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" />
      ) : (
        <FileText className="size-3.5 shrink-0 text-muted-foreground" />
      )}
      <span className="min-w-0 flex-1 truncate">
        {uploadedDocument.original_filename}
      </span>
      <Badge
        variant={
          uploadedDocument.status === "failed"
            ? "destructive"
            : uploadedDocument.status === "ready"
              ? "secondary"
              : "outline"
        }
      >
        {documentStatusLabel(uploadedDocument.status)}
      </Badge>
      <Button
        variant="ghost"
        size="icon"
        className="size-6 shrink-0"
        aria-label={`Remove ${uploadedDocument.original_filename}`}
        onClick={() => onRemove(uploadedDocument.id)}
      >
        <X className="size-3" />
      </Button>
    </div>
  );
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
  const importIdRef = useRef<string | null>(null);
  const [state, dispatch] = useReducer(scholarImportReducer, {
    url: "",
    step: "input",
    profile: null,
    error: null,
  });

  useEffect(() => {
    if (state.step !== "polling" || !importIdRef.current) return;
    const importId = importIdRef.current;
    const interval = setInterval(async () => {
      try {
        const status = await api.getScholarImportStatus(importId);
        if (status.status === "completed") {
          dispatch({ type: "done" });
          queryClient.invalidateQueries({ queryKey: ["filters"] });
          clearInterval(interval);
        } else if (status.status === "failed") {
          dispatch({ type: "error", error: status.error || "Import failed" });
          clearInterval(interval);
        }
      } catch {
        // keep polling
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [state.step, queryClient]);

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
      importIdRef.current = result.id;
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
              state.step === "verifying" ||
              state.step === "importing" ||
              state.step === "polling"
            }
          />
          {(state.step === "input" || state.step === "error") && (
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
        {state.step === "verifying" && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Verifying profile…
          </div>
        )}
        {state.step === "verified" && state.profile && (
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
        {(state.step === "importing" || state.step === "polling") && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            {state.step === "importing"
              ? "Starting import…"
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
      <CardContent className="pt-4 space-y-2">
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
  progressText,
  status,
  fileInputRef,
  onInputTextChange,
  onSend,
}: {
  inputText: string;
  progressText: string | null;
  status: {
    isGenerating: boolean;
    isUploading: boolean;
    isCreating: boolean;
    canSend: boolean;
  };
  fileInputRef: RefObject<HTMLInputElement | null>;
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
          <InputGroupAddon align="block-end" className="gap-2">
            <InputGroupButton
              size="icon-sm"
              variant="ghost"
              aria-label="Upload PDF"
              onClick={() => fileInputRef.current?.click()}
              disabled={status.isUploading}
            >
              {status.isUploading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Plus className="size-4" />
              )}
            </InputGroupButton>
            <InputGroupText>
              {inputText.length}/{MAX_INPUT_CHARS}
            </InputGroupText>
            {progressText ? <InputGroupText>{progressText}</InputGroupText> : null}
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
        <FieldDescription>
          PDFs must be 1 MB or smaller and 10 pages or fewer. OCR-only work is
          skipped until it is ready.
        </FieldDescription>
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

function FeedbackCard({
  status,
  isProcessing,
  onProcess,
}: {
  status?: FeedbackStatus;
  isProcessing: boolean;
  onProcess: () => void;
}) {
  if (!status || (status.pending_votes === 0 && status.pending_notes === 0)) {
    return null;
  }

  return (
    <Card>
      <CardContent className="pt-4 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Pending Feedback</p>
          <p className="text-xs text-muted-foreground">
            {status.pending_votes} vote{status.pending_votes !== 1 ? "s" : ""}
            {status.pending_notes > 0 &&
              `, ${status.pending_notes} note${
                status.pending_notes !== 1 ? "s" : ""
              }`}
          </p>
        </div>
        <Button size="sm" onClick={onProcess} disabled={isProcessing}>
          {isProcessing ? (
            <Loader2 className="mr-1 size-3 animate-spin" />
          ) : null}
          Process Feedback
        </Button>
      </CardContent>
    </Card>
  );
}

function ProposalSection({
  filters,
  allFilters,
  onAccept,
  onReject,
}: {
  filters: FilterResponse[];
  allFilters: FilterResponse[];
  onAccept: (filterId: string) => void;
  onReject: (filterId: string) => void;
}) {
  if (filters.length === 0) return null;

  return (
    <div className="space-y-3">
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

function EmptyFiltersState({ isVisible }: { isVisible: boolean }) {
  if (!isVisible) return null;

  return (
    <Card>
      <CardContent className="pt-6 text-center">
        <p className="text-muted-foreground">
          No filters yet. Add research context above to generate filters.
        </p>
      </CardContent>
    </Card>
  );
}

export default function FiltersPage() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [state, dispatch] = useReducer(filterPageReducer, {
    inputText: "",
    documents: [],
    uploadError: null,
    generationJobId: null,
    archivedOpen: false,
  });

  const uploadDocument = useUploadDocument();
  const createGeneration = useCreateOnboardingGeneration();
  const promoteDraftFilters = usePromoteDraftFilters();
  const archiveFilter = useArchiveFilter();
  const restoreFilter = useRestoreFilter();
  const processFeedback = useProcessFeedback();
  const { data: feedbackStatus } = useFeedbackStatus();
  const { data: generationState } = useOnboardingGenerationJob(
    state.generationJobId
  );
  const generationJob = generationState?.job;
  const { data: draftFilters = [] } = useFilters("draft");
  const { data: allFilters = [] } = useFilters();

  const documentJobs = useQueries({
    queries: state.documents.map((uploadedDocument) => ({
      queryKey: ["jobs", "document-processing", uploadedDocument.job_id],
      queryFn: () => api.getDocumentProcessingJob(uploadedDocument.job_id),
      enabled: BLOCKING_DOCUMENT_STATUSES.has(uploadedDocument.status),
      refetchInterval: documentJobRefetchInterval,
    })),
  });

  const displayDocuments = useMemo(
    () =>
      state.documents.map((uploadedDocument, index) => {
        const latestDocument = documentJobs[index]?.data?.subject;
        return latestDocument
          ? {
              ...uploadedDocument,
              ...latestDocument,
              job_id: uploadedDocument.job_id,
            }
          : uploadedDocument;
      }),
    [state.documents, documentJobs]
  );

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
  const readyDocuments = displayDocuments.filter(
    (uploadedDocument) => uploadedDocument.status === "ready"
  );
  const blockingDocuments = displayDocuments.filter((uploadedDocument) =>
    BLOCKING_DOCUMENT_STATUSES.has(uploadedDocument.status)
  );
  const processedCount = displayDocuments.filter(
    (uploadedDocument) =>
      !BLOCKING_DOCUMENT_STATUSES.has(uploadedDocument.status)
  ).length;
  const isGenerating =
    generationJob?.status === "queued" || generationJob?.status === "running";
  const canSend =
    !isGenerating &&
    !uploadDocument.isPending &&
    !createGeneration.isPending &&
    blockingDocuments.length === 0 &&
    state.inputText.length <= MAX_INPUT_CHARS &&
    (state.inputText.trim().length > 0 || readyDocuments.length > 0);

  const progressText = useMemo(() => {
    if (displayDocuments.length === 0) return null;
    return `${processedCount}/${displayDocuments.length} PDFs processed`;
  }, [displayDocuments.length, processedCount]);

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

  const handleFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    dispatch({ type: "set-upload-error", error: null });
    try {
      const uploads = await Promise.all(
        Array.from(files).map((file) => uploadDocument.mutateAsync(file))
      );
      dispatch({ type: "add-documents", documents: uploads });
    } catch (error) {
      dispatch({
        type: "set-upload-error",
        error: error instanceof Error ? error.message : "Upload failed",
      });
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleSend = async () => {
    if (!canSend) return;
    const result = await createGeneration.mutateAsync({
      input_text: state.inputText,
      document_ids: readyDocuments.map((uploadedDocument) => uploadedDocument.id),
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
        progressText={progressText}
        status={{
          isGenerating,
          isUploading: uploadDocument.isPending,
          isCreating: createGeneration.isPending,
          canSend,
        }}
        fileInputRef={fileInputRef}
        onInputTextChange={(value) =>
          dispatch({ type: "set-input-text", value })
        }
        onSend={handleSend}
      />

      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        multiple
        className="hidden"
        onChange={(event) => handleFiles(event.target.files)}
      />

      {state.uploadError ? (
        <p className="text-sm text-destructive">{state.uploadError}</p>
      ) : null}

      {displayDocuments.length > 0 ? (
        <div className="flex flex-col gap-2">
          {displayDocuments.map((uploadedDocument) => (
            <DocumentChip
              key={uploadedDocument.id}
              uploadedDocument={uploadedDocument}
              onRemove={(id) =>
                dispatch({ type: "remove-document", id })
              }
            />
          ))}
        </div>
      ) : null}

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
        isProcessing={processFeedback.isPending}
        onProcess={() => processFeedback.mutate()}
      />

      <ProposalSection
        filters={proposalFilters}
        allFilters={allFilters}
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
