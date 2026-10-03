# Local corpus development

The production corpus can be copied without fetching RBI/SEBI again or paying
for new embeddings. `make corpus-sync` uses the `ovh-vps3` SSH alias and exports
only public documents, chunks, optional embedding metadata, and cached PDFs.
Conversation data, IP usage and credentials are excluded. Copies live in
git-ignored `.benchmarks/` and `corpus/raw/`.

For another host, run:

```bash
python -m scripts.sync_corpus --host YOUR_SSH_ALIAS
```

Create a separate local database, configure `.env`, run `make migrate`, then
restore the data into that empty database:

```bash
pg_restore --dbname="$DATABASE_URL" --data-only --no-owner --exit-on-error .benchmarks/corpus.dump
```

Use a local development database URL. A restore inserts public corpus data;
repeated restores into a populated database will fail on duplicate IDs.

If the snapshot predates embedding metadata, populate the known legacy profile
after restoring it:

```sql
INSERT INTO corpus_embedding_profile (singleton, provider, model, dimension)
SELECT TRUE, 'gemini', 'gemini-embedding-2', 768
WHERE EXISTS (SELECT 1 FROM chunks)
ON CONFLICT (singleton) DO NOTHING;
```

Run `make api-dev` for the backend, and `npm run dev` from `ui/` for the frontend.
Next.js proxies `/chat-api/*` to port 8000 during development. Set
`ANCHOR_DEV_API_URL` when the backend uses a different address. The production
build retains static export compatibility.

Run `make benchmark` to test real providers against the copied corpus. The
report `.benchmarks/answer-eval.json` includes answers, citations, retrieved
passages and explicit expected facts. Requests are paced eight seconds apart
to respect the observed Cohere trial quota. Timing and grading are independent:
the report does not count waiting between questions as query latency.

This workspace has a populated database at `127.0.0.1:55432/anchor_dev` and a
user-owned PostgreSQL installation under `.benchmarks/pg-local/`. It can be
started without Docker or sudo:

```bash
.benchmarks/pg-local/root/usr/lib/postgresql/16/bin/pg_ctl \
  -D .benchmarks/pg-local/data -l .benchmarks/pg-local/postgres.log \
  -o "-p 55432 -h 127.0.0.1 -k $(pwd)/.benchmarks/pg-local/socket" start
```
