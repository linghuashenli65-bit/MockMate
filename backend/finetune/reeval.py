"""重评估脚本 — 加载已训练的 LoRA 模型，在验证集上算 loss

用法:
    python -m backend.finetune.reeval
"""
import json, os, sys, time
from pathlib import Path

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from datasets import Dataset
import torch
from transformers import (
    AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
    TrainingArguments, Trainer,
)
from peft import PeftModel

BASE_DIR = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = BASE_DIR / "models" / "qwen-finetuned"
DATA_DIR = BASE_DIR / "backend" / "data" / "training"

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"设备: {device}")

# 1. 加载 LoRA 模型
print(f"\n加载模型: {MODEL_DIR}")
t0 = time.time()

with open(MODEL_DIR / "adapter_config.json") as f:
    base_model_name = json.load(f)["base_model_name_or_path"]

tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, trust_remote_code=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

quant_config = BitsAndBytesConfig(
    load_in_4bit=True, bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True,
)
model = AutoModelForCausalLM.from_pretrained(
    base_model_name, quantization_config=quant_config,
    device_map="auto", trust_remote_code=True, torch_dtype=torch.float16,
)
model = PeftModel.from_pretrained(model, MODEL_DIR)
model.eval()
print(f"  加载耗时: {time.time()-t0:.1f}s")

# 2. 加载验证集
def load_jsonl(path):
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records

val_data = load_jsonl(DATA_DIR / "val.jsonl")
print(f"\n验证集: {len(val_data)} 条")

for i, ex in enumerate(val_data):
    roles = [m["role"] for m in ex["messages"]]
    print(f"  [{i}] roles={roles}")

# 3. Tokenize
assistant_token_ids = tokenizer("<|im_start|>assistant", add_special_tokens=False)["input_ids"]
print(f"\n'<|im_start|>assistant' → {len(assistant_token_ids)} tokens: {assistant_token_ids}")

def format_chat(example):
    text = tokenizer.apply_chat_template(
        example["messages"], tokenize=False, add_generation_prompt=False,
    )
    return {"text": text}

def tokenize_fn(examples):
    tokenized = tokenizer(
        examples["text"], truncation=True, max_length=2048,
        padding="max_length",
    )
    tokenized["labels"] = [[-100] * len(ids) for ids in tokenized["input_ids"]]

    for i in range(len(tokenized["input_ids"])):
        input_ids = tokenized["input_ids"][i]
        start_pos = None
        for j in range(len(input_ids) - len(assistant_token_ids), -1, -1):
            if input_ids[j:j + len(assistant_token_ids)] == assistant_token_ids:
                start_pos = j
                break

        if start_pos is not None:
            print(f"  样本[{i}]: 找到 assistant 位置 {start_pos}/{len(input_ids)}")
            for j in range(start_pos, len(input_ids)):
                if input_ids[j] != tokenizer.pad_token_id:
                    tokenized["labels"][i][j] = input_ids[j]
                else:
                    break
        else:
            print(f"  样本[{i}]: 未找到 assistant 标记! 将全为 -100")

    return tokenized

val_dataset = Dataset.from_list(val_data).map(format_chat)

print("\n验证集文本样例 (前300字符):")
print(val_dataset[0]["text"][:300])

tokenized_val = val_dataset.map(
    tokenize_fn, batched=True,
    remove_columns=["text", "messages", "source_id"] \
        if "source_id" in val_dataset.column_names else ["text", "messages"],
)

# 检查 labels
for i in range(len(tokenized_val)):
    labels = tokenized_val[i]["labels"]
    valid = sum(1 for l in labels if l != -100)
    print(f"  样本[{i}]: labels 有效位置 {valid}/{len(labels)}")

# 4. 跑评估
print(f"\n{'='*50}")
print(f"运行评估...")
print(f"{'='*50}")

training_args = TrainingArguments(
    output_dir=str(MODEL_DIR / "_eval_tmp"),
    per_device_eval_batch_size=1,
    fp16=True,
    report_to="none",
    remove_unused_columns=False,
    dataloader_num_workers=0,
)

trainer = Trainer(
    model=model,
    args=training_args,
    eval_dataset=tokenized_val,
    processing_class=tokenizer,
)

metrics = trainer.evaluate()
print(f"\n评估结果:")
for k, v in metrics.items():
    print(f"  {k}: {v}")
