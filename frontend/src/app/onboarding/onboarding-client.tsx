"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCreateExtraction,
  useOnboardingExtraction,
  useCompleteOnboarding,
  useResetOnboarding,
  useJob,
} from "@/hooks/use-queries";
import { ProposedFilter } from "@/lib/api";
import { Loader2, X, RotateCcw, Pencil, Check } from "lucide-react";

const EMPTY_PROPOSED_FILTERS: ProposedFilter[] = [];
const ONBOARDING_SKELETON_KEYS = [
  "onboarding-skeleton-1",
  "onboarding-skeleton-2",
  "onboarding-skeleton-3",
];

export function OnboardingClient() {
  const { push } = useRouter();
  const [inputText, setInputText] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [editedFilters, setEditedFilters] = useState<ProposedFilter[]>([]);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const seenProposedFilterIds = useRef<Set<string>>(new Set());

  const createExtraction = useCreateExtraction();
  const { data: job } = useJob(jobId);
  const isExtracting = job?.status === "queued" || job?.status === "running";
  const extractionId =
    job?.subject_type === "onboarding_extraction" ? job.subject_id || null : null;
  const { data: extraction } = useOnboardingExtraction(extractionId, isExtracting);
  const completeOnboarding = useCompleteOnboarding();
  const resetOnboarding = useResetOnboarding();

  const isComplete = extraction?.status === "completed" || job?.status === "completed";
  const proposedFilters = extraction?.proposed_filters ?? EMPTY_PROPOSED_FILTERS;

  const handleSubmit = async () => {
    if (!inputText.trim()) return;
    const result = await createExtraction.mutateAsync({
      input_text: inputText,
    });
    setJobId(result.job_id);
  };

  useEffect(() => {
    if (!extractionId) {
      seenProposedFilterIds.current.clear();
      return;
    }

    const additions = proposedFilters.filter(
      (filter) => !seenProposedFilterIds.current.has(filter.id)
    );
    proposedFilters.forEach((filter) =>
      seenProposedFilterIds.current.add(filter.id)
    );

    if (additions.length === 0) return;
    setEditedFilters((prev) => {
      const existingIds = new Set(prev.map((f) => f.id));
      const unseenAdditions = additions.filter((f) => !existingIds.has(f.id));
      return unseenAdditions.length ? [...prev, ...unseenAdditions] : prev;
    });
  }, [extractionId, proposedFilters]);

  const handleRemoveFilter = (idx: number) => {
    setEditedFilters((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleComplete = async () => {
    if (editedFilters.length === 0) return;
    await completeOnboarding.mutateAsync(
      editedFilters.map((f) => ({
        name: f.name,
        definition: {
          name: f.name,
          description: f.description,
          mode: f.mode || "topic",
        },
      }))
    );
    push("/dashboard/daily");
  };

  const handleReset = async () => {
    await resetOnboarding.mutateAsync();
    setInputText("");
    setJobId(null);
    setEditedFilters([]);
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <div className="w-full max-w-2xl space-y-6">
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight">Paper Search</h1>
          <p className="text-muted-foreground">
            Tell us about your research interests and we&apos;ll create
            personalized search filters.
          </p>
        </div>

        {!isComplete && (
          <Card>
            <CardHeader>
              <CardTitle>Your Research Interests</CardTitle>
              <CardDescription>
                Describe your current research interests, hypotheses, open
                questions, and topics you want to follow.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Textarea
                aria-label="Research interests"
                name="research-interests"
                autoComplete="off"
                placeholder="I'm interested in mechanistic interpretability of language models, particularly circuit discovery and sparse autoencoders. I'm tracking hypotheses about whether…"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                rows={8}
                disabled={isExtracting || createExtraction.isPending}
              />
              <div className="flex gap-2">
                <Button
                  onClick={handleSubmit}
                  disabled={
                    !inputText.trim() ||
                    isExtracting ||
                    createExtraction.isPending
                  }
                  className="flex-1"
                >
                  {isExtracting ? (
                    <>
                      <Loader2 className="mr-2 size-4 animate-spin" />
                      Generating filters…
                    </>
                  ) : (
                    "Generate Search Filters"
                  )}
                </Button>
              </div>
              {(extraction?.status === "failed" || job?.status === "failed") && (
                <p className="text-sm text-destructive">
                  {extraction?.error || job?.error || "Extraction failed. Please try again."}
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {isExtracting && editedFilters.length === 0 && (
          <div className="space-y-3">
            {ONBOARDING_SKELETON_KEYS.map((key) => (
              <Skeleton key={key} className="h-24 w-full rounded-lg" />
            ))}
          </div>
        )}

        {(isComplete || editedFilters.length > 0) && (
          <>
            <div className="space-y-2">
              <h2 className="text-lg font-semibold">
                Proposed Filters ({editedFilters.length})
              </h2>
              <p className="text-sm text-muted-foreground">
                {isExtracting
                  ? "Filters will appear here as they are generated."
                  : "Review, edit, or remove filters before completing setup."}
              </p>
            </div>

            <div className="space-y-3">
              {editedFilters.map((f, idx) => (
                <Card key={f.id}>
                  <CardContent className="pt-4">
                    {editingIdx === idx ? (
                      <div className="space-y-3">
                        <Input
                          aria-label="Filter name"
                          name={`filter-${f.id}-name`}
                          autoComplete="off"
                          value={f.name}
                          onChange={(e) => {
                            const updated = [...editedFilters];
                            updated[idx] = {
                              ...f,
                              name: e.target.value,
                            };
                            setEditedFilters(updated);
                          }}
                          placeholder="Filter name…"
                        />
                        <Textarea
                          aria-label="Filter description"
                          name={`filter-${f.id}-description`}
                          autoComplete="off"
                          value={f.description}
                          onChange={(e) => {
                            const updated = [...editedFilters];
                            updated[idx] = {
                              ...f,
                              description: e.target.value,
                            };
                            setEditedFilters(updated);
                          }}
                          placeholder="Description…"
                          rows={3}
                        />
                        <Button
                          size="sm"
                          onClick={() => setEditingIdx(null)}
                        >
                          <Check className="mr-1 size-3" /> Done
                        </Button>
                      </div>
                    ) : (
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 space-y-1">
                          <p className="font-medium">{f.name}</p>
                          <p className="text-sm text-muted-foreground">
                            {f.description}
                          </p>
                        </div>
                        <div className="flex gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-7"
                            aria-label={`Edit ${f.name}`}
                            onClick={() => setEditingIdx(idx)}
                          >
                            <Pencil className="size-3" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-7"
                            aria-label={`Remove ${f.name}`}
                            onClick={() => handleRemoveFilter(idx)}
                          >
                            <X className="size-3" />
                          </Button>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>

            <div className="flex gap-2">
              <Button
                onClick={handleComplete}
                disabled={isExtracting || completeOnboarding.isPending}
                className="flex-1"
              >
                {completeOnboarding.isPending ? (
                  <Loader2 className="mr-2 size-4 animate-spin" />
                ) : null}
                Complete Setup ({editedFilters.length} filters)
              </Button>
            </div>
          </>
        )}

        <div className="flex justify-center">
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            onClick={handleReset}
            disabled={resetOnboarding.isPending}
          >
            <RotateCcw className="mr-1 size-3" />
            Reset
          </Button>
        </div>
      </div>
    </div>
  );
}
