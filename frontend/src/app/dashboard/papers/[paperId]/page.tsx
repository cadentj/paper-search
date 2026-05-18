"use client";

import { useRef, useState, use, type RefObject } from "react";
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
import type { IdeaMap, IdeaMapClaim, IdeaMapWarrant, Paper } from "@/lib/api";

const BLOCK_SELECTOR = "[data-paper-block-id]";
const HIGHLIGHT_STYLE_ID = "ps-highlight-style";
const EMPTY_IDEA_MAP_CLAIMS: IdeaMapClaim[] = [];
const PAPER_SKELETON_KEYS = [
  "paper-idea-map-skeleton-1",
  "paper-idea-map-skeleton-2",
  "paper-idea-map-skeleton-3",
];

function ensureHighlightStyles(doc: Document) {
  if (doc.getElementById(HIGHLIGHT_STYLE_ID)) return;
  const style = doc.createElement("style");
  style.id = HIGHLIGHT_STYLE_ID;
  style.textContent = `
    .ps-highlight {
      background-color: #fef08a;
      outline: 2px solid #facc15;
      scroll-margin-top: 24px;
    }
  `;
  doc.head.appendChild(style);
}

function clearHighlights(doc: Document) {
  doc
    .querySelectorAll(".ps-highlight")
    .forEach((element) => element.classList.remove("ps-highlight"));
}

function findPaperBlock(doc: Document, blockId: string): Element | undefined {
  return Array.from(doc.querySelectorAll(BLOCK_SELECTOR)).find(
    (element) => element.getAttribute("data-paper-block-id") === blockId
  );
}

function PaperHeader({
  paper,
  onBack,
}: {
  paper?: Paper;
  onBack: () => void;
}) {
  const sourceUrl = paper?.source_url || paper?.landing_url ||
    (paper?.arxiv_id ? `https://arxiv.org/abs/${paper.arxiv_id}` : undefined);
  const sourceLabel = paper?.source_type === "lesswrong" ? "LessWrong" : "arXiv";

  return (
    <div className="flex items-center gap-3 p-4 border-b">
      <Button variant="ghost" size="sm" aria-label="Go back" onClick={onBack}>
        <ArrowLeft className="size-4" />
      </Button>
      <div className="flex-1 min-w-0">
        <h1 className="text-sm font-semibold truncate">
          {paper?.title || "Loading…"}
        </h1>
        {/* {paper?.authors && (
          <p className="text-xs text-muted-foreground truncate">
            {paper.authors.join(", ")}
          </p>
        )} */}
      </div>
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
    </div>
  );
}

function IdeaMapPanel({
  supportsIdeaMap,
  ideaMap,
  hasIdeaMapError,
  expandedClaims,
  highlightedWarrant,
  isGenerating,
  onGenerate,
  onToggleClaim,
  onWarrantClick,
}: {
  supportsIdeaMap: boolean;
  ideaMap?: IdeaMap;
  hasIdeaMapError: boolean;
  expandedClaims: Set<string>;
  highlightedWarrant: string | null;
  isGenerating: boolean;
  onGenerate: () => void;
  onToggleClaim: (claimId: string) => void;
  onWarrantClick: (warrant: IdeaMapWarrant) => void;
}) {
  if (!supportsIdeaMap) {
    return (
      <div className="w-96 border-r flex flex-col">
        <div className="p-3 border-b">
          <h2 className="text-sm font-semibold">Idea Map</h2>
        </div>
        <CenteredMessage>
          Idea map unavailable for LessWrong posts.
        </CenteredMessage>
      </div>
    );
  }

  const isLoading =
    ideaMap?.status === "queued" ||
    ideaMap?.status === "running" ||
    ideaMap?.status === "claims_running" ||
    ideaMap?.status === "warrants_running";
  const isComplete = ideaMap?.status === "completed";
  const isEmpty = isComplete && (!ideaMap.claims || ideaMap.claims.length === 0);
  const isSkipped = ideaMap?.status === "skipped";
  const claims = ideaMap?.claims ?? EMPTY_IDEA_MAP_CLAIMS;
  const hasClaims = claims.length > 0;
  const loadingLabel =
    ideaMap?.status === "claims_running"
      ? "Finding core claims…"
      : ideaMap?.status === "warrants_running"
        ? "Finding warrants…"
        : "Generating idea map…";

  return (
    <div className="w-96 border-r flex flex-col">
      <div className="p-3 border-b flex items-center justify-between">
        <h2 className="text-sm font-semibold">Idea Map</h2>
        {!ideaMap && !hasIdeaMapError && (
        <GenerateButton
            label="Generate"
            isGenerating={isGenerating}
            onGenerate={onGenerate}
          />
        )}
        {isComplete && !isEmpty && (
          <GenerateButton
            label="Regenerate"
            isGenerating={isGenerating}
            onGenerate={onGenerate}
          />
        )}
      </div>

      <ScrollArea className="flex-1">
        <div className="p-3 space-y-2">
          {isLoading && (
            <IdeaMapLoading label={loadingLabel} showSkeletons={!hasClaims} />
          )}
          {isSkipped && (
            <CenteredMessage>
              {ideaMap?.dropped_reason || "Idea map unavailable for this paper."}
            </CenteredMessage>
          )}
          {ideaMap?.status === "failed" && (
            <IdeaMapRetry
              message={ideaMap.error || "Failed to generate idea map."}
              onGenerate={onGenerate}
            />
          )}
          {isEmpty && (
            <IdeaMapRetry
              message="No valid cited claims were generated."
              onGenerate={onGenerate}
              label="Regenerate"
              isGenerating={isGenerating}
            />
          )}
          {!ideaMap && hasIdeaMapError && (
            <IdeaMapRetry
              message="No idea map yet."
              onGenerate={onGenerate}
              label="Generate"
              isGenerating={isGenerating}
            />
          )}
          {hasClaims &&
            claims.map((claim) => (
              <IdeaMapClaimCard
                key={claim.id}
                claim={claim}
                isExpanded={expandedClaims.has(claim.id)}
                isLoading={isLoading}
                isWarrantsRunning={ideaMap?.status === "warrants_running"}
                highlightedWarrant={highlightedWarrant}
                onToggleClaim={onToggleClaim}
                onWarrantClick={onWarrantClick}
              />
            ))}
        </div>
      </ScrollArea>
    </div>
  );
}

function GenerateButton({
  label,
  isGenerating,
  onGenerate,
}: {
  label: string;
  isGenerating: boolean;
  onGenerate: () => void;
}) {
  return (
    <Button
      size="sm"
      variant="outline"
      onClick={onGenerate}
      disabled={isGenerating}
    >
      <Sparkles className="mr-1 size-3" />
      {label}
    </Button>
  );
}

function IdeaMapLoading({
  label,
  showSkeletons,
}: {
  label: string;
  showSkeletons: boolean;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        {label}
      </div>
      {showSkeletons &&
        PAPER_SKELETON_KEYS.map((key) => (
          <Skeleton key={key} className="h-12 w-full" />
        ))}
    </div>
  );
}

function CenteredMessage({ children }: { children: string }) {
  return (
    <div className="text-center py-8">
      <p className="text-sm text-muted-foreground">{children}</p>
    </div>
  );
}

function IdeaMapRetry({
  message,
  label = "Retry",
  isGenerating = false,
  onGenerate,
}: {
  message: string;
  label?: string;
  isGenerating?: boolean;
  onGenerate: () => void;
}) {
  return (
    <div className="text-center py-8">
      <p className="text-sm text-muted-foreground">{message}</p>
      <Button
        size="sm"
        variant="outline"
        className="mt-2"
        onClick={onGenerate}
        disabled={isGenerating}
      >
        {label !== "Retry" && <Sparkles className="mr-1 size-3" />}
        {label}
      </Button>
    </div>
  );
}

function IdeaMapClaimCard({
  claim,
  isExpanded,
  isLoading,
  isWarrantsRunning,
  highlightedWarrant,
  onToggleClaim,
  onWarrantClick,
}: {
  claim: IdeaMapClaim;
  isExpanded: boolean;
  isLoading: boolean;
  isWarrantsRunning: boolean;
  highlightedWarrant: string | null;
  onToggleClaim: (claimId: string) => void;
  onWarrantClick: (warrant: IdeaMapWarrant) => void;
}) {
  return (
    <div className="border rounded-lg">
      <button
        type="button"
        className="flex w-full items-start gap-2 p-2 text-left hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-expanded={isExpanded}
        onClick={() => onToggleClaim(claim.id)}
      >
        {isExpanded ? (
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
            isWarrantsRunning ? "animate-pulse" : ""
          }`}
        >
          {claim.warrants.length}
        </Badge>
      </button>
      {isExpanded && (
        <div className="px-2 pb-2 space-y-1">
          {claim.warrants.length === 0 && isLoading && (
            <div className="flex items-center gap-2 rounded p-1.5 text-xs text-muted-foreground">
              <Loader2 className="size-3 animate-spin" />
              Finding warrants…
            </div>
          )}
          {claim.warrants.map((warrant) => (
            <IdeaMapWarrantButton
              key={warrant.id}
              warrant={warrant}
              isHighlighted={highlightedWarrant === warrant.id}
              onWarrantClick={onWarrantClick}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function IdeaMapWarrantButton({
  warrant,
  isHighlighted,
  onWarrantClick,
}: {
  warrant: IdeaMapWarrant;
  isHighlighted: boolean;
  onWarrantClick: (warrant: IdeaMapWarrant) => void;
}) {
  return (
    <button
      type="button"
      className={`w-full rounded p-1.5 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
        isHighlighted ? "bg-yellow-100 border border-yellow-300" : "hover:bg-muted/50"
      }`}
      onClick={() => onWarrantClick(warrant)}
    >
      <p className="leading-snug">{warrant.text}</p>
      {warrant.citation?.sectionTitle && (
        <Badge variant="outline" className="mt-1 text-xs">
          {warrant.citation.sectionTitle}
        </Badge>
      )}
    </button>
  );
}

function PaperHtmlViewer({
  paper,
  htmlData,
  iframeRef,
}: {
  paper?: Paper;
  htmlData?: { html: string | null; source_url: string | null };
  iframeRef: RefObject<HTMLIFrameElement | null>;
}) {
  if (htmlData?.html) {
    return (
      <iframe
        ref={iframeRef}
        srcDoc={htmlData.html}
        title="Paper HTML"
        className="flex-1 w-full border-0"
        sandbox="allow-same-origin"
      />
    );
  }

  if (htmlData?.source_url) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center space-y-2">
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
    <div className="flex-1 flex items-center justify-center">
      <p className="text-sm text-muted-foreground">
        {paper?.abstract || "Loading paper…"}
      </p>
    </div>
  );
}

export default function PaperDetailPage({
  params,
}: {
  params: Promise<{ paperId: string }>;
}) {
  const { paperId } = use(params);
  const { back } = useRouter();
  const { data: paper } = usePaper(paperId);
  const { data: htmlData } = usePaperHtml(paperId);
  const { data: ideaMap, error: ideaMapError } = useIdeaMap(paperId);
  const generateIdeaMap = useGenerateIdeaMap();

  const [expandedClaims, setExpandedClaims] = useState<Set<string>>(new Set());
  const [highlightedWarrant, setHighlightedWarrant] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

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
    if (!iframeRef.current?.contentWindow || !warrant.citation) return;

    const { startBlockId, endBlockId } = warrant.citation;
    if (!startBlockId || !endBlockId) return;

    try {
      const doc = iframeRef.current.contentDocument;
      if (!doc) return;
      ensureHighlightStyles(doc);
      clearHighlights(doc);

      const start = findPaperBlock(doc, startBlockId);
      const end = findPaperBlock(doc, endBlockId);
      if (!start || !end) return;

      const blocks = Array.from(doc.querySelectorAll(BLOCK_SELECTOR));
      const startIndex = blocks.indexOf(start);
      const endIndex = blocks.indexOf(end);
      const highlightedBlocks =
        startIndex >= 0 && endIndex >= startIndex
          ? blocks.slice(startIndex, endIndex + 1)
          : [start];

      highlightedBlocks.forEach((element) =>
        element.classList.add("ps-highlight")
      );

      const prefersReducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
      ).matches;
      start.scrollIntoView({
        behavior: prefersReducedMotion ? "auto" : "smooth",
        block: "center",
      });
    } catch {
      iframeRef.current.contentWindow.postMessage(
        { type: "scrollToBlock", blockId: startBlockId },
        "*"
      );
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen">
      <PaperHeader paper={paper} onBack={back} />
      <div className="flex-1 flex overflow-hidden">
        <IdeaMapPanel
          supportsIdeaMap={paper?.source_type !== "lesswrong"}
          ideaMap={ideaMap}
          hasIdeaMapError={!!ideaMapError}
          expandedClaims={expandedClaims}
          highlightedWarrant={highlightedWarrant}
          isGenerating={generateIdeaMap.isPending}
          onGenerate={() => generateIdeaMap.mutate(paperId)}
          onToggleClaim={toggleClaim}
          onWarrantClick={handleWarrantClick}
        />
        <div className="flex-1 flex flex-col">
          <PaperHtmlViewer
            paper={paper}
            htmlData={htmlData}
            iframeRef={iframeRef}
          />
        </div>
      </div>
    </div>
  );
}
