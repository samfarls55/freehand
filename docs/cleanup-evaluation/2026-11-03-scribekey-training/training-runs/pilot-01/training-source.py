#!/usr/bin/env python3
"""ScribeKey-only local supervised LoRA training; no remote model code or downloads.

This tool trains on the production specialist prompt and literal protocol. It
never reads a blind evaluation corpus. Adapter weights are the only train-time
checkpoint; merge writes a separate, full BF16 derivative when explicitly asked.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import resource
import shutil
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/Freehand.Cleanup.Evaluation"))
from specialist_literal_protection import SpecialistLiteralMask, PROTOCOL

BOS = "<|startoftext|>"
PREFIX = BOS + "### Input:\n[Styling: semi-casual] [Structure: prose] [Context: general]\n"
SUFFIX = "\n\n### Output:\n"
SOURCE_WEIGHT_SHA = "1a9ab3fcd2384f9c4053f4b55d5e0f40de195487853fdd006b1fa810cd69e16a"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def write_json(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def protected_pair(source: str, target: str) -> tuple[str, str, SpecialistLiteralMask]:
    """Use input-derived tokens on both sides, then prove exact target restoration."""
    mask = SpecialistLiteralMask.create(source)
    masked_target = target
    for ordinal, block in enumerate(mask.legacy.blocks):
        if masked_target.count(block) != 1:
            raise ValueError("Target must retain every exact dictionary block once")
        masked_target = masked_target.replace(block, mask.legacy.token_prefix + str(ordinal) + "_END", 1)
    output = []
    at = 0
    for token, payload in zip(mask.tokens, mask.payloads):
        found = masked_target.find(payload, at)
        if found < 0:
            raise ValueError("Target must retain exact quoted/dictionary payloads in input order")
        output.extend([masked_target[at:found], token])
        at = found + len(payload)
    output.append(masked_target[at:])
    masked_target = "".join(output)
    if mask.restore(masked_target) != target:
        raise ValueError("Literal target round-trip failed")
    return PREFIX + mask.masked_text + SUFFIX, masked_target, mask


def load_data(path: Path):
    rows = []
    ids = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row.get("id"), str) or row["id"] in ids:
            raise ValueError(f"Missing/duplicate id at line {line_number}")
        ids.add(row["id"])
        if not isinstance(row.get("input"), str) or not isinstance(row.get("target"), str):
            raise ValueError(f"Missing input/target at line {line_number}")
        for value in [row["input"], row["target"]]:
            if not value or any(control in value for control in ["<|", "###", "\x00"]):
                raise ValueError(f"Empty/reserved control input at line {line_number}")
        prompt, target, mask = protected_pair(row["input"], row["target"])
        rows.append({**row, "prompt": prompt, "masked_target": target, "literal_count": len(mask.tokens)})
    if not rows:
        raise ValueError("Dataset is empty")
    return rows


def imports(threads: int):
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    import torch
    from safetensors.torch import load_file, save_file
    from transformers import AutoModelForCausalLM, PreTrainedTokenizerFast
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    return torch, load_file, save_file, AutoModelForCausalLM, PreTrainedTokenizerFast


def base_model(base: Path, threads: int):
    torch, load_file, save_file, AutoModel, Tokenizer = imports(threads)
    if sha(base / "model.safetensors") != SOURCE_WEIGHT_SHA:
        raise ValueError("This experiment requires the pinned original ScribeKey v1.1 BF16 weights")
    tokenizer = Tokenizer(tokenizer_file=str(base / "tokenizer.json"), bos_token=BOS,
                          eos_token="<|im_end|>", pad_token="<|pad|>", clean_up_tokenization_spaces=False)
    model, loading = AutoModel.from_pretrained(base, torch_dtype=torch.float32, local_files_only=True,
                                              trust_remote_code=False, attn_implementation="sdpa",
                                              output_loading_info=True)
    if loading["missing_keys"] or loading["unexpected_keys"] or loading["mismatched_keys"]:
        raise ValueError("Checkpoint/model implementation keys do not match: " + repr(loading))
    model.config.use_cache = False
    return torch, load_file, save_file, tokenizer, model


def install_lora(model, torch, rank: int, alpha: float, names=None):
    class LoRALinear(torch.nn.Module):
        def __init__(self, linear):
            super().__init__()
            self.base = linear
            self.lora_A = torch.nn.Parameter(torch.empty(rank, linear.in_features, dtype=torch.float32))
            self.lora_B = torch.nn.Parameter(torch.zeros(linear.out_features, rank, dtype=torch.float32))
            torch.nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))
            self.scaling = alpha / rank

        def forward(self, x):
            base = self.base(x)
            return base + torch.nn.functional.linear(torch.nn.functional.linear(x, self.lora_A), self.lora_B) * self.scaling

    for parameter in model.parameters():
        parameter.requires_grad_(False)
    selected = []
    for name, module in list(model.named_modules()):
        if isinstance(module, torch.nn.Linear) and name.startswith("model.layers.") and (names is None or name in names):
            parent, child = name.rsplit(".", 1)
            setattr(model.get_submodule(parent), child, LoRALinear(module))
            selected.append(name)
    if not selected or (names is not None and set(selected) != set(names)):
        raise ValueError("LoRA targets are absent or disagree with saved adapter")
    return selected


def encode_rows(rows, tokenizer, max_tokens):
    prepared = []
    for row in rows:
        prompt = tokenizer.encode(row["prompt"], add_special_tokens=False)
        target = tokenizer.encode(row["masked_target"], add_special_tokens=False) + [7]
        if prompt.count(1) != 1 or prompt[0] != 1:
            raise ValueError("Production ScribeKey prompt must contain exactly one leading BOS")
        if len(prompt) + len(target) > max_tokens:
            raise ValueError(f"Complete example {row['id']} needs {len(prompt) + len(target)} tokens; cap {max_tokens}. Refusing truncation.")
        prepared.append({**row, "input_ids": prompt + target, "labels": [-100] * len(prompt) + target})
    return prepared


def batch_tensors(rows, torch):
    size = max(len(row["input_ids"]) for row in rows)
    ids = torch.zeros((len(rows), size), dtype=torch.long)
    labels = torch.full((len(rows), size), -100, dtype=torch.long)
    attention = torch.zeros_like(ids)
    for ordinal, row in enumerate(rows):
        length = len(row["input_ids"])
        ids[ordinal, :length] = torch.tensor(row["input_ids"])
        labels[ordinal, :length] = torch.tensor(row["labels"])
        attention[ordinal, :length] = 1
    return ids, labels, attention


def assistant_loss(model, rows, torch):
    ids, labels, attention = batch_tensors(rows, torch)
    hidden = model.model(input_ids=ids, attention_mask=attention, use_cache=False).last_hidden_state
    selected = labels[:, 1:] != -100
    # Avoid allocating vocabulary logits for masked prompt/padding positions.
    logits = model.lm_head(hidden[:, :-1, :][selected])
    targets = labels[:, 1:][selected]
    loss = torch.nn.functional.cross_entropy(logits.float(), targets)
    return loss, int(selected.sum().item())


def adapter_state(model):
    return {key: value.detach().cpu().contiguous() for key, value in model.state_dict().items()
            if key.endswith((".lora_A", ".lora_B"))}


def packages():
    return {name: importlib.metadata.version(name) for name in ["torch", "transformers", "safetensors", "tokenizers"]}


def train(args):
    if args.output.exists():
        raise ValueError("Output must be a fresh directory")
    args.output.mkdir(parents=True)
    raw = load_data(args.train)
    if any(row.get("split") not in (None, "train") for row in raw):
        raise ValueError("Training file contains a non-training split")
    random.seed(args.seed)
    torch, _, save_file, tokenizer, model = base_model(args.base, args.threads)
    torch.manual_seed(args.seed)
    rows = encode_rows(raw, tokenizer, args.max_tokens)
    model.eval()
    with torch.inference_mode():
        before = model(torch.tensor([rows[0]["input_ids"]]), use_cache=False).logits.clone()
    targets = install_lora(model, torch, args.rank, args.alpha)
    with torch.inference_mode():
        after = model(torch.tensor([rows[0]["input_ids"]]), use_cache=False).logits
    if not torch.equal(before, after):
        raise ValueError("Zero-initialized LoRA changed baseline logits")
    del before, after
    resume_sha = None
    if args.resume_adapter:
        old_config = json.loads((args.resume_adapter / "adapter-config.json").read_text())
        if (old_config["base_model_sha256"] != SOURCE_WEIGHT_SHA or old_config["rank"] != args.rank
                or old_config["alpha"] != args.alpha or old_config["target_modules"] != targets):
            raise ValueError("Resume adapter configuration differs from this run")
        from safetensors.torch import load_file
        state = load_file(str(args.resume_adapter / "adapter.safetensors"))
        expected = set(adapter_state(model))
        if set(state) != expected:
            raise ValueError("Resume adapter tensor keys differ")
        parameters = dict(model.named_parameters())
        with torch.no_grad():
            for key, value in state.items():
                parameters[key].copy_(value)
        resume_sha = sha(args.resume_adapter / "adapter.safetensors")
    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    config = {"schema_version": 1, "base_path": str(args.base.resolve()), "base_model_sha256": SOURCE_WEIGHT_SHA,
              "rank": args.rank, "alpha": args.alpha, "scaling": args.alpha / args.rank,
              "target_modules": targets, "seed": args.seed, "train_sha256": sha(args.train),
              "train_rows": len(rows), "trainable_parameters": sum(p.numel() for p in trainable),
              "epochs": args.epochs, "batch_size": args.batch_size, "gradient_accumulation": args.gradient_accumulation,
              "learning_rate": args.learning_rate, "max_tokens": args.max_tokens, "threads": args.threads,
              "dtype": "float32", "packages": packages(), "literal_protocol": PROTOCOL,
              "assistant_only_loss": True, "zero_adapter_exact_logit_identity": True,
              "training_source_sha256": sha(Path(__file__)), "optimizer": "AdamW", "weight_decay": 0,
              "warmup_steps": args.warmup_steps, "checkpoint_every_steps": args.checkpoint_every,
              "resume_adapter_sha256": resume_sha, "resume_optimizer": False,
              "full_examples_truncated": 0, "blind_evaluation_read": False}
    write_json(args.output / "adapter-config.json", config)
    optimizer = torch.optim.AdamW(trainable, lr=args.learning_rate, weight_decay=0)
    total_micro = args.epochs * math.ceil(len(rows) / args.batch_size)
    total_steps = math.ceil(total_micro / args.gradient_accumulation)
    warmup = min(args.warmup_steps, total_steps // 10)
    optimizer.zero_grad(set_to_none=True)
    start = time.monotonic()
    consumed_tokens = micro = step = 0
    step_loss_sum = step_micro_count = 0
    model.train()
    with (args.output / "training-log.jsonl").open("x", encoding="utf-8", buffering=1) as log:
        for epoch in range(args.epochs):
            order = list(range(len(rows)))
            random.Random(args.seed + epoch).shuffle(order)
            # Sort small random buckets to reduce padding, while retaining epoch shuffling.
            bucketed = []
            for at in range(0, len(order), 64):
                bucketed.extend(sorted(order[at:at + 64], key=lambda i: len(rows[i]["input_ids"])))
            for at in range(0, len(bucketed), args.batch_size):
                batch = [rows[i] for i in bucketed[at:at + args.batch_size]]
                loss, tokens = assistant_loss(model, batch, torch)
                if not torch.isfinite(loss):
                    raise ValueError("Non-finite training loss")
                group_size = min(args.gradient_accumulation,
                                 total_micro - (micro // args.gradient_accumulation) * args.gradient_accumulation)
                (loss / group_size).backward()
                step_loss_sum += loss.item()
                step_micro_count += 1
                consumed_tokens += tokens
                micro += 1
                if micro % args.gradient_accumulation == 0 or micro == total_micro:
                    norm = torch.nn.utils.clip_grad_norm_(trainable, 1.0)
                    if not torch.isfinite(norm):
                        raise ValueError("Non-finite gradient norm")
                    step += 1
                    ratio = (step / warmup) if step <= warmup and warmup else max(0.1, (total_steps - step + 1) / max(1, total_steps - warmup))
                    for group in optimizer.param_groups:
                        group["lr"] = args.learning_rate * ratio
                    optimizer.step()
                    optimizer.zero_grad(set_to_none=True)
                    event = {"epoch": epoch + 1, "step": step, "microbatch": micro, "loss": step_loss_sum / step_micro_count,
                             "lr": optimizer.param_groups[0]["lr"], "gradient_norm": norm.item(),
                             "assistant_tokens": consumed_tokens, "seconds": time.monotonic() - start}
                    log.write(json.dumps(event) + "\n")
                    print(json.dumps(event), flush=True)
                    step_loss_sum = step_micro_count = 0
                    if args.checkpoint_every and step % args.checkpoint_every == 0:
                        temporary = args.output / "checkpoint.partial.safetensors"
                        save_file(adapter_state(model), str(temporary), metadata={"base_sha256": SOURCE_WEIGHT_SHA})
                        os.replace(temporary, args.output / "checkpoint.safetensors")
                        temporary_optimizer = args.output / "checkpoint.partial.optimizer.pt"
                        torch.save(optimizer.state_dict(), temporary_optimizer)
                        os.replace(temporary_optimizer, args.output / "checkpoint.optimizer.pt")
                    if args.max_steps and step >= args.max_steps:
                        break
            if args.max_steps and step >= args.max_steps:
                break
    save_file(adapter_state(model), str(args.output / "adapter.safetensors"), metadata={"base_sha256": SOURCE_WEIGHT_SHA})
    torch.save(optimizer.state_dict(), args.output / "optimizer.pt")
    write_json(args.output / "training-result.json", {"steps": step, "microbatches": micro,
               "assistant_tokens": consumed_tokens, "seconds": time.monotonic() - start,
               "adapter_sha256": sha(args.output / "adapter.safetensors"), "completed": True,
               "max_steps_limited": bool(args.max_steps), "whole_app_sla_verified": False})


def merge(args):
    if args.output.exists():
        raise ValueError("Merged output must be fresh")
    args.output.mkdir(parents=True)
    torch, load_file, save_file, _, _ = imports(args.threads)
    config = json.loads((args.adapter / "adapter-config.json").read_text())
    if sha(args.base / "model.safetensors") != config["base_model_sha256"] or config["base_model_sha256"] != SOURCE_WEIGHT_SHA:
        raise ValueError("Adapter base hash mismatch")
    adapters = load_file(str(args.adapter / "adapter.safetensors"))
    base = load_file(str(args.base / "model.safetensors"))
    used = set()
    with torch.no_grad():
        for name in config["target_modules"]:
            a_key, b_key, weight = name + ".lora_A", name + ".lora_B", name + ".weight"
            a, b = adapters[a_key], adapters[b_key]
            if a.shape[0] != config["rank"] or b.shape[1] != config["rank"]:
                raise ValueError("Adapter rank mismatch")
            delta = (b.float() @ a.float()) * config["scaling"]
            if delta.shape != base[weight].shape or not torch.isfinite(delta).all():
                raise ValueError("Adapter shape/value mismatch")
            base[weight] = (base[weight].float() + delta).to(torch.bfloat16).contiguous()
            used.update([a_key, b_key])
    if set(adapters) != used:
        raise ValueError("Unused or missing adapter tensors")
    save_file(base, str(args.output / "model.safetensors"), metadata={"format": "pt"})
    for path in args.base.iterdir():
        if path.is_file() and path.name != "model.safetensors":
            shutil.copyfile(path, args.output / path.name)
    write_json(args.output / "freehand-training-provenance.json", {
        "base_model_sha256": SOURCE_WEIGHT_SHA, "adapter_sha256": sha(args.adapter / "adapter.safetensors"),
        "adapter_config_sha256": sha(args.adapter / "adapter-config.json"),
        "merged_model_sha256": sha(args.output / "model.safetensors"), "dtype": "bfloat16",
        "source_code_sha256": sha(Path(__file__)), "merge_formula": "W + (B @ A) * alpha/rank",
        "tokenizer_and_configuration_changed": False,
        "display_credit": "Derived from ScribeKey Fast by ScribeKey"})
    print(json.dumps({"merged": str(args.output), "weights_sha256": sha(args.output / "model.safetensors")}))


def profile(args):
    """Probe exact known publisher case, zero-adapter identity and CPU backward cost."""
    if args.output.exists():
        raise ValueError("Profile output must be fresh")
    args.output.mkdir(parents=True)
    torch, _, _, tokenizer, model = base_model(args.base, args.threads)
    source = "um can you send the updated agenda before lunch"
    target = "Can you send the updated agenda before lunch?"
    prompt, masked_target, _ = protected_pair(source, target)
    prompt_ids = tokenizer.encode(prompt, add_special_tokens=False)
    assert prompt_ids[0] == 1 and prompt_ids.count(1) == 1
    model.eval()
    inference_start = time.monotonic()
    with torch.inference_mode():
        generated = model.generate(input_ids=torch.tensor([prompt_ids]), max_new_tokens=64,
                                   do_sample=False, use_cache=True, eos_token_id=7, pad_token_id=0)
    result = tokenizer.decode(generated[0, len(prompt_ids):], skip_special_tokens=True,
                              clean_up_tokenization_spaces=False).split("###", 1)[0].strip()
    if result != target:
        write_json(args.output / "profile-failed.json", {"known_source": source, "expected": target,
                   "generated": result, "packages": packages(), "reason": "Original Transformers generation differs from known BF16/native case"})
        raise ValueError("Original checkpoint known-case generation mismatch: " + repr(result))
    row = encode_rows([{"id": "profile-001", "prompt": prompt, "masked_target": masked_target}], tokenizer, 1024)[0]
    with torch.inference_mode():
        before = model(torch.tensor([row["input_ids"]]), use_cache=False).logits.clone()
    torch.manual_seed(42)
    targets = install_lora(model, torch, args.rank, args.alpha)
    with torch.inference_mode():
        after = model(torch.tensor([row["input_ids"]]), use_cache=False).logits
    identical = torch.equal(before, after)
    if not identical:
        raise ValueError("Zero adapter changed baseline logits")
    del before, after
    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=0.0002, weight_decay=0)
    model.train()
    timings = []
    for ordinal in range(args.steps):
        start = time.monotonic()
        optimizer.zero_grad(set_to_none=True)
        loss, tokens = assistant_loss(model, [row], torch)
        loss.backward()
        gradient = torch.nn.utils.clip_grad_norm_(trainable, 1.0)
        optimizer.step()
        event = {"step": ordinal + 1, "seconds": time.monotonic() - start, "assistant_tokens": tokens,
                 "loss": loss.item(), "gradient_norm": gradient.item()}
        timings.append(event)
        print(json.dumps(event), flush=True)
    report = {"packages": packages(), "known_case": {"input": source, "expected": target, "generated": result},
              "zero_adapter_exact_logit_identity": identical, "training_dtype": "float32", "threads": args.threads,
              "target_modules": targets, "trainable_parameters": sum(p.numel() for p in trainable),
              "steps": timings, "max_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
              "profile_only": True, "training_adapter_retained": False}
    write_json(args.output / "profile-result.json", report)
    print(json.dumps(report), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    training = commands.add_parser("train")
    training.add_argument("--base", type=Path, required=True)
    training.add_argument("--train", type=Path, required=True)
    training.add_argument("--output", type=Path, required=True)
    training.add_argument("--threads", type=int, default=4)
    training.add_argument("--seed", type=int, default=42)
    training.add_argument("--rank", type=int, default=8)
    training.add_argument("--alpha", type=float, default=16)
    training.add_argument("--learning-rate", type=float, default=0.0002)
    training.add_argument("--epochs", type=int, default=2)
    training.add_argument("--batch-size", type=int, default=2)
    training.add_argument("--gradient-accumulation", type=int, default=4)
    training.add_argument("--max-tokens", type=int, default=1024)
    training.add_argument("--warmup-steps", type=int, default=50)
    training.add_argument("--max-steps", type=int, default=0)
    training.add_argument("--resume-adapter", type=Path)
    training.add_argument("--checkpoint-every", type=int, default=100)
    training.set_defaults(handler=train)
    merging = commands.add_parser("merge")
    merging.add_argument("--base", type=Path, required=True)
    merging.add_argument("--adapter", type=Path, required=True)
    merging.add_argument("--output", type=Path, required=True)
    merging.add_argument("--threads", type=int, default=4)
    merging.set_defaults(handler=merge)
    profiling = commands.add_parser("profile")
    profiling.add_argument("--base", type=Path, required=True)
    profiling.add_argument("--output", type=Path, required=True)
    profiling.add_argument("--threads", type=int, default=4)
    profiling.add_argument("--rank", type=int, default=8)
    profiling.add_argument("--alpha", type=float, default=16)
    profiling.add_argument("--steps", type=int, default=3)
    profiling.set_defaults(handler=profile)
    args = parser.parse_args(argv)
    if args.threads not in range(1, 9):
        parser.error("threads must be 1..8")
    if args.command == "train" and (not 1 <= args.rank <= 64 or args.alpha <= 0 or args.learning_rate <= 0
            or args.epochs < 1 or args.batch_size < 1 or args.gradient_accumulation < 1 or args.max_steps < 0
            or not 64 <= args.max_tokens <= 1024):
        parser.error("Invalid bounded training options")
    args.handler(args)


if __name__ == "__main__":
    main()
