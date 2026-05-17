"use client";

import { useState, useEffect, useRef, use } from "react";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
    ideaMap?.status === "queued" || ideaMap?.status === "running";
  const isIdeaMapComplete = ideaMap?.status === "completed";
  const isIdeaMapSkipped = ideaMap?.status === "skipped";

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
      const anchor = warrant.citation.htmlAnchor;
      if (anchor) {
        try {
          const doc = iframeRef.current.contentDocument;
          if (doc) {
            const prevHighlights = doc.querySelectorAll(".ps-highlight");
            prevHighlights.forEach((el) => {
              el.classList.remove("ps-highlight");
              (el as HTMLElement).style.backgroundColor = "";
            });

            const targetId = anchor.replace("#", "");
            const target = doc.getElementById(targetId);
            if (target) {
              target.scrollIntoView({ behavior: "smooth", block: "center" });
              target.style.backgroundColor = "#fef08a";
              target.classList.add("ps-highlight");
            }
          }
        } catch {
          iframeRef.current.contentWindow.postMessage(
            { type: "scrollTo", anchor },
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
    <AppShell>
      <div className="flex-1 flex flex-col h-screen">
        <div className="flex items-center gap-3 p-4 border-b">
          <Button variant="ghost" size="sm" onClick={() => router.back()}>
            <ArrowLeft className="size-4" />
          </Button>
          <div className="flex-1 min-w-0">
            <h1 className="text-sm font-semibold truncate">
              {paper?.title || "Loading..."}
            </h1>
            {paper?.authors && (
              <p className="text-xs text-muted-foreground truncate">
                {paper.authors.join(", ")}
              </p>
            )}
          </div>
          {paper?.arxiv_id && (
            <a
              href={`https://arxiv.org/abs/${paper.arxiv_id}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              <Button variant="outline" size="sm">
                <ExternalLink className="mr-1 size-3" />
                arXiv
              </Button>
            </a>
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
            </div>

            <ScrollArea className="flex-1">
              <div className="p-3 space-y-2">
                {isIdeaMapLoading && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="size-4 animate-spin" />
                      Generating idea map...
                    </div>
                    {[1, 2, 3].map((i) => (
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

                {isIdeaMapComplete &&
                  ideaMap?.claims?.map((claim: IdeaMapClaim) => (
                    <div key={claim.id} className="border rounded-lg">
                      <button
                        className="w-full text-left p-2 flex items-start gap-2 hover:bg-muted/50"
                        onClick={() => toggleClaim(claim.id)}
                      >
                        {expandedClaims.has(claim.id) ? (
                          <ChevronDown className="size-4 mt-0.5 shrink-0" />
                        ) : (
                          <ChevronRight className="size-4 mt-0.5 shrink-0" />
                        )}
                        <span className="text-xs font-medium leading-snug">
                          {claim.text}
                        </span>
                      </button>
                      {expandedClaims.has(claim.id) && (
                        <div className="px-2 pb-2 space-y-1">
                          {claim.warrants.map((warrant: IdeaMapWarrant) => (
                            <button
                              key={warrant.id}
                              className={`w-full text-left rounded p-1.5 text-xs transition-colors ${
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
                className="flex-1 w-full border-0"
                sandbox="allow-same-origin"
              />
            ) : htmlData?.source_url ? (
              <div className="flex-1 flex items-center justify-center">
                <div className="text-center space-y-2">
                  <p className="text-sm text-muted-foreground">
                    HTML not cached yet.
                  </p>
                  <a
                    href={htmlData.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Button variant="outline" size="sm">
                      <ExternalLink className="mr-1 size-3" />
                      View on arXiv
                    </Button>
                  </a>
                </div>
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center">
                <p className="text-sm text-muted-foreground">
                  {paper?.abstract || "Loading paper..."}
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
