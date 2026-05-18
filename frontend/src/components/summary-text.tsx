"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { PaperMatch, SummaryCitation } from "@/lib/api";

const CITE_MARKER_RE = /<cite\s+(itemId|arxivId)=(["'])([^"']+)\2\s*\/>/g;
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
  const citationsByItemId = new Map(
    citations.map((citation) => [citation.itemId || citation.arxivId || "", citation])
  );
  const matchesByItemId = new Map<string, PaperMatch>();
  matches.forEach((match) => {
    if (match.paper_item_label) {
      matchesByItemId.set(match.paper_item_label, match);
    }
    if (match.paper_source_type && match.paper_source_id) {
      matchesByItemId.set(`${match.paper_source_type}:${match.paper_source_id}`, match);
      matchesByItemId.set(match.paper_source_id, match);
    }
  });

  for (const match of summary.matchAll(CITE_MARKER_RE)) {
    const marker = match[0];
    const markerIndex = match.index ?? 0;
    const itemId = match[3].trim();

    if (markerIndex > cursor) {
      nodes.push(summary.slice(cursor, markerIndex));
    }

    const citation = citationsByItemId.get(itemId);
    const paperMatch = matchesByItemId.get(itemId);
    const label = `Open citation ${citationIndex + 1}: ${itemId}`;

    if (paperMatch) {
      nodes.push(
        <Link
          key={`${itemId}-${markerIndex}`}
          href={`/dashboard/papers/${paperMatch.paper_id}`}
          title={citation?.citedFor}
          aria-label={label}
          className={citationClassName(true)}
        >
          {itemId}
        </Link>
      );
    } else {
      nodes.push(
        <span
          key={`${itemId}-${markerIndex}`}
          title={citation?.citedFor}
          aria-label={`Unlinked citation ${citationIndex + 1}: ${itemId}`}
          className={citationClassName(false)}
        >
          {itemId}
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
