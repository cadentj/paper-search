"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { PaperMatch, SummaryCitation } from "@/lib/api";

const CITE_MARKER_RE = /<cite\s+arxivId=(["'])([^"']+)\1\s*\/>/g;

function citationClassName(isLinked: boolean) {
  return [
    "mx-1 inline-flex h-6 items-center rounded-md border border-border px-2 align-baseline text-xs font-medium leading-none text-muted-foreground transition-colors",
    isLinked
      ? "hover:bg-accent hover:text-accent-foreground"
      : "cursor-default opacity-60",
  ].join(" ");
}

export function SummaryText({
  summary,
  citations = [],
  matches = [],
  className,
}: {
  summary: string;
  citations?: SummaryCitation[];
  matches?: PaperMatch[];
  className?: string;
}) {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let citationIndex = 0;

  for (const match of summary.matchAll(CITE_MARKER_RE)) {
    const marker = match[0];
    const markerIndex = match.index ?? 0;
    const arxivId = match[2].trim();

    if (markerIndex > cursor) {
      nodes.push(summary.slice(cursor, markerIndex));
    }

    const citation = citations.find((c) => c.arxivId === arxivId);
    const paperMatch = matches.find((m) => m.paper_arxiv_id === arxivId);
    const label = `Open citation ${citationIndex + 1}: ${arxivId}`;

    if (paperMatch) {
      nodes.push(
        <Link
          key={`${arxivId}-${markerIndex}`}
          href={`/dashboard/papers/${paperMatch.paper_id}`}
          title={citation?.citedFor}
          aria-label={label}
          className={citationClassName(true)}
        >
          {arxivId}
        </Link>
      );
    } else {
      nodes.push(
        <span
          key={`${arxivId}-${markerIndex}`}
          title={citation?.citedFor}
          aria-label={`Unlinked citation ${citationIndex + 1}: ${arxivId}`}
          className={citationClassName(false)}
        >
          {arxivId}
        </span>
      );
    }

    citationIndex += 1;
    cursor = markerIndex + marker.length;
  }

  if (cursor < summary.length) {
    nodes.push(summary.slice(cursor));
  }

  return (
    <div className={className}>
      {nodes.length > 0 ? nodes : summary}
    </div>
  );
}
