# NSFWTrack Performance Baseline

## Scope

This document records the Phase 2-I1 read-only performance audit completed on
2026-07-10. It is a baseline and issue inventory, not an optimization change.

The audit covers:

- item list pagination, filtering, and sorting
- dashboard / workbench
- stats
- tags, creators, collections, and collection detail
- saved views and activity
- duplicate items and metadata cleanup
- data health
- backup preview / validation
- JSON import dry-run

No production database, default data volume, table, field, index, dependency,
migration, tag, or GitHub Release was changed.

## Reproduce

Run the complete matrix from the repository root:

```bash
.venv/bin/python scripts/profile_queries.py \
  --sizes 100 1000 10000 \
  --output /tmp/nsfwtrack-performance-i1.json
```

The command creates one disposable SQLite database per size, inserts fixture
data, prepares local backup / import payloads, runs each audit through a
`PRAGMA query_only = ON` connection, writes the optional JSON report, and
removes every temporary database. The audit accepts no SQL or table name from
the command line. Generated fixture data is never written to the repository.

The audit records SQL count, unique and repeated SQL fingerprints, elapsed
wall-clock time, `EXPLAIN QUERY PLAN` details, full table scans, boundedness,
and confirmed N+1 matches. Timings are observations from one local run, not
pass / fail thresholds.

## Environment

- WSL2 Linux `6.18.33.2-microsoft-standard-WSL2`, x86_64
- Intel Core i9-12900H
- 15 GiB memory
- Python 3.12.13
- SQLite 3.37.2
- SQLAlchemy 2.0.51
- local disposable SQLite files

## Fixture Shape

| Items | Tags | Creators | Collections | Saved views | Activity rows | Relation rows |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 10 | 5 | 2 | 5 | 100 | 300 |
| 1,000 | 100 | 50 | 20 | 50 | 1,000 | 3,000 |
| 10,000 | 1,000 | 500 | 200 | 500 | 10,000 | 30,000 |

Each item has one tag, creator, collection, state row, and activity row.
Deterministic title and metadata variants produce duplicate candidates without
breaking unique constraints.

## Baseline Results

Each cell is `SQL queries / milliseconds`. Query counts include relationship
loads needed by the corresponding template data.

| Operation | 100 | 1,000 | 10,000 | Full scans at 10k | N+1 |
| --- | ---: | ---: | ---: | ---: | --- |
| Items page | 29 / 27.252 | 41 / 158.918 | 258 / 1,791.543 | 7 | No |
| Filtered / rating-sorted items | 29 / 25.054 | 41 / 149.224 | 258 / 1,828.384 | 6 | No |
| Workbench | 25 / 19.311 | 25 / 18.259 | 25 / 29.688 | 4 | No |
| Stats | 28 / 13.399 | 28 / 14.915 | 28 / 57.885 | 12 | No |
| Tags | 8 / 8.742 | 12 / 76.959 | 85 / 852.061 | 1 | No |
| Creators | 8 / 27.847 | 12 / 49.125 | 84 / 927.002 | 1 | No |
| Collections | 8 / 7.307 | 12 / 72.244 | 84 / 900.360 | 1 | No |
| Collection detail | 70 / 30.428 | 75 / 109.903 | 165 / 937.068 | 1 | **Yes** |
| Saved views | 3 / 0.836 | 3 / 1.115 | 3 / 3.173 | 1 | No |
| Activity | 15 / 10.491 | 15 / 11.904 | 15 / 22.062 | 2 | No |
| Duplicate items | 8 / 8.151 | 13 / 51.991 | 103 / 978.750 | 0 | No |
| Metadata cleanup | 20 / 30.156 | 32 / 206.377 | 249 / 2,796.679 | 2 | No |
| Data health | 15 / 3.701 | 15 / 10.844 | 15 / 133.031 | 4 | No |
| Backup preview / validation | 9 / 3.775 | 9 / 11.499 | 9 / 96.487 | 0 | No |
| JSON import dry-run | 4 / 1.558 | 4 / 7.270 | 4 / 118.232 | 0 | No |

## Confirmed Issues

### P0: Item Page Query Amplification

The item result itself remains paginated to 20 or 50 rows. The complete page,
however, loads every tag, creator, collection, and saved view for its controls.
Because the metadata models use `lazy="selectin"` back-references, loading
those filter options also cascades through related items, states, activity,
tags, creators, and collections.

At 10,000 items the page executed 258 SQL statements. Repeated fingerprints
included 60 state batches, 60 activity batches, and 40 batches each for item
tags, creators, and collections. The default and filtered pages took about
1.79 and 1.83 seconds respectively. This is batched eager-load amplification,
not a classic one-query-per-row N+1.

The default item query also reported `SCAN items` and a temporary B-tree for
`ORDER BY updated_at`, while the rating sort scanned the title index and used
a temporary B-tree.

### P0: Metadata Cleanup Query Amplification

Cleanup intentionally loads all tags, creators, and collections to build
candidate groups. Their `items` relationships then cascade into the same item
relationship graph. At 10,000 items the cleanup audit executed 249 queries and
took about 2.80 seconds. The dominant fingerprints were 60 state batches, 60
activity batches, and 40 batches each for item tags, creators, and collections.

### P1: Collection Detail N+1 And Unbounded Available Items

The collection detail path calls `get_collection` twice and loads every item
not already in the collection for the add-item selector. At 10,000 items it
loaded 50 current items and 9,950 available items.

The audit also confirmed 50 executions of:

```text
SELECT collections ...
FROM collections, item_collections
WHERE ? = item_collections.item_id
  AND collections.id = item_collections.collection_id
```

Those 50 singleton queries match the 50 current collection items, so this path
contains a confirmed N+1. Total query count grew from 70 to 165 and the 10,000
item run took about 0.94 seconds.

### P1: Unpaginated Metadata Lists

The tags, creators, and collections pages load every row. Their model-level
selectin relationships also load related item graphs even though the list
templates do not need them. At the largest fixture:

- tags: 1,000 visible rows, 85 queries, about 0.85 seconds
- creators: 500 visible rows, 84 queries, about 0.93 seconds
- collections: 200 visible rows, 84 queries, about 0.90 seconds

### P1: Duplicate Detection Loads The Full Item Graph

Duplicate detection loads all items and all tag, creator, collection, state,
and activity relationships before grouping titles in Python. Query count grew
from 8 to 103 and the 10,000 item run took about 0.98 seconds. The relationship
queries were batched, so the audit did not classify this as N+1.

### P2: Stats Repeats Full Scans

Stats kept a fixed 28-query count, but its 10,000 item plan contained 12 full
scans. Verified repeated work includes separate 7-day and 30-day counts for
both `created_at` and `updated_at`, followed by another recent activity query
that loads matching timestamps. Status, rating, relation ranking, and missing
summary calculations also scan their source tables. The 10,000 item baseline
was about 58 ms, so this is repeated work rather than a current severe delay.

### P2: Data Health Loads Unbounded Detail Inputs

Data health kept a fixed 15-query count, but it reads all items, states, saved
views, and activity rows into Python and scans all relation tables. The clean
10,000 row fixture took about 133 ms. A damaged database can additionally
produce an unbounded in-memory issue list because every detected issue is
retained for rendering.

### P2: Repeated Settings Reads And Unbounded Saved Views

Page-equivalent audits confirmed two identical `app_settings` reads in the
shared context. Items and workbench perform a third settings read before that
context. The workbench also loads every saved view and only then slices the
first four; it loaded 500 rows in the largest fixture. These did not cause a
large 10,000 item delay by themselves, but they are verified redundant and
unbounded reads.

### P3: Backup And Import Scale Linearly With File Rows

Backup upload JSON is parsed once, but preview and validation then traverse the
same payload separately. The combined path kept a fixed 9 SQL queries and took
about 96 ms for 10,000 items plus 30,000 relation rows.

JSON import dry-run parses once and kept a fixed 4 queries. It loads all local
tag, creator, collection, and item titles, then processes all uploaded rows in
memory. The 10,000 row baseline was about 118 ms. No repeated JSON parse or SQL
N+1 was observed.

## Paths Without A Confirmed Major Issue

- Item result pagination remained effective; relationship access for the
  returned 20 / 50 item rows did not produce one SQL statement per item.
- Workbench recent items and recent activity stayed bounded and kept 25 SQL
  queries across all three sizes.
- Activity stayed bounded to 50 recent views and 50 recent edits, kept 15 SQL
  queries, and took about 22 ms at 10,000 rows. Its ordering plan still scans
  `item_activity` and uses a temporary B-tree.
- Saved views alone kept 3 queries and took about 3 ms at 500 rows, although
  the list remains unpaginated.
- Backup preview / validation and import dry-run showed fixed SQL counts and no
  N+1. Their CPU and memory work still grows with uploaded row count.
- No audit operation wrote data, accepted arbitrary SQL, or used an external
  service.

## I2 Priorities

1. Stop metadata list / filter queries from recursively eager-loading item
   graphs. Use operation-specific loader options or column projections.
2. Remove the collection detail N+1 and paginate or search the available-item
   selector instead of loading all remaining items.
3. Paginate tags, creators, collections, duplicates, and cleanup results, or
   split candidate summary queries from detailed relation loading.
4. Consolidate shared settings reads within one request and apply SQL limits
   before slicing saved views.
5. Consolidate stats aggregates and avoid loading recent timestamp rows when
   SQL aggregation can produce the same seven-day buckets.
6. Add bounded data-health detail pagination while preserving complete summary
   counts.
7. Avoid duplicate backup preview / validation traversal where the same
   validated intermediate representation can be reused safely.

Items 1, 2, 3, 4, 5, 6, and 7 can begin as query / service changes without a
schema migration. They must preserve current behavior and safety tests.

## Suggestions Requiring A Real Schema Migration

The following are recommendations only. They were not implemented in I1 and
must not be added through startup `create_all` or an invented schema version:

- composite item indexes for list ordering, such as `(updated_at, id)` and
  `(created_at, id)`
- activity indexes supporting `(last_viewed_at, id)` and
  `(last_edited_at, id)` ordering
- a collection-first relation index such as
  `item_collections(collection_id, item_id)`
- reviewed indexes for state status / rating filters and stats aggregation

Any accepted index change requires an explicit production migration, a schema
version increase, upgrade dry-run coverage, rollback tests, and a backup-first
upgrade path. Phase 2-I1 intentionally does none of those things.
