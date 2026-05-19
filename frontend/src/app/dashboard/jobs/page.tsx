"use client";

import Link from "next/link";
import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useJobsOverview } from "@/hooks/use-queries";
import type { Job, JobOverviewEntry } from "@/lib/api";

function jobProgressPercent(job: Job): number {
  const total = Math.max(job.progress?.total ?? 1, 1);
  const current = Math.min(job.progress?.current ?? 0, total);
  return Math.round((current / total) * 100);
}

function statusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "failed") return "destructive";
  if (status === "completed") return "default";
  if (status === "skipped") return "outline";
  return "secondary";
}

function JobRow({ entry }: { entry: JobOverviewEntry }) {
  const { job, href } = entry;
  const percent = jobProgressPercent(job);
  const total = Math.max(job.progress?.total ?? 1, 1);
  const current = Math.min(job.progress?.current ?? 0, total);
  const showProgress = job.status === "queued" || job.status === "running";

  const title = href ? (
    <Link href={href} className="font-medium hover:underline">
      {job.kind}
    </Link>
  ) : (
    <span className="font-medium">{job.kind}</span>
  );

  return (
    <div className="space-y-2 rounded-lg border p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          {title}
          <p className="text-xs text-muted-foreground">
            Queue: {job.queue_name ?? "unknown"}
          </p>
        </div>
        <Badge variant={statusVariant(job.status)}>{job.status}</Badge>
      </div>
      {showProgress ? (
        <div className="space-y-1">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              {total > 1 ? `${current} / ${total}` : "In progress"}
            </span>
            <span className="font-medium tabular-nums">{percent}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-[width]"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
      ) : null}
      {job.error ? (
        <p className="text-sm text-destructive">{job.error}</p>
      ) : null}
    </div>
  );
}

function JobSection({
  title,
  entries,
  emptyMessage,
}: {
  title: string;
  entries: JobOverviewEntry[];
  emptyMessage: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">{emptyMessage}</p>
        ) : (
          entries.map((entry) => <JobRow key={entry.job.id} entry={entry} />)
        )}
      </CardContent>
    </Card>
  );
}

export default function JobsPage() {
  const { data, isLoading } = useJobsOverview();

  if (isLoading && !data) {
    return (
      <div className="flex items-center justify-center gap-2 py-12 text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        Loading jobs…
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>
        <p className="text-sm text-muted-foreground">
          Background work across daily search, idea maps, feedback, and setup.
        </p>
      </div>
      <JobSection
        title="Active"
        entries={data?.active ?? []}
        emptyMessage="No jobs are running right now."
      />
      <JobSection
        title="Recent"
        entries={data?.recent ?? []}
        emptyMessage="No recently finished jobs."
      />
    </div>
  );
}
