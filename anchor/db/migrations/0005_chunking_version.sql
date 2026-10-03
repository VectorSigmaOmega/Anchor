ALTER TABLE documents ADD COLUMN IF NOT EXISTS chunking_version TEXT NOT NULL DEFAULT 'legacy-v1';
