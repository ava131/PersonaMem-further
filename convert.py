#!/usr/bin/env python3
"""PersonaMem-v3 text -> exact-token, round-robin cache workloads.

No model inference, generated answers, or source benchmark scoring is involved.
Lengths apply to the context/question payload BEFORE a serving chat template.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_REPO = "bowen-upenn/PersonaMem-v3"
DEFAULT_TOKENIZER = "Qwen/Qwen3-32B"
APPS = ("chatbot", "ai_studio", "instagram", "facebook", "threads")


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def encode(tokenizer, text):
    return tokenizer.encode(text, add_special_tokens=False)


def decode(tokenizer, ids):
    return tokenizer.decode(ids, skip_special_tokens=False, clean_up_tokenization_spaces=False)


def load_tokenizer(name, revision=None):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(
        name, revision=revision, cache_dir=str(ROOT / ".cache" / "huggingface"),
        trust_remote_code=False, use_fast=True,
    )
    # This is data preparation, not a context-window capability claim.
    tok.model_max_length = 10**12
    return tok


def tokenizer_fingerprint(tok):
    return digest(tok.backend_tokenizer.to_str().encode("utf-8"))


def common_prefix(a, b):
    for index, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return index
    return min(len(a), len(b))


def content_text(value):
    """Read visible content only. Never recursively stringify arbitrary metadata."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(
            str(item["text"]).strip() for item in value
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
    return ""


def event_text(event):
    conversation = event.get("conversation") or event.get("messages")
    if isinstance(conversation, list):
        parts = []
        for message in conversation:
            if not isinstance(message, dict):
                continue
            text = content_text(message.get("content", message.get("text", "")))
            if text:
                parts.append(f"{message.get('role', 'message')}:\n{text}")
        if parts:
            return "\n\n".join(parts)
    parts = []
    content = event.get("content", {})
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, dict):
        for key in ("title", "text", "caption", "media_description", "audio_transcript"):
            value = content_text(content.get(key))
            if value:
                parts.append(value)
    interaction = event.get("interaction_format", {})
    if isinstance(interaction, dict):
        value = content_text(interaction.get("user_message"))
        if value:
            parts.append(value)
    return "\n\n".join(parts)


def read_persona(folder, apps):
    records, sources = [], []
    for app in apps:
        path = folder / f"{app}.json"
        if not path.is_file():
            continue
        raw = path.read_bytes()
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("events", data.get("records", data.get("interactions")))
        if not isinstance(data, list):
            raise ValueError(f"Unsupported event schema in {path}")
        sources.append({"file": str(path.resolve()), "sha256": digest(raw)})
        for index, event in enumerate(data):
            if not isinstance(event, dict):
                raise ValueError(f"Non-object event in {path}, index {index}")
            text = event_text(event)
            if text:
                records.append((float(event.get("source_timestamp", event.get("timestamp", 0))),
                                app, index, text))
    records.sort(key=lambda item: item[:3])
    return "\n\n".join(record[3] for record in records), sources, len(records)


def download(args):
    from huggingface_hub import HfApi, hf_hub_download
    api = HfApi()
    revision = api.dataset_info(args.repo, revision=args.revision).sha
    entries = api.list_repo_tree(args.repo, path_in_repo="backend", repo_type="dataset", revision=revision)
    ids = sorted(entry.path.split("/")[-1] for entry in entries
                 if entry.path.split("/")[-1].isdigit())
    if args.persona_ids:
        requested = args.persona_ids.split(",")
        if len(requested) != len(set(requested)) or not set(requested) <= set(ids):
            raise ValueError("persona IDs must be unique and exist in the dataset")
        ids = requested
    else:
        random.Random(args.seed).shuffle(ids)
        if len(ids) < args.personas:
            raise ValueError(f"Only {len(ids)} personas available; requested {args.personas}")
        ids = ids[:args.personas]
    target = Path(args.data_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    manifest_path = target / "download_manifest.json"
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text())
        if old["revision"] != revision or old["repo"] != args.repo:
            raise ValueError("Existing data uses another revision; use a fresh --data-dir")
    jobs = [f"backend/{pid}/{app}.json" for pid in ids for app in args.apps]

    def fetch(filename):
        path = hf_hub_download(args.repo, filename, repo_type="dataset", revision=revision,
                               local_dir=str(target))
        return {"file": filename, "sha256": digest(Path(path).read_bytes())}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        files = []
        for result in pool.map(fetch, jobs):
            files.append(result)
            print(f"[{len(files)}/{len(jobs)}] {result['file']}", flush=True)
    write_json(manifest_path, {"repo": args.repo, "revision": revision, "persona_ids": ids,
                              "apps": args.apps, "files": files})
    print(f"Downloaded to {target}")


def choose_prefixes(tokenizer, ids, lengths, accepted, max_overlap, attempts, rng):
    """Try source offsets until ALL UTF-8/BPE cuts round-trip exactly.

    Decoding an arbitrary token slice is not necessarily reversible. A successful
    candidate must re-encode exactly, have no broken Unicode, and be an actual
    text and token prefix at every round. No padding/repetition is introduced.
    """
    remaining = len(ids) - lengths[-1]
    if remaining < 0:
        return None
    offsets = list(range(min(remaining + 1, attempts)))
    rng.shuffle(offsets)
    offsets = [0] + [x for x in offsets if x != 0]
    for offset in offsets:
        first = ids[offset:offset + lengths[0]]
        if any(common_prefix(first, previous) > max_overlap for previous in accepted):
            continue
        texts, previous, valid = [], "", True
        for length in lengths:
            expected = ids[offset:offset + length]
            text = decode(tokenizer, expected)
            if "\ufffd" in text or encode(tokenizer, text) != expected or not text.startswith(previous):
                valid = False
                break
            texts.append(text)
            previous = text
        if valid:
            return texts, offset, first
    return None


def dataset_row(fmt, text, request_id):
    if fmt == "gsm8k":
        return {"question": text, "answer": ""}
    return {
        "_id": request_id,
        "domain": "Long-dialogue History Understanding",
        "sub_domain": "PersonaMem-v3 cache replay",
        "difficulty": "easy", "length": "long",
        "question": "", "choice_A": "", "choice_B": "", "choice_C": "", "choice_D": "",
        "answer": "", "context": text,
    }


def build(args, tokenizer=None):
    if not 0 <= args.max_first_prefix_tokens < args.block_size:
        raise ValueError("--max-first-prefix-tokens must be >=0 and < --block-size")
    tok = tokenizer or load_tokenizer(args.tokenizer, args.tokenizer_revision)
    data_dir = Path(args.data_dir).resolve()
    backend = data_dir / "backend" if (data_dir / "backend").is_dir() else data_dir
    folders = sorted(p for p in backend.iterdir() if p.is_dir() and p.name.isdigit())
    if args.persona_ids:
        wanted = args.persona_ids.split(",")
        by_id = {p.name: p for p in folders}
        if len(wanted) != len(set(wanted)) or not set(wanted) <= set(by_id):
            raise ValueError("Invalid or duplicate --persona-ids")
        folders = [by_id[pid] for pid in wanted]
    else:
        random.Random(args.seed).shuffle(folders)
    lengths = [args.initial_tokens + r * args.increment_tokens for r in range(args.rounds)]
    selected, first_ids, skipped = [], [], []
    rng = random.Random(args.seed)
    special_ids = set(getattr(tok, "all_special_ids", []))
    for folder in folders:
        text, source_files, event_count = read_persona(folder, args.apps)
        ids = encode(tok, text)
        # Literal control tokens in source could change serving behavior.
        if special_ids.intersection(ids):
            skipped.append({"persona": folder.name, "reason": "contains special tokens"})
            continue
        result = choose_prefixes(tok, ids, lengths, first_ids,
                                 args.max_first_prefix_tokens, args.offset_attempts, rng)
        if result is None:
            skipped.append({"persona": folder.name, "source_tokens": len(ids),
                            "reason": "too short, overlapping, or no exact reversible boundaries"})
            continue
        texts, offset, first = result
        first_ids.append(first)
        selected.append({"persona": folder.name, "texts": texts, "offset": offset,
                         "source_tokens": len(ids), "event_count": event_count,
                         "source_files": source_files, "text_sha256": digest(text.encode())})
        print(f"Selected {len(selected)}/{args.requests_per_round}: persona {folder.name}, "
              f"source={len(ids)} tokens, offset={offset}", flush=True)
        if len(selected) == args.requests_per_round:
            break
    if len(selected) != args.requests_per_round:
        raise ValueError(f"Only {len(selected)} suitable independent personas; need {args.requests_per_round}. "
                         "Download more personas, add --apps, or reduce the requested lengths. "
                         f"Skipped: {json.dumps(skipped, ensure_ascii=False)}")
    formats = ["longbenchv2", "gsm8k"] if args.format == "both" else [args.format]
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    filenames = [f"{fmt}.jsonl" for fmt in formats] + ["requests.meta.jsonl", "manifest.json"]
    if any((out / name).exists() for name in filenames):
        raise ValueError("Output files already exist; choose a fresh --output-dir")
    largest = max((common_prefix(a, b) for i, a in enumerate(first_ids)
                   for b in first_ids[i + 1:]), default=0)
    with tempfile.TemporaryDirectory(prefix=".build-", dir=out) as tmp:
        temp = Path(tmp)
        handles = {fmt: (temp / f"{fmt}.jsonl").open("w", encoding="utf-8") for fmt in formats}
        try:
            with (temp / "requests.meta.jsonl").open("w", encoding="utf-8") as meta:
                for r in range(args.rounds):
                    for session, source in enumerate(selected):
                        line = r * args.requests_per_round + session + 1
                        request_id = f"pm3-s{session:04d}-r{r + 1:04d}"
                        text = source["texts"][r]
                        for fmt, handle in handles.items():
                            handle.write(json.dumps(dataset_row(fmt, text, request_id), ensure_ascii=False) + "\n")
                        record = {"line": line, "request_id": request_id, "session_id": session,
                                  "persona_id": source["persona"], "round": r + 1,
                                  "payload_tokens": lengths[r],
                                  "previous_line": line - args.requests_per_round if r else None,
                                  "previous_prefix_tokens": lengths[r - 1] if r else 0,
                                  "append_tokens": args.increment_tokens if r else 0,
                                  "payload_sha256": digest(text.encode())}
                        if args.emit_token_ids:
                            record["input_ids"] = encode(tok, text)
                        meta.write(json.dumps(record, ensure_ascii=False) + "\n")
        finally:
            for handle in handles.values():
                handle.close()
        downloaded = data_dir / "download_manifest.json"
        manifest = {
            "purpose": "cache_performance_only", "schema_version": 1,
            "source_repo": DEFAULT_REPO,
            "source_download": json.loads(downloaded.read_text()) if downloaded.exists() else None,
            "tokenizer": args.tokenizer, "tokenizer_revision_requested": args.tokenizer_revision,
            "tokenizer_resolved_commit": getattr(tok, "init_kwargs", {}).get("_commit_hash"),
            "tokenizer_fingerprint_sha256": tokenizer_fingerprint(tok) if hasattr(tok, "backend_tokenizer") else None,
            "rounds": args.rounds, "requests_per_round": args.requests_per_round,
            "initial_tokens": args.initial_tokens, "increment_tokens": args.increment_tokens,
            "tokens_per_round": lengths, "total_requests": args.rounds * args.requests_per_round,
            "order": "round-major, session-minor", "other_requests_between_turns": args.requests_per_round - 1,
            "formats": formats, "seed": args.seed, "apps": args.apps,
            "length_scope": "context in longbenchv2; question in gsm8k; add_special_tokens=False",
            "labels": "empty placeholders; NOT valid original benchmark accuracy tasks",
            "block_size": args.block_size, "max_allowed_first_prefix_tokens": args.max_first_prefix_tokens,
            "max_observed_first_prefix_tokens": largest, "first_round_shared_full_prefix_blocks": largest // args.block_size,
            "serving_template_verified": False,
            "sources": [{k: v for k, v in s.items() if k != "texts"} for s in selected],
            "skipped": skipped,
        }
        write_json(temp / "manifest.json", manifest)
        for name in filenames:
            shutil.move(str(temp / name), str(out / name))
    print(f"Wrote {args.rounds * args.requests_per_round} requests per format to {out}")
    print(f"Max cross-session first-round prefix: {largest} tokens; shared full prefix blocks: {largest // args.block_size}")
    return manifest


def verify(args):
    directory = Path(args.output_dir)
    manifest = json.loads((directory / "manifest.json").read_text())
    name = args.tokenizer or manifest["tokenizer"]
    revision = args.tokenizer_revision or manifest.get("tokenizer_resolved_commit") or manifest.get("tokenizer_revision_requested")
    tok = load_tokenizer(name, revision)
    if tokenizer_fingerprint(tok) != manifest["tokenizer_fingerprint_sha256"]:
        raise ValueError("Tokenizer differs from the one used to build this workload")
    metadata = [json.loads(line) for line in (directory / "requests.meta.jsonl").read_text().splitlines()]
    expected_total = manifest["total_requests"]
    if len(metadata) != expected_total:
        raise ValueError("Metadata row count mismatch")
    n = manifest["requests_per_round"]
    reports = {}
    for fmt in manifest["formats"]:
        prior, first = {}, []
        count, max_first = 0, 0
        with (directory / f"{fmt}.jsonl").open(encoding="utf-8") as f:
            for count, line in enumerate(f, 1):
                if count > expected_total:
                    raise ValueError("Too many data rows")
                row, meta = json.loads(line), metadata[count - 1]
                session, r = (count - 1) % n, (count - 1) // n
                if (meta["line"], meta["session_id"], meta["round"]) != (count, session, r + 1):
                    raise ValueError(f"Invalid schedule at line {count}")
                text = row["question" if fmt == "gsm8k" else "context"]
                ids = encode(tok, text)
                expected = manifest["initial_tokens"] + r * manifest["increment_tokens"]
                if len(ids) != expected or meta["payload_tokens"] != expected or digest(text.encode()) != meta["payload_sha256"]:
                    raise ValueError(f"Length/hash mismatch at line {count}")
                if r:
                    old_text, old_ids = prior[session]
                    if not text.startswith(old_text) or ids[:len(old_ids)] != old_ids:
                        raise ValueError(f"Broken continuation at line {count}")
                else:
                    overlap = max((common_prefix(ids, x) for x in first), default=0)
                    if overlap > manifest["max_allowed_first_prefix_tokens"]:
                        raise ValueError(f"First-round overlap at line {count}")
                    max_first = max(max_first, overlap)
                    first.append(ids)
                if "input_ids" in meta and meta["input_ids"] != ids:
                    raise ValueError(f"Token IDs mismatch at line {count}")
                prior[session] = (text, ids)
        if count != expected_total:
            raise ValueError(f"Expected {expected_total} rows, found {count}")
        reports[fmt] = {"rows": count, "exact_lengths": True, "exact_continuations": True,
                        "max_first_round_shared_prefix_tokens": max_first}
    report = {"passed": True, "length_scope": manifest["length_scope"], "formats": reports}
    write_json(directory / "verification.json", report)
    print(json.dumps(report, indent=2))


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("download", help="Download ready-made source JSON, no LLM calls")
    d.add_argument("--repo", default=DEFAULT_REPO)
    d.add_argument("--revision", default="main")
    d.add_argument("--data-dir", default=str(ROOT / "data"))
    d.add_argument("--personas", type=positive, default=24)
    d.add_argument("--persona-ids", help="Comma-separated exact source IDs")
    d.add_argument("--apps", nargs="+", choices=APPS, default=["chatbot", "ai_studio"])
    d.add_argument("--seed", type=int, default=42)
    d.add_argument("--workers", type=positive, default=4)
    b = sub.add_parser("build", help="Create round-robin exact-token JSONL")
    b.add_argument("--data-dir", default=str(ROOT / "data"))
    b.add_argument("--persona-ids")
    b.add_argument("--apps", nargs="+", choices=APPS, default=["chatbot", "ai_studio"])
    b.add_argument("--tokenizer", default=DEFAULT_TOKENIZER)
    b.add_argument("--tokenizer-revision")
    b.add_argument("--rounds", type=positive, default=3)
    b.add_argument("--requests-per-round", type=positive, default=20)
    b.add_argument("--initial-tokens", type=positive, default=32768)
    b.add_argument("--increment-tokens", type=positive, default=100)
    b.add_argument("--format", choices=["longbenchv2", "gsm8k", "both"], default="both")
    b.add_argument("--output-dir", default=str(ROOT / "generated" / "r3_n20_l32768_d100"))
    b.add_argument("--seed", type=int, default=42)
    b.add_argument("--block-size", type=positive, default=16)
    b.add_argument("--max-first-prefix-tokens", type=int, default=8)
    b.add_argument("--offset-attempts", type=positive, default=1024)
    b.add_argument("--emit-token-ids", action="store_true", help="Include canonical IDs in metadata sidecar")
    v = sub.add_parser("verify", help="Re-tokenize output and validate every request")
    v.add_argument("--output-dir", required=True)
    v.add_argument("--tokenizer", help="Optional local path to the exact same tokenizer")
    v.add_argument("--tokenizer-revision")
    return p


def main():
    args = parser().parse_args()
    try:
        {"download": download, "build": build, "verify": verify}[args.command](args)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
