"use client";

import Link from "next/link";
import { X, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePaper, usePaperHtml } from "@/hooks/use-queries";
import type { Paper } from "@/lib/api";

function getSourceUrl(paper?: Paper) {
  return (
    paper?.source_url ||
    (paper?.source_type === "arxiv" && paper?.source_id
      ? `https://arxiv.org/abs/${paper.source_id}`
      : undefined)
  );
}

function PaperHtmlBody({
  paper,
  htmlData,
}: {
  paper?: Paper;
  htmlData?: { html: string | null; source_url: string | null };
}) {
  if (htmlData?.html) {
    return (
      <iframe
        srcDoc={htmlData.html}
        title="Paper HTML"
        className="min-h-0 w-full flex-1 border-0"
        sandbox="allow-same-origin"
      />
    );
  }

  if (htmlData?.source_url) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center p-6">
        <div className="space-y-2 text-center">
          <p className="text-sm text-muted-foreground">HTML not available yet.</p>
          <Button
            variant="outline"
            size="sm"
            nativeButton={false}
            render={
              <a
                href={htmlData.source_url}
                target="_blank"
                rel="noopener noreferrer"
              />
            }
          >
            <ExternalLink className="mr-1 size-3" />
            View source
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-auto p-4">
      <p className="whitespace-pre-wrap text-sm text-muted-foreground">
        {paper?.search_text || "Loading paper…"}
      </p>
    </div>
  );
}

export function PaperReadPreview({
  paperId,
  onClose,
}: {
  paperId: string;
  onClose: () => void;
}) {
  const { data: paper, isLoading: paperLoading } = usePaper(paperId);
  const { data: htmlData, isLoading: htmlLoading } = usePaperHtml(paperId);
  const sourceUrl = getSourceUrl(paper);
  const sourceLabel = paper?.source_type === "lesswrong" ? "LessWrong" : "arXiv";

  return (
    <div className="flex min-h-[320px] flex-1 flex-col overflow-hidden rounded-lg border bg-card lg:min-h-0">
      <div className="flex shrink-0 items-start gap-2 border-b p-3">
        <div className="min-w-0 flex-1 space-y-1">
          <h2 className="text-sm font-semibold leading-snug">
            {paperLoading ? "Loading…" : paper?.title}
          </h2>
          {paper?.authors && paper.authors.length > 0 && (
            <p className="text-xs text-muted-foreground">
              {paper.authors.join(", ")}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {sourceUrl && (
            <Button
              variant="outline"
              size="sm"
              nativeButton={false}
              render={
                <a
                  href={sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                />
              }
            >
              <ExternalLink className="mr-1 size-3" />
              {sourceLabel}
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            nativeButton={false}
            render={<Link href={`/dashboard/papers/${paperId}`} />}
          >
            Full page
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label="Close preview"
          >
            <X className="size-4" />
          </Button>
        </div>
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {(paperLoading || htmlLoading) && !paper ? (
          <p className="p-4 text-sm text-muted-foreground">Loading paper…</p>
        ) : (
          <PaperHtmlBody paper={paper} htmlData={htmlData} />
        )}
      </div>
    </div>
  );
}
