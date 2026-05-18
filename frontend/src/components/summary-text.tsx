"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { PaperMatch, SummaryCitation } from "@/lib/api";

const CITE_MARKER_RE = /<cite\s+arxivId=(["'])([^"']+)\1\s*\/>/g;
const EMPTY_CITATIONS: SummaryCitation[] = [];
const EMPTY_MATCHES: PaperMatch[] = [];

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
  citations = EMPTY_CITATIONS,
  matches = EMPTY_MATCHES,
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
  const citationsByArxivId = new Map(
    citations.map((citation) => [citation.arxivId, citation])
  );
  const matchesByArxivId = new Map<string, PaperMatch>();
  matches.forEach((match) => {
    if (match.paper_arxiv_id) {
      matchesByArxivId.set(match.paper_arxiv_id, match);
    }
  });

  for (const match of summary.matchAll(CITE_MARKER_RE)) {
    const marker = match[0];
    const markerIndex = match.index ?? 0;
    const arxivId = match[2].trim();

    if (markerIndex > cursor) {
      nodes.push(summary.slice(cursor, markerIndex));
    }

    const citation = citationsByArxivId.get(arxivId);
    const paperMatch = matchesByArxivId.get(arxivId);
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
