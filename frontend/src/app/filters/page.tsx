"use client";

import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  useFilters,
  useCreateFilter,
  useArchiveFilter,
  useRestoreFilter,
} from "@/hooks/use-queries";
import { FilterDefinition } from "@/lib/api";
import {
  Plus,
  Archive,
  RotateCcw,
  ChevronDown,
  ChevronRight,
} from "lucide-react";

const TEMPLATES: Record<string, Partial<FilterDefinition>> = {
  claim: {
    search: { instructions: "Search for evidence supporting or refuting this proposition.", outputMode: "warrants" },
  },
  question: {
    search: { instructions: "Search for papers that answer or partially answer this question.", outputMode: "answers" },
  },
  topic: {
    search: { instructions: "Search for papers relevant to this topic.", outputMode: "relevance" },
  },
  blank: {
    search: { instructions: "", outputMode: "relevance" },
  },
};

export default function FiltersPage() {
  const { data: allFilters } = useFilters();
  const createFilter = useCreateFilter();
  const archiveFilter = useArchiveFilter();
  const restoreFilter = useRestoreFilter();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [template, setTemplate] = useState("claim");
  const [name, setName] = useState("");
  const [statement, setStatement] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState(
    TEMPLATES.claim.search?.instructions || ""
  );
  const [outputMode, setOutputMode] = useState<string>(
    TEMPLATES.claim.search?.outputMode || "warrants"
  );
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const activeFilters = allFilters?.filter((f) => f.status === "active") || [];
  const archivedFilters =
    allFilters?.filter((f) => f.status === "archived") || [];

  const handleTemplateChange = (t: string | null) => {
    if (!t) return;
    setTemplate(t);
    const tmpl = TEMPLATES[t];
    if (tmpl.search) {
      setInstructions(tmpl.search.instructions);
      setOutputMode(tmpl.search.outputMode);
    }
  };

  const handleCreate = async () => {
    if (!name.trim() || !statement.trim()) return;
    const definition: FilterDefinition = {
      name,
      statement,
      description: description || undefined,
      search: {
        instructions,
        outputMode: outputMode as "warrants" | "answers" | "relevance",
      },
    };
    await createFilter.mutateAsync({ name, definition });
    setDialogOpen(false);
    setName("");
    setStatement("");
    setDescription("");
    setInstructions(TEMPLATES.claim.search?.instructions || "");
    setOutputMode("warrants");
  };

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <AppShell>
      <div className="flex-1 p-6 space-y-6 max-w-4xl">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold tracking-tight">Filters</h1>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger
              render={
                <Button>
                  <Plus className="mr-2 size-4" />
                  New Filter
                </Button>
              }
            />
            <DialogContent className="max-w-lg">
              <DialogHeader>
                <DialogTitle>Create Filter</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>Template</Label>
                  <Select value={template} onValueChange={handleTemplateChange}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="claim">Claim (warrants)</SelectItem>
                      <SelectItem value="question">
                        Question (answers)
                      </SelectItem>
                      <SelectItem value="topic">
                        Topic (relevance)
                      </SelectItem>
                      <SelectItem value="blank">Blank</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Name</Label>
                  <Input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Filter name"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Statement</Label>
                  <Textarea
                    value={statement}
                    onChange={(e) => setStatement(e.target.value)}
                    placeholder="The proposition, question, or topic"
                    rows={2}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Description (optional)</Label>
                  <Input
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Additional context"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Search Instructions</Label>
                  <Textarea
                    value={instructions}
                    onChange={(e) => setInstructions(e.target.value)}
                    rows={3}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Output Mode</Label>
                  <Select
                    value={outputMode}
                    onValueChange={(v) => { if (v) setOutputMode(v); }}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="warrants">Warrants</SelectItem>
                      <SelectItem value="answers">Answers</SelectItem>
                      <SelectItem value="relevance">Relevance</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <Button
                  onClick={handleCreate}
                  disabled={
                    !name.trim() ||
                    !statement.trim() ||
                    createFilter.isPending
                  }
                  className="w-full"
                >
                  Create Filter
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>

        {activeFilters.length > 0 && (
          <div className="space-y-3">
            <h2 className="text-lg font-semibold">
              Active ({activeFilters.length})
            </h2>
            {activeFilters.map((f) => (
              <Card key={f.id}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <button
                      className="flex items-center gap-2 text-left"
                      onClick={() => toggleExpand(f.id)}
                    >
                      {expandedIds.has(f.id) ? (
                        <ChevronDown className="size-4" />
                      ) : (
                        <ChevronRight className="size-4" />
                      )}
                      <CardTitle className="text-sm">{f.name}</CardTitle>
                      <Badge variant="secondary">
                        {f.definition?.search?.outputMode || "relevance"}
                      </Badge>
                    </button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => archiveFilter.mutate(f.id)}
                    >
                      <Archive className="mr-1 size-3" />
                      Archive
                    </Button>
                  </div>
                </CardHeader>
                {expandedIds.has(f.id) && (
                  <CardContent className="text-sm space-y-2">
                    <p>
                      <span className="font-medium">Statement:</span>{" "}
                      {f.definition?.statement}
                    </p>
                    {f.definition?.description && (
                      <p>
                        <span className="font-medium">Description:</span>{" "}
                        {f.definition.description}
                      </p>
                    )}
                    <p>
                      <span className="font-medium">Instructions:</span>{" "}
                      {f.definition?.search?.instructions}
                    </p>
                  </CardContent>
                )}
              </Card>
            ))}
          </div>
        )}

        {archivedFilters.length > 0 && (
          <div className="space-y-3">
            <h2 className="text-lg font-semibold text-muted-foreground">
              Archived ({archivedFilters.length})
            </h2>
            {archivedFilters.map((f) => (
              <Card key={f.id} className="opacity-60">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CardTitle className="text-sm">{f.name}</CardTitle>
                      <Badge variant="outline">archived</Badge>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => restoreFilter.mutate(f.id)}
                    >
                      <RotateCcw className="mr-1 size-3" />
                      Restore
                    </Button>
                  </div>
                </CardHeader>
              </Card>
            ))}
          </div>
        )}

        {activeFilters.length === 0 && archivedFilters.length === 0 && (
          <Card>
            <CardContent className="pt-6 text-center">
              <p className="text-muted-foreground">
                No filters yet. Create one to start searching for papers.
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </AppShell>
  );
}
