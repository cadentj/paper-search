"use client";

import { Database, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useDataSources, useUpdateDataSource } from "@/hooks/use-queries";
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
    </div>
  );
}
