"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
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

export default function FiltersPage() {
  const { data: allFilters } = useFilters();
  const createFilter = useCreateFilter();
  const archiveFilter = useArchiveFilter();
  const restoreFilter = useRestoreFilter();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [archivedOpen, setArchivedOpen] = useState(false);

  const activeFilters = allFilters?.filter((f) => f.status === "active") || [];
  const archivedFilters =
    allFilters?.filter((f) => f.status === "archived") || [];

  const handleCreate = async () => {
    if (!name.trim() || !description.trim()) return;
    const definition: FilterDefinition = {
      name,
      description,
      mode: "topic",
    };
    await createFilter.mutateAsync({ name, definition });
    setDialogOpen(false);
    setName("");
    setDescription("");
  };

  return (
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
                  <Label htmlFor="filter-name">Name</Label>
                  <Input
                    id="filter-name"
                    name="filter-name"
                    autoComplete="off"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Example: Mechanistic interpretability…"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="filter-description">Description</Label>
                  <Textarea
                    id="filter-description"
                    name="filter-description"
                    autoComplete="off"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="The question, topic, or claim to search for…"
                    rows={4}
                  />
                </div>
                <Button
                  onClick={handleCreate}
                  disabled={
                    !name.trim() ||
                    !description.trim() ||
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
                    <div className="min-w-0 space-y-1">
                      <CardTitle className="text-sm">{f.name}</CardTitle>
                      <p className="text-sm text-muted-foreground">
                        {f.definition?.description}
                      </p>
                    </div>
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
              </Card>
            ))}
          </div>
        )}

        {archivedFilters.length > 0 && (
          <div className="space-y-3">
            <button
              type="button"
              className="flex items-center gap-2 text-lg font-semibold text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setArchivedOpen((open) => !open)}
              aria-expanded={archivedOpen}
            >
              {archivedOpen ? (
                <ChevronDown className="size-4" />
              ) : (
                <ChevronRight className="size-4" />
              )}
              Archived ({archivedFilters.length})
            </button>
            {archivedOpen &&
              archivedFilters.map((f) => (
                <Card key={f.id} className="opacity-60">
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <div className="min-w-0 space-y-1">
                        <CardTitle className="text-sm">{f.name}</CardTitle>
                        <p className="text-sm text-muted-foreground">
                          {f.definition?.description}
                        </p>
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
  );
}
