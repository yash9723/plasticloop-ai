"use client";

import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import type * as React from "react";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useT } from "@/i18n/i18n";
import { cn } from "@/lib/utils";

export interface Column<T> {
  key: string;
  header: React.ReactNode;
  cell: (row: T) => React.ReactNode;
  sortKey?: string;
  className?: string;
  align?: "left" | "right" | "center";
}

const alignClass = { left: "text-left", right: "text-right", center: "text-center" };

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  error,
  onRetry,
  emptyTitle,
  emptyDescription,
  emptyAction,
  onRowClick,
  sort,
  onSortChange,
  caption,
}: {
  columns: Column<T>[];
  rows: T[] | undefined;
  rowKey: (row: T) => string;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyDescription?: React.ReactNode;
  emptyAction?: React.ReactNode;
  onRowClick?: (row: T) => void;
  sort?: string;
  onSortChange?: (sort: string) => void;
  caption?: string;
}) {
  const { t } = useT();
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (!loading && rows && rows.length === 0)
    return <EmptyState title={emptyTitle ?? t("common.noData")} description={emptyDescription} action={emptyAction} />;

  const toggleSort = (key: string) => {
    if (!onSortChange) return;
    onSortChange(sort === key ? `-${key}` : key);
  };

  return (
    <div className="rounded-xl border bg-card shadow-[var(--shadow-card)]">
      <Table>
        {caption && <caption className="sr-only">{caption}</caption>}
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {columns.map((c) => {
              const active = sort === c.sortKey || sort === `-${c.sortKey}`;
              const SortIcon = !active ? ArrowUpDown : sort?.startsWith("-") ? ArrowDown : ArrowUp;
              return (
                <TableHead
                  key={c.key}
                  className={cn(alignClass[c.align ?? "left"], c.className)}
                  aria-sort={active ? (sort?.startsWith("-") ? "descending" : "ascending") : undefined}
                >
                  {c.sortKey && onSortChange ? (
                    <button type="button" onClick={() => toggleSort(c.sortKey!)} className="inline-flex items-center gap-1 uppercase hover:text-foreground">
                      {c.header}
                      <SortIcon className="size-3" aria-hidden />
                    </button>
                  ) : (
                    c.header
                  )}
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading || !rows
            ? Array.from({ length: 6 }).map((_, i) => (
                <TableRow key={`s${i}`}>
                  {columns.map((c) => (
                    <TableCell key={c.key}>
                      <Skeleton className="h-4 w-full max-w-40" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            : rows.map((row) => (
                <TableRow
                  key={rowKey(row)}
                  className={cn(onRowClick && "cursor-pointer")}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  onKeyDown={onRowClick ? (e) => e.key === "Enter" && onRowClick(row) : undefined}
                  tabIndex={onRowClick ? 0 : undefined}
                >
                  {columns.map((c) => (
                    <TableCell key={c.key} className={cn(alignClass[c.align ?? "left"], c.className)}>
                      {c.cell(row)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
        </TableBody>
      </Table>
    </div>
  );
}
