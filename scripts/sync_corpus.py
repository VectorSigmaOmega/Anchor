"""Copy the public corpus and indexed passages from OVH for local development.

Only documents, chunks and optional embedding metadata are exported. Chat
sessions, conversations, IP usage and provider credentials are excluded.
"""

import argparse
import subprocess
import tarfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="ovh-vps3", help="SSH alias for the Anchor host")
    parser.add_argument("--output", type=Path, default=Path(".benchmarks/corpus.dump"))
    parser.add_argument("--raw-dir", type=Path, default=Path("corpus/raw"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    profile = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "--", args.host,
         "sudo -u postgres psql -d anchor -Atc \"SELECT to_regclass('public.corpus_embedding_profile')\""],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    command = "sudo -u postgres pg_dump -d anchor --data-only --format=custom --table=public.documents --table=public.chunks"
    if profile:
        command += " --table=public.corpus_embedding_profile"
    temporary = args.output.with_suffix(".partial")
    with temporary.open("wb") as target:
        subprocess.run(["ssh", "-o", "BatchMode=yes", "--", args.host, command], check=True, stdout=target)
    temporary.replace(args.output)
    archive_path = args.output.with_suffix(".raw.tar.gz")
    with archive_path.open("wb") as target:
        subprocess.run(["ssh", "-o", "BatchMode=yes", "--", args.host,
                        "sudo tar -C /var/lib/anchor/corpus/raw -czf - ."], check=True, stdout=target)
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as archive:
        archive.extractall(args.raw_dir, filter="data")
    print(f"Saved public corpus snapshot to {args.output} and source files to {args.raw_dir}.")
    if not profile:
        print("This legacy snapshot uses Gemini Embedding 2 at 768 dimensions. Run migration 0004 after restoring the data.")


if __name__ == "__main__":
    main()
