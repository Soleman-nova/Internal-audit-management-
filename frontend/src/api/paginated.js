/** Unwrap a DRF page while keeping the server's total.
 *  Plain-array responses (non-paginated @action endpoints) still work:
 *  `count` is the array length and `hasMore` is false.
 *
 *  The app's usual `res.data?.results ?? res.data` idiom throws `count` and
 *  `next` away, so any heading rendering `items.length` silently caps at
 *  PAGE_SIZE. Use this wherever a total reaches the screen. */
export function unwrapPage(data) {
  if (Array.isArray(data)) return { items: data, count: data.length, hasMore: false };
  const items = data?.results ?? [];
  return { items, count: data?.count ?? items.length, hasMore: Boolean(data?.next) };
}

export default unwrapPage;
