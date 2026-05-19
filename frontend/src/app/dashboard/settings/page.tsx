"use client";

import { useEffect, useState } from "react";
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
import { useDataSources, useUpdateDataSource } from "@/hooks/use-queries";
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
  const [time, setTime] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api.getDailySchedule()
      .then((data) => {
        setTime(data.time || "");
        setEnabled(data.enabled);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const result = await api.updateDailySchedule({ time: time || null, enabled });
      setTime(result.time || "");
      setEnabled(result.enabled);
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  };

  if (!loaded) return null;

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
            value={time}
            onChange={(e) => setTime(e.target.value)}
            className="w-36"
          />
          <Button
            variant={enabled ? "outline" : "default"}
            size="sm"
            onClick={() => setEnabled(!enabled)}
          >
            {enabled ? "Enabled" : "Disabled"}
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="mr-1 size-3 animate-spin" />}
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
