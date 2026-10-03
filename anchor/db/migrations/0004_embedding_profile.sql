CREATE TABLE IF NOT EXISTS corpus_embedding_profile (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    dimension INTEGER NOT NULL CHECK (dimension > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- All pre-migration Anchor releases indexed Gemini Embedding 2 at 768
-- dimensions. Do not label existing vectors with the newly configured model.
INSERT INTO corpus_embedding_profile (singleton, provider, model, dimension)
SELECT TRUE, 'gemini', 'gemini-embedding-2', 768
WHERE EXISTS (SELECT 1 FROM chunks)
ON CONFLICT (singleton) DO NOTHING;
