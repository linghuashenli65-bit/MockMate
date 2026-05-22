"""QLoRA 微调训练脚本 — MockMate

用法:
    python -m backend.finetune.train

流程:
    1. 加载 Qwen3.5-4B (4-bit 量化)
    2. 附加 LoRA 适配器
    3. 加载训练/验证数据
    4. 训练 + 评估
    5. 保存 LoRA 权重

环境变量:
    HF_ENDPOINT: HuggingFace 镜像，默认 https://hf-mirror.com
"""
import argparse
import json
import os
import sys
from pathlib import Path

# HuggingFace 镜像（国内访问加速）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
# CUDA 内存优化
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

# ---------- 依赖 ----------
# 注意: datasets 必须在 torch 之前导入，否则 CUDA 下 segfault
from datasets import Dataset
import torch
import transformers
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

# ── 命令行参数 ──
parser = argparse.ArgumentParser()
parser.add_argument("--epochs", type=int, default=None, help="训练轮数（覆盖配置文件中的默认值）")
parser.add_argument("--lr", type=float, default=None, help="学习率（覆盖配置文件中的默认值）")
parser.add_argument("--incremental", action="store_true", default=None, help="强制增量训练模式")
args = parser.parse_args()

print(f"transformers: {transformers.__version__}")
print(f"torch: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"GPU: {torch.cuda.get_device_name(0)}")

# ---------- 路径 ----------
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "backend" / "data" / "training"
MODEL_DIR = BASE_DIR / "models" / "qwen-finetuned"

# ──────────────────────────────────────────────
# 第1步: 4-bit 量化配置
# ──────────────────────────────────────────────
print("\n=== 1. 配置量化参数 ===")

quant_config = BitsAndBytesConfig(
    load_in_4bit=True,                          # 4-bit 量化
    bnb_4bit_quant_type="nf4",                  # NormalFloat4 (QLoRA 论文推荐)
    bnb_4bit_compute_dtype=torch.float16,       # 计算用 float16
    bnb_4bit_use_double_quant=True,             # 双重量化 (省显存)
)
print(f"  quant_type: nf4")
print(f"  compute_dtype: float16")
print(f"  double_quant: True")

# ──────────────────────────────────────────────
# 第2步: 加载模型和 Tokenizer
# ──────────────────────────────────────────────
print("\n=== 2. 加载 Qwen3.5-4B ===")
print("  (首次下载约 9GB，已缓存则几秒加载)")

model_name = "Qwen/Qwen2.5-3B"

tokenizer = AutoTokenizer.from_pretrained(
    model_name,
    trust_remote_code=True,
    padding_side="right",
)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    model_name,
    quantization_config=quant_config,           # 4-bit 加载
    device_map="auto",                          # 自动分配到 GPU
    trust_remote_code=True,
    torch_dtype=torch.float16,
)

print(f"  模型加载完成")
print(f"  参数总量: {model.num_parameters():,}")

# ──────────────────────────────────────────────
# 第3步: 配置 LoRA（支持增量训练）
# ──────────────────────────────────────────────
print("\n=== 3. 配置 LoRA ===")

# 先准备 k-bit 训练（冻结原权重，启用梯度检查点）
model = prepare_model_for_kbit_training(model)

# 检查是否有已有的 LoRA 权重（增量训练）
incremental = MODEL_DIR.exists() and (MODEL_DIR / "adapter_config.json").exists()
if incremental:
    print(f"  检测到已有 LoRA 权重，加载增量训练: {MODEL_DIR}")
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, MODEL_DIR, is_trainable=True)
    model = model.to("cuda")
    model.train()
else:
    # LoRA 配置（首次训练）
    lora_config = LoraConfig(
        r=8,
        lora_alpha=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)

# 看看训练了多少参数
trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total = sum(p.numel() for p in model.parameters())
print(f"  可训练参数: {trainable:,} ({100 * trainable / total:.3f}%)")
print(f"  总参数:     {total:,}")

# ──────────────────────────────────────────────
# 第4步: 加载数据
# ──────────────────────────────────────────────
print("\n=== 4. 加载训练数据 ===")

def load_jsonl(path):
    """读取 JSONL 文件"""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records

train_data = load_jsonl(DATA_DIR / "train.jsonl")
val_data = load_jsonl(DATA_DIR / "val.jsonl")
print(f"  训练集: {len(train_data)} 条")
print(f"  验证集: {len(val_data)} 条")


def format_chat(example):
    """将 messages 格式转换为模型输入

    使用 Qwen2.5 的 chat_template 将 messages 转成文本。
    然后只对 assistant 部分计算 loss。
    """
    # 将 messages 转成模型输入文本
    text = tokenizer.apply_chat_template(
        example["messages"],
        tokenize=False,                         # 先不 tokenize
        add_generation_prompt=False,
    )
    return {"text": text}


# 转换数据
train_dataset = Dataset.from_list(train_data).map(format_chat)
val_dataset = Dataset.from_list(val_data).map(format_chat)

print("\n数据样例 (前200字):")
print(train_dataset[0]["text"][:200])


def tokenize_function(examples):
    """Tokenize + 构建 labels（只对 assistant 部分计算 loss）

    原理: 找到每个样本中最后一个 "<|im_start|>assistant" 的位置，
    该位置之前（system + user）的 labels 设为 -100（忽略），
    只对 assistant 的回答部分计算 loss。
    """
    # Tokenize
    tokenized = tokenizer(
        examples["text"],
        truncation=True,
        max_length=2048,
        padding="max_length",
    )

    # labels 初始化为全 -100（默认全部忽略）
    tokenized["labels"] = [
        [-100] * len(ids) for ids in tokenized["input_ids"]
    ]

    # 找到每个样本中 assistant 部分的起始位置
    # Qwen2.5 中 <|im_start|> 是单独 token，assistant 是 ASCII 分段
    assistant_token_ids = tokenizer("<|im_start|>assistant", add_special_tokens=False)["input_ids"]

    for i in range(len(tokenized["input_ids"])):
        input_ids = tokenized["input_ids"][i]

        # 从右向左扫描，找最后一个 "<|im_start|>assistant"（避免 system 里也出现这个词）
        start_pos = None
        for j in range(len(input_ids) - len(assistant_token_ids), -1, -1):
            if input_ids[j:j + len(assistant_token_ids)] == assistant_token_ids:
                start_pos = j
                break

        if start_pos is not None:
            for j in range(start_pos, len(input_ids)):
                if input_ids[j] != tokenizer.pad_token_id:
                    tokenized["labels"][i][j] = input_ids[j]
                else:
                    break

    return tokenized


# Tokenize 数据集
print("\nTokenizing...")
tokenized_train = train_dataset.map(
    tokenize_function,
    batched=True,
    remove_columns=["text", "messages", "source_id"],
)
tokenized_val = val_dataset.map(
    tokenize_function,
    batched=True,
    remove_columns=["text", "messages", "source_id"],
)

# ──────────────────────────────────────────────
# 第5步: 设置训练参数
# ──────────────────────────────────────────────
print("\n=== 5. 配置训练参数 ===")

training_args = TrainingArguments(
    output_dir=str(MODEL_DIR),                  # 保存目录
    num_train_epochs=args.epochs or 15,                        # 默认15轮，支持 --epochs 覆盖
    per_device_train_batch_size=1,              # qwen3.5 架构 OOM，只能 batch=1
    per_device_eval_batch_size=1,
    gradient_accumulation_steps=8,              # 有效 batch = 1×8 = 8
    learning_rate=args.lr or 2e-4,                         # LoRA 典型学习率，支持 --lr 覆盖
    warmup_steps=10,                            # 热身步数
    logging_steps=1,                            # 每步都打日志 (数据少)
    eval_strategy="epoch",                     # 每轮评估一次
    save_strategy="epoch",                      # 每轮保存一次
    load_best_model_at_end=True,                # 保存最优的
    metric_for_best_model="eval_loss",
    fp16=True,                                  # 半精度训练
    gradient_checkpointing=True,                # 梯度检查点 (省显存)
    save_total_limit=2,                         # 只保留最近2个 checkpoint
    report_to="none",                           # 不报告到 wandb/tensorboard
    remove_unused_columns=False,
    dataloader_num_workers=0,                   # Windows 需要设为 0
)

print(f"  epochs: {training_args.num_train_epochs}")
print(f"  batch_size: {training_args.per_device_train_batch_size}")
print(f"  gradient_accumulation: {training_args.gradient_accumulation_steps}")
print(f"  effective_batch: {training_args.per_device_train_batch_size * training_args.gradient_accumulation_steps}")
print(f"  warmup_steps: {training_args.warmup_steps}")
print(f"  learning_rate: {training_args.learning_rate}")
print(f"  fp16: {training_args.fp16}")

# ──────────────────────────────────────────────
# 第6步: 开始训练
# ──────────────────────────────────────────────
print("\n=== 6. 开始训练 ===")
print("  (数据少，预计 2-5 分钟)")

trainer = transformers.Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_train,
    eval_dataset=tokenized_val,
    processing_class=tokenizer,
)

trainer.train()

# ──────────────────────────────────────────────
# 第7步: 保存模型
# ──────────────────────────────────────────────
print("\n=== 7. 保存模型 ===")

# 保存 LoRA 适配器权重 (很小，约 8MB)
model.save_pretrained(str(MODEL_DIR))
tokenizer.save_pretrained(str(MODEL_DIR))

print(f"  LoRA 权重已保存到: {MODEL_DIR}")
print(f"  文件列表:")
for f in sorted(MODEL_DIR.glob("*")):
    size = f.stat().st_size / 1024 / 1024
    print(f"    {f.name} ({size:.1f} MB)")

# 打印训练前后的评估对比
print("\n=== 训练完成 ===")
print(f"  最终验证集 loss: {trainer.state.best_metric:.4f}")

# 简单的推理测试
print("\n=== 推理测试 ===")
model.eval()

test_messages = [
    {"role": "system", "content": "你是一个专业的技术一面（资深工程师面试官）。你正在面试一位AI应用开发工程师岗位的候选人。请根据候选人的回答，从技术掌握、逻辑思维、思维深度、表达沟通等维度进行评分（1-10分），并给出评语和改进建议。"},
    {"role": "user", "content": "【面试题】\n在FastAPI中，依赖注入（Depends）是如何工作的？请举例说明。\n【回答】\nFastAPI的Depends通过参数类型注解来工作。当我们在路由函数中写 `user: User = Depends(get_current_user)` 时，FastAPI会自动调用 `get_current_user` 函数并把返回值注入到参数中。Depends支持嵌套，一个依赖可以依赖另一个依赖。它还支持yield用于数据库会话的获取和释放，这样在请求结束后自动关闭连接。Depends也可以用于权限校验、缓存等场景。"},
]
test_prompt = tokenizer.apply_chat_template(test_messages, tokenize=False, add_generation_prompt=True)

inputs = tokenizer(test_prompt, return_tensors="pt").to(model.device)
with torch.no_grad():
    outputs = model.generate(
        **inputs,
        max_new_tokens=512,
        temperature=0.7,
        do_sample=True,
        pad_token_id=tokenizer.pad_token_id,
    )

response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
print(response)
