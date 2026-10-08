"use client";

import { keepPreviousData, useQuery, type UseQueryOptions } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Page } from "@/lib/api";

type Query = Record<string, string | number | boolean | null | undefined>;

/** GET JSON from the API with TanStack Query caching. */
export function useApi<T>(path: string | null, query?: Query, options?: Omit<UseQueryOptions<T>, "queryKey" | "queryFn">) {
  return useQuery<T>({
    queryKey: [path, query ?? {}],
    queryFn: ({ signal }) => api<T>(path!, { query, signal }),
    enabled: path !== null && (options?.enabled ?? true),
    ...options,
  });
}

/** Paginated list with page/sort/filter state and smooth transitions between pages. */
export function usePagedList<T>(path: string, initial: { sort?: string; pageSize?: number; filters?: Query } = {}) {
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<string | undefined>(initial.sort);
  const [filters, setFiltersState] = useState<Query>(initial.filters ?? {});
  const pageSize = initial.pageSize ?? 25;
  const query = { ...filters, page, page_size: pageSize, sort };
  const result = useQuery<Page<T>>({
    queryKey: [path, query],
    queryFn: ({ signal }) => api<Page<T>>(path, { query, signal }),
    placeholderData: keepPreviousData,
  });
  const setFilters = (next: Query) => {
    setFiltersState(next);
    setPage(1);
  };
  const setFilter = (key: string, value: string | number | boolean | null | undefined) => setFilters({ ...filters, [key]: value });
  return { ...result, page, setPage, sort, setSort, filters, setFilters, setFilter, pageSize };
}
