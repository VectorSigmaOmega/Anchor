import argparse
import asyncio

from anchor.eval.runner import (
    DATASET_PATH,
    SMOKE_PATH,
    EvalSample,
    FixtureEvalService,
    build_live_eval_service,
    emit_json,
    load_dataset,
    score,
    smoke_passes,
    write_eval_doc,
)


async def run(args: argparse.Namespace) -> int:
    if args.pause < 0:
        raise ValueError("Evaluation pause must be nonnegative")
    dataset_path = SMOKE_PATH if args.smoke else DATASET_PATH
    rows = load_dataset(dataset_path)
    fixture_mode = args.fixture_mode or args.smoke

    service = FixtureEvalService() if fixture_mode else await build_live_eval_service()
    try:
        samples: list[EvalSample] = []
        for index, row in enumerate(rows):
            result = await service.execute(row)
            samples.append(EvalSample(row=row, result=result))
            if not fixture_mode and args.pause and index + 1 < len(rows):
                await asyncio.sleep(args.pause)
        metrics = score(samples)
        if args.write_docs:
            write_eval_doc("smoke" if args.smoke else "full", fixture_mode, metrics)
        print(emit_json(metrics))
        if args.smoke and not smoke_passes(metrics):
            return 1
        return 0
    finally:
        if hasattr(service, "close"):
            await service.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--fixture-mode", action="store_true")
    parser.add_argument("--write-docs", action="store_true")
    parser.add_argument("--pause", "--pause-seconds", type=float, default=6.5, help="Pause between live cases; fixture runs do not pause.")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
