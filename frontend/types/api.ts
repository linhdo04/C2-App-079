export type ApiResponse<T, TMeta = never> = {
  data: T;
} & ([TMeta] extends [never] ? object : { meta: TMeta });

export type CollectionMeta = {
  count: number;
};

export type CursorMeta = CollectionMeta & {
  limit: number;
  has_more: boolean;
  next_cursor: string | null;
};
