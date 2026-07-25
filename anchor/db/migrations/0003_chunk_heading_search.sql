UPDATE chunks
SET text_tsv = to_tsvector('english', section_path || ' ' || text);
