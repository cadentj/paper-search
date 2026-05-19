"use client";

import { useState } from "react";
import { Clock, Database, GraduationCap, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  useDailySchedule,
  useDataSources,
  useUpdateDailySchedule,
  useUpdateDataSource,
} from "@/hooks/use-queries";
import { api } from "@/lib/api";
import type { DataSource } from "@/lib/api";

const SOURCE_DESCRIPTIONS: Record<string, string> = {
  arxiv: "R2-indexed arXiv papers in the configured research categories.",
  lesswrong: "R2-indexed LessWrong posts from the configured cache.",
};

function SourceRow({
  source,
  isPending,
  onToggle,
}: {
  source: DataSource;
  isPending: boolean;
  onToggle: (source: DataSource) => void;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="flex items-center gap-2 text-base">
              <Database className="size-4" />
              {source.name}
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              {SOURCE_DESCRIPTIONS[source.source_type] || "External content source."}
            </p>
          </div>
          <Badge variant={source.enabled ? "secondary" : "outline"}>
            {source.enabled ? "Enabled" : "Disabled"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">
          {source.source_type === "lesswrong"
            ? "When enabled, Daily searches include cached LessWrong posts. HTML is fetched from R2 during matching and when opened."
            : "When enabled, Daily searches include arXiv papers. Paper HTML stays in R2 and is fetched only when opened."}
        </p>
        <Button
          variant={source.enabled ? "outline" : "default"}
          size="sm"
          onClick={() => onToggle(source)}
          disabled={isPending}
        >
          {isPending && <Loader2 className="mr-2 size-3 animate-spin" />}
          {source.enabled ? "Disable" : "Enable"}
        </Button>
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const { data: sources, isLoading } = useDataSources();
  const updateSource = useUpdateDataSource();

  return (
    <div className="flex-1 p-6 space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Configure which sources contribute items to daily searches.
        </p>
      </div>

      <div className="space-y-3">
        {isLoading && (
          <Card>
            <CardContent className="flex items-center gap-2 pt-6 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading data sources…
            </CardContent>
          </Card>
        )}
        {sources?.map((source) => (
          <SourceRow
            key={source.source_type}
            source={source}
            isPending={updateSource.isPending}
            onToggle={(nextSource) =>
              updateSource.mutate({
                sourceType: nextSource.source_type,
                input: { enabled: !nextSource.enabled },
              })
            }
          />
        ))}
      </div>

      <DailyScheduleSection />
      <ScholarReimportSection />
    </div>
  );
}

function ScholarReimportSection() {
  const [url, setUrl] = useState("");
  const [step, setStep] = useState<"input" | "verifying" | "importing" | "done" | "error">("input");
  const [error, setError] = useState<string | null>(null);

  const handleImport = async () => {
    if (!url.trim()) return;
    setStep("verifying");
    setError(null);
    try {
      const profile = await api.verifyScholarProfile(url);
      setStep("importing");
      await api.startScholarImport({
        url,
        author_id: profile.author_id,
        display_name: profile.name,
      });
      setStep("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
      setStep("error");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <GraduationCap className="size-4" />
          Semantic Scholar Re-import
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {step === "done" ? (
          <p className="text-sm text-muted-foreground">
            Re-import started. New draft filters will appear on the Filters page.
          </p>
        ) : (
          <>
            <div className="flex gap-2">
              <Input
                placeholder="Paste Semantic Scholar profile URL..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                disabled={step === "verifying" || step === "importing"}
              />
              <Button
                size="sm"
                onClick={handleImport}
                disabled={!url.trim() || step === "verifying" || step === "importing"}
              >
                {(step === "verifying" || step === "importing") && (
                  <Loader2 className="mr-1 size-3 animate-spin" />
                )}
                Re-import
              </Button>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <p className="text-xs text-muted-foreground">
              Re-import your Semantic Scholar profile to generate new draft filters from your latest publications.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function DailyScheduleSection() {
  const { data: schedule, isLoading } = useDailySchedule();
  const updateSchedule = useUpdateDailySchedule();
  const [draft, setDraft] = useState<{
    time: string;
    enabled: boolean;
  } | null>(null);
  const currentSchedule = draft ?? {
    time: schedule?.time || "",
    enabled: schedule?.enabled ?? false,
  };

  const handleSave = async () => {
    const result = await updateSchedule.mutateAsync({
      time: currentSchedule.time || null,
      enabled: currentSchedule.enabled,
    });
    setDraft({ time: result.time || "", enabled: result.enabled });
  };

  if (isLoading) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Clock className="size-4" />
          Daily Search Schedule
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-3">
          <Input
            type="time"
            value={currentSchedule.time}
            onChange={(e) =>
              setDraft({ ...currentSchedule, time: e.target.value })
            }
            className="w-36"
          />
          <Button
            variant={currentSchedule.enabled ? "outline" : "default"}
            size="sm"
            onClick={() =>
              setDraft({
                ...currentSchedule,
                enabled: !currentSchedule.enabled,
              })
            }
          >
            {currentSchedule.enabled ? "Enabled" : "Disabled"}
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={updateSchedule.isPending}
          >
            {updateSchedule.isPending && (
              <Loader2 className="mr-1 size-3 animate-spin" />
            )}
            Save
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Set a preferred time for daily searches. Scheduling is not yet automated.
        </p>
      </CardContent>
    </Card>
  );
}
