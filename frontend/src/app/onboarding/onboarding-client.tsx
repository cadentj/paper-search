"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
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
  useDocumentProcessingJob,
  useFilters,
  useOnboardingGenerationJob,
  usePromoteDraftFilters,
  useUpdateFilter,
  useUploadDocument,
} from "@/hooks/use-queries";
import { DocumentUploadResponse, FilterResponse } from "@/lib/api";
import {
  Archive,
  Check,
  FileText,
  Loader2,
  Pencil,
  Plus,
  Send,
  X,
} from "lucide-react";

const MAX_INPUT_CHARS = 2000;
const BLOCKING_DOCUMENT_STATUSES = new Set(["queued", "processing"]);

type UploadedDocument = DocumentUploadResponse;

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

function DocumentChip({
  document,
  onRemove,
  onUpdate,
}: {
  document: UploadedDocument;
  onRemove: (id: string) => void;
  onUpdate: (document: UploadedDocument) => void;
}) {
  const isActive = BLOCKING_DOCUMENT_STATUSES.has(document.status);
  const { data: documentJob } = useDocumentProcessingJob(
    isActive ? document.job_id : null
  );
  const latestDocument = documentJob?.subject;
  const job = documentJob?.job;
  const displayDocument = latestDocument
    ? { ...document, ...latestDocument, job_id: document.job_id }
    : document;

  useEffect(() => {
    if (
      latestDocument &&
      (latestDocument.status !== document.status ||
        latestDocument.updated_at !== document.updated_at)
    ) {
      onUpdate({ ...document, ...latestDocument, job_id: document.job_id });
    }
  }, [
    document,
    document.job_id,
    document.status,
    document.updated_at,
    latestDocument,
    onUpdate,
  ]);

  const isRunning =
    displayDocument.status === "queued" || displayDocument.status === "processing";

  return (
    <div className="flex min-w-0 items-center gap-2 rounded-md border bg-background px-2 py-1 text-sm">
      {isRunning ? (
        <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" />
      ) : (
        <FileText className="size-3.5 shrink-0 text-muted-foreground" />
      )}
      <span className="min-w-0 flex-1 truncate">{displayDocument.original_filename}</span>
      <Badge
        variant={
          displayDocument.status === "failed"
            ? "destructive"
            : displayDocument.status === "ready"
              ? "secondary"
              : "outline"
        }
      >
        {documentStatusLabel(displayDocument.status)}
      </Badge>
      {job?.progress?.message && isRunning ? (
        <span className="hidden max-w-36 truncate text-xs text-muted-foreground sm:inline">
          {job.progress.message}
        </span>
      ) : null}
      <Button
        variant="ghost"
        size="icon"
        className="size-6 shrink-0"
        aria-label={`Remove ${displayDocument.original_filename}`}
        onClick={() => onRemove(document.id)}
      >
        <X className="size-3" />
      </Button>
    </div>
  );
}

function DraftFilterCard({
  filter,
}: {
  filter: FilterResponse;
}) {
  const updateFilter = useUpdateFilter();
  const archiveFilter = useArchiveFilter();
  const [isEditing, setIsEditing] = useState(false);
  const [name, setName] = useState(filter.name);
  const [description, setDescription] = useState(filter.definition.description || "");

  const save = async () => {
    const nextName = name.trim();
    const nextDescription = description.trim();
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
    setIsEditing(false);
  };

  return (
    <Card>
      <CardContent className="pt-4">
        {isEditing ? (
          <div className="space-y-3">
            <Input
              aria-label="Filter name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <Input
              aria-label="Filter description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={save} disabled={updateFilter.isPending}>
                <Check className="mr-1 size-3" />
                Save
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setIsEditing(false)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 space-y-1">
              <p className="font-medium">{filter.name}</p>
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
                onClick={() => {
                  setName(filter.name);
                  setDescription(filter.definition.description || "");
                  setIsEditing(true);
                }}
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

export function OnboardingClient() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [inputText, setInputText] = useState("");
  const [documents, setDocuments] = useState<UploadedDocument[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [generationJobId, setGenerationJobId] = useState<string | null>(null);

  const uploadDocument = useUploadDocument();
  const createGeneration = useCreateOnboardingGeneration();
  const promoteDraftFilters = usePromoteDraftFilters();
  const { data: generationState } = useOnboardingGenerationJob(generationJobId);
  const generationJob = generationState?.job;
  const { data: draftFilters = [] } = useFilters("draft");

  const readyDocuments = documents.filter((document) => document.status === "ready");
  const blockingDocuments = documents.filter((document) =>
    BLOCKING_DOCUMENT_STATUSES.has(document.status)
  );
  const processedCount = documents.filter(
    (document) => !BLOCKING_DOCUMENT_STATUSES.has(document.status)
  ).length;
  const isGenerating =
    generationJob?.status === "queued" || generationJob?.status === "running";
  const canSend =
    !isGenerating &&
    !uploadDocument.isPending &&
    !createGeneration.isPending &&
    blockingDocuments.length === 0 &&
    inputText.length <= MAX_INPUT_CHARS &&
    (inputText.trim().length > 0 || readyDocuments.length > 0);

  const progressText = useMemo(() => {
    if (documents.length === 0) return null;
    return `${processedCount}/${documents.length} PDFs processed`;
  }, [documents.length, processedCount]);

  useEffect(() => {
    if (!generationState) return;
    if (generationState.items.length > 0) {
      queryClient.setQueryData<FilterResponse[]>(
        ["filters", "draft"],
        (current = []) => {
          const byId = new Map(current.map((filter) => [filter.id, filter]));
          generationState.items.forEach((filter) => byId.set(filter.id, filter));
          return Array.from(byId.values());
        }
      );
    }
  }, [generationState, queryClient]);

  const handleFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    setUploadError(null);
    try {
      const uploads = await Promise.all(
        Array.from(files).map((file) => uploadDocument.mutateAsync(file))
      );
      setDocuments((current) => [...current, ...uploads]);
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Upload failed");
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleSend = async () => {
    if (!canSend) return;
    const result = await createGeneration.mutateAsync({
      input_text: inputText,
      document_ids: readyDocuments.map((document) => document.id),
    });
    setGenerationJobId(result.job_id);
    setInputText("");
  };

  const handleAcceptDrafts = async () => {
    if (draftFilters.length === 0) return;
    await promoteDraftFilters.mutateAsync(draftFilters.map((filter) => filter.id));
  };

  const updateDocument = (nextDocument: UploadedDocument) => {
    setDocuments((current) =>
      current.map((document) =>
        document.id === nextDocument.id ? nextDocument : document
      )
    );
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 p-4 md:p-8">
      <div className="w-full max-w-3xl space-y-6">
        <div className="space-y-2 text-center">
          <h1 className="text-3xl font-semibold tracking-tight">Onboarding</h1>
          <p className="text-sm text-muted-foreground">
            Add research context to generate draft filters you can review and activate.
          </p>
        </div>

        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="onboarding-context">Research context</FieldLabel>
            <InputGroup>
              <InputGroupTextarea
                id="onboarding-context"
                value={inputText}
                maxLength={MAX_INPUT_CHARS}
                rows={7}
                placeholder="Add a research direction, question, claim, or context from your current work..."
                onChange={(event) => setInputText(event.target.value)}
                disabled={isGenerating}
              />
              <InputGroupAddon align="block-end" className="gap-2">
                <InputGroupButton
                  size="icon-sm"
                  variant="ghost"
                  aria-label="Upload PDF"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadDocument.isPending}
                >
                  {uploadDocument.isPending ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Plus className="size-4" />
                  )}
                </InputGroupButton>
                <InputGroupText>{inputText.length}/{MAX_INPUT_CHARS}</InputGroupText>
                {progressText ? <InputGroupText>{progressText}</InputGroupText> : null}
                <InputGroupButton
                  variant="default"
                  size="sm"
                  className="ml-auto"
                  onClick={handleSend}
                  disabled={!canSend}
                >
                  {isGenerating || createGeneration.isPending ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Send className="size-4" />
                  )}
                  Send
                </InputGroupButton>
              </InputGroupAddon>
            </InputGroup>
            <FieldDescription>
              PDFs must be 1 MB or smaller and 10 pages or fewer. OCR-only work is skipped until it is ready.
            </FieldDescription>
          </Field>
        </FieldGroup>

        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          multiple
          className="hidden"
          onChange={(event) => handleFiles(event.target.files)}
        />

        {uploadError ? (
          <p className="text-sm text-destructive">{uploadError}</p>
        ) : null}

        {documents.length > 0 ? (
          <div className="flex flex-col gap-2">
            {documents.map((document) => (
              <DocumentChip
                key={document.id}
                document={document}
                onUpdate={updateDocument}
                onRemove={(id) =>
                  setDocuments((current) =>
                    current.filter((document) => document.id !== id)
                  )
                }
              />
            ))}
          </div>
        ) : null}

        {generationJob ? (
          <Card>
            <CardContent className="flex items-center gap-2 pt-6 text-sm text-muted-foreground">
              {isGenerating ? <Loader2 className="size-4 animate-spin" /> : null}
              <span>{generationJob.progress?.message || generationJob.status}</span>
            </CardContent>
          </Card>
        ) : null}

        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">Draft Filters</h2>
              <p className="text-sm text-muted-foreground">
                Drafts are ignored by daily search until accepted.
              </p>
            </div>
            <Button
              onClick={handleAcceptDrafts}
              disabled={draftFilters.length === 0 || promoteDraftFilters.isPending}
            >
              {promoteDraftFilters.isPending ? (
                <Loader2 className="mr-2 size-4 animate-spin" />
              ) : (
                <Check className="mr-2 size-4" />
              )}
              Accept Drafts ({draftFilters.length})
            </Button>
          </div>

          {draftFilters.length > 0 ? (
            <div className="space-y-3">
              {draftFilters.map((filter) => (
                <DraftFilterCard key={filter.id} filter={filter} />
              ))}
            </div>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">No draft filters</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">
                Send context to create draft filters for review.
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
