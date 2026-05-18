"use client";

import { useState, useRef, use } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  usePaper,
  usePaperHtml,
  useIdeaMap,
  useGenerateIdeaMap,
} from "@/hooks/use-queries";
import {
  Loader2,
  Sparkles,
  ChevronDown,
  ChevronRight,
  ArrowLeft,
  ExternalLink,
} from "lucide-react";
import { useRouter } from "next/navigation";
import type { IdeaMapClaim, IdeaMapWarrant } from "@/lib/api";

export default function PaperDetailPage({
  params,
}: {
  params: Promise<{ paperId: string }>;
}) {
  const { paperId } = use(params);
  const router = useRouter();
  const { data: paper } = usePaper(paperId);
  const { data: htmlData } = usePaperHtml(paperId);
  const { data: ideaMap, error: ideaMapError } = useIdeaMap(paperId);
  const generateIdeaMap = useGenerateIdeaMap();

  const [expandedClaims, setExpandedClaims] = useState<Set<string>>(new Set());
  const [highlightedWarrant, setHighlightedWarrant] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const isIdeaMapLoading =
    ideaMap?.status === "queued" ||
    ideaMap?.status === "running" ||
    ideaMap?.status === "claims_running" ||
    ideaMap?.status === "warrants_running";
  const isIdeaMapComplete = ideaMap?.status === "completed";
  const isIdeaMapEmpty =
    isIdeaMapComplete && (!ideaMap.claims || ideaMap.claims.length === 0);
  const isIdeaMapSkipped = ideaMap?.status === "skipped";
  const ideaMapClaims = ideaMap?.claims || [];
  const shouldRenderIdeaMapClaims = ideaMapClaims.length > 0;
  const ideaMapLoadingLabel =
    ideaMap?.status === "claims_running"
      ? "Finding core claims…"
      : ideaMap?.status === "warrants_running"
        ? "Finding warrants…"
        : "Generating idea map…";

  const toggleClaim = (claimId: string) => {
    setExpandedClaims((prev) => {
      const next = new Set(prev);
      if (next.has(claimId)) next.delete(claimId);
      else next.add(claimId);
      return next;
    });
  };

  const handleWarrantClick = (warrant: IdeaMapWarrant) => {
    setHighlightedWarrant(warrant.id);
    if (iframeRef.current?.contentWindow && warrant.citation) {
      const { startBlockId, endBlockId } = warrant.citation;
      if (startBlockId && endBlockId) {
        try {
          const doc = iframeRef.current.contentDocument;
          if (doc) {
            const prevHighlights = doc.querySelectorAll(".ps-highlight");
            prevHighlights.forEach((el) => {
              el.classList.remove("ps-highlight");
              (el as HTMLElement).style.backgroundColor = "";
              (el as HTMLElement).style.outline = "";
              (el as HTMLElement).style.scrollMarginTop = "";
            });

            const start = doc.getElementById(startBlockId);
            const end = doc.getElementById(endBlockId);
            if (start && end) {
              const blockSelector =
                "p[id], h1[id], h2[id], h3[id], h4[id], h5[id], h6[id], li[id], td[id], th[id], figcaption[id], blockquote[id]";
              const blocks = Array.from(doc.querySelectorAll(blockSelector));
              const startIndex = blocks.indexOf(start);
              const endIndex = blocks.indexOf(end);
              const highlightedBlocks =
                startIndex >= 0 && endIndex >= startIndex
                  ? blocks.slice(startIndex, endIndex + 1)
                  : [start];

              highlightedBlocks.forEach((el) => {
                const target = el as HTMLElement;
                target.style.backgroundColor = "#fef08a";
                target.style.outline = "2px solid #facc15";
                target.style.scrollMarginTop = "24px";
                target.classList.add("ps-highlight");
              });
              const prefersReducedMotion = window.matchMedia(
                "(prefers-reduced-motion: reduce)"
              ).matches;
              start.scrollIntoView({
                behavior: prefersReducedMotion ? "auto" : "smooth",
                block: "center",
              });
            }
          }
        } catch {
          iframeRef.current.contentWindow.postMessage(
            { type: "scrollTo", anchor: `#${startBlockId}` },
            "*"
          );
        }
      }
    }
  };

  const handleGenerate = () => {
    generateIdeaMap.mutate(paperId);
  };

  return (
    <div className="flex-1 flex flex-col h-screen">
        <div className="flex items-center gap-3 p-4 border-b">
          <Button
            variant="ghost"
            size="sm"
            aria-label="Go back"
            onClick={() => router.back()}
          >
            <ArrowLeft className="size-4" />
          </Button>
          <div className="flex-1 min-w-0">
            <h1 className="text-sm font-semibold truncate">
              {paper?.title || "Loading…"}
            </h1>
            {paper?.authors && (
              <p className="text-xs text-muted-foreground truncate">
                {paper.authors.join(", ")}
              </p>
            )}
          </div>
          {paper?.arxiv_id && (
            <Button
              variant="outline"
              size="sm"
              render={
                <a
                  href={`https://arxiv.org/abs/${paper.arxiv_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                />
              }
            >
              <ExternalLink className="mr-1 size-3" />
              arXiv
            </Button>
          )}
        </div>

        <div className="flex-1 flex overflow-hidden">
          {/* Left: Idea Map */}
          <div className="w-96 border-r flex flex-col">
            <div className="p-3 border-b flex items-center justify-between">
              <h2 className="text-sm font-semibold">Idea Map</h2>
              {!ideaMap && !ideaMapError && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleGenerate}
                  disabled={generateIdeaMap.isPending}
                >
                  <Sparkles className="mr-1 size-3" />
                  Generate
                </Button>
              )}
              {isIdeaMapComplete && !isIdeaMapEmpty && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleGenerate}
                  disabled={generateIdeaMap.isPending}
                >
                  <Sparkles className="mr-1 size-3" />
                  Regenerate
                </Button>
              )}
            </div>

            <ScrollArea className="flex-1">
              <div className="p-3 space-y-2">
                {isIdeaMapLoading && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="size-4 animate-spin" />
                      {ideaMapLoadingLabel}
                    </div>
                    {!shouldRenderIdeaMapClaims &&
                      [1, 2, 3].map((i) => (
                        <Skeleton key={i} className="h-12 w-full" />
                      ))}
                  </div>
                )}

                {isIdeaMapSkipped && (
                  <div className="text-center py-8">
                    <p className="text-sm text-muted-foreground">
                      {ideaMap?.dropped_reason || "Idea map unavailable for this paper."}
                    </p>
                  </div>
                )}

                {ideaMap?.status === "failed" && (
                  <div className="text-center py-8">
                    <p className="text-sm text-destructive">
                      {ideaMap.error || "Failed to generate idea map."}
                    </p>
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-2"
                      onClick={handleGenerate}
                    >
                      Retry
                    </Button>
                  </div>
                )}

                {isIdeaMapEmpty && (
                  <div className="text-center py-8">
                    <p className="text-sm text-muted-foreground">
                      No valid cited claims were generated.
                    </p>
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-2"
                      onClick={handleGenerate}
                      disabled={generateIdeaMap.isPending}
                    >
                      <Sparkles className="mr-1 size-3" />
                      Regenerate
                    </Button>
                  </div>
                )}

                {!ideaMap && ideaMapError && (
                  <div className="text-center py-8">
                    <p className="text-sm text-muted-foreground">
                      No idea map yet.
                    </p>
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-2"
                      onClick={handleGenerate}
                      disabled={generateIdeaMap.isPending}
                    >
                      <Sparkles className="mr-1 size-3" />
                      Generate
                    </Button>
                  </div>
                )}

                {shouldRenderIdeaMapClaims &&
                  ideaMapClaims.map((claim: IdeaMapClaim) => (
                    <div key={claim.id} className="border rounded-lg">
                      <button
                        type="button"
                        className="flex w-full items-start gap-2 p-2 text-left hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        aria-expanded={expandedClaims.has(claim.id)}
                        onClick={() => toggleClaim(claim.id)}
                      >
                        {expandedClaims.has(claim.id) ? (
                          <ChevronDown className="size-4 mt-0.5 shrink-0" />
                        ) : (
                          <ChevronRight className="size-4 mt-0.5 shrink-0" />
                        )}
                        <span className="text-xs font-medium leading-snug flex-1">
                          {claim.text}
                        </span>
                        <Badge
                          variant="secondary"
                          className={`shrink-0 text-xs tabular-nums ${
                            ideaMap?.status === "warrants_running"
                              ? "animate-pulse"
                              : ""
                          }`}
                        >
                          {claim.warrants.length}
                        </Badge>
                      </button>
                      {expandedClaims.has(claim.id) && (
                        <div className="px-2 pb-2 space-y-1">
                          {claim.warrants.length === 0 && isIdeaMapLoading && (
                            <div className="flex items-center gap-2 rounded p-1.5 text-xs text-muted-foreground">
                              <Loader2 className="size-3 animate-spin" />
                              Finding warrants…
                            </div>
                          )}
                          {claim.warrants.map((warrant: IdeaMapWarrant) => (
                            <button
                              key={warrant.id}
                              type="button"
                              className={`w-full rounded p-1.5 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                                highlightedWarrant === warrant.id
                                  ? "bg-yellow-100 border border-yellow-300"
                                  : "hover:bg-muted/50"
                              }`}
                              onClick={() => handleWarrantClick(warrant)}
                            >
                              <p className="leading-snug">{warrant.text}</p>
                              {warrant.citation?.sectionTitle && (
                                <Badge
                                  variant="outline"
                                  className="mt-1 text-xs"
                                >
                                  {warrant.citation.sectionTitle}
                                </Badge>
                              )}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
              </div>
            </ScrollArea>
          </div>

          {/* Right: HTML Viewer */}
          <div className="flex-1 flex flex-col">
            {htmlData?.html ? (
              <iframe
                ref={iframeRef}
                srcDoc={htmlData.html}
                title={paper?.title || "Paper HTML"}
                className="flex-1 w-full border-0"
                sandbox="allow-same-origin"
              />
            ) : htmlData?.source_url ? (
              <div className="flex-1 flex items-center justify-center">
                <div className="text-center space-y-2">
                  <p className="text-sm text-muted-foreground">
                    HTML not cached yet.
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    render={
                      <a
                        href={htmlData.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                      />
                    }
                  >
                    <ExternalLink className="mr-1 size-3" />
                    View on arXiv
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center">
                <p className="text-sm text-muted-foreground">
                  {paper?.abstract || "Loading paper…"}
                </p>
              </div>
            )}
          </div>
        </div>
    </div>
  );
}
