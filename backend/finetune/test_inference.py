"""微调模型推理测试脚本 - MockMate

用法:
    python -m backend.finetune.test_inference           # 交互模式
    python -m backend.finetune.test_inference --quick    # 快速跑预设用例
"""
import json
import time
import argparse
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

# 路径
BASE_DIR = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = BASE_DIR / "models" / "qwen-finetuned"

# 预设测试用例
TEST_CASES = [
    {
        "name": "FastAPI 依赖注入",
        "question": "在FastAPI中，依赖注入（Depends）是如何工作的？请举例说明。",
        "answer": "FastAPI的Depends通过参数类型注解来工作。当我们在路由函数中写 `user: User = Depends(get_current_user)` 时，FastAPI会自动调用 `get_current_user` 函数并把返回值注入到参数中。Depends支持嵌套，一个依赖可以依赖另一个依赖。它还支持yield用于数据库会话的获取和释放，这样在请求结束后自动关闭连接。Depends也可以用于权限校验、缓存等场景。",
    },
    {
        "name": "Python GIL",
        "question": "请解释 Python 的 GIL（全局解释器锁）是什么，以及它对多线程编程的影响。",
        "answer": "GIL是CPython解释器中的一个互斥锁，确保同一时刻只有一个线程执行Python字节码。它简化了内存管理，但限制了多线程的并行性。对CPU密集型任务，多线程无法充分利用多核，应该用多进程或异步。对I/O密集型任务，GIL会在I/O等待时释放，多线程仍然有效。",
    },
    {
        "name": "Docker 网络",
        "question": "Docker 的网络模式有哪些？各自适用于什么场景？",
        "answer": "Docker有bridge、host、none和overlay四种网络模式。bridge是默认模式，容器通过虚拟网桥通信，适合单机多容器。host模式容器直接使用宿主机网络栈，性能最好但隔离性差。none模式容器无网络，用于安全敏感场景。overlay用于跨主机的容器通信，是Swarm和K8s的基础。",
    },
]


def load_model():
    """加载微调后的模型"""
    print(f"加载模型: {MODEL_DIR}")
    t0 = time.time()

    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    # 原始模型路径（从 adapter_config 获取基座模型名）
    with open(MODEL_DIR / "adapter_config.json") as f:
        base_model_name = json.load(f)["base_model_name_or_path"]

    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_DIR,
        trust_remote_code=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        quantization_config=quant_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.float16,
    )

    model = PeftModel.from_pretrained(model, MODEL_DIR)
    model.eval()

    load_time = time.time() - t0
    print(f"  加载完成 ({load_time:.1f}s)")
    return model, tokenizer


def generate_evaluation(model, tokenizer, question, answer):
    """生成面试评估"""
    messages = [
        {
            "role": "system",
            "content": "你是一个专业的技术一面（资深工程师面试官）。你正在面试一位AI应用开发工程师岗位的候选人。请根据候选人的回答，从技术掌握、逻辑思维、思维深度、表达沟通等维度进行评分（1-10分），并给出评语和改进建议。",
        },
        {
            "role": "user",
            "content": f"【面试题】\n{question}\n【回答】\n{answer}",
        },
    ]

    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    t0 = time.time()
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=256,
            temperature=0.1,
            do_sample=True,
            repetition_penalty=1.1,
            pad_token_id=tokenizer.pad_token_id,
        )
    gen_time = time.time() - t0

    response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    return response, gen_time


def run_quick_test(model, tokenizer):
    """快速跑预设用例"""
    print(f"\n{'='*60}")
    print(f"快速测试: {len(TEST_CASES)} 个预设用例")
    print(f"{'='*60}")

    for i, case in enumerate(TEST_CASES, 1):
        print(f"\n--- 用例 {i}/{len(TEST_CASES)}: {case['name']} ---")
        print(f"问题: {case['question'][:50]}...")
        print(f"回答: {case['answer'][:50]}...")

        response, gen_time = generate_evaluation(model, tokenizer, case["question"], case["answer"])

        print(f"\n[生成耗时: {gen_time:.1f}s, {gen_time/len(response)*1000:.0f}ms/字]")
        print(f"\n{response}")

        if i < len(TEST_CASES):
            print(f"\n{'-'*60}")


def run_interactive(model, tokenizer):
    """交互模式"""
    print(f"\n{'='*60}")
    print(f"交互测试模式 - 输入面试题和回答进行评测")
    print(f"输入 'q' 退出")
    print(f"{'='*60}")

    while True:
        print()
        question = input("面试题: ").strip()
        if question.lower() == "q":
            break

        answer = input("回答: ").strip()
        if answer.lower() == "q":
            break

        if not question or not answer:
            print("请输入题目和回答")
            continue

        print("\n生成中...", end=" ", flush=True)
        response, gen_time = generate_evaluation(model, tokenizer, question, answer)

        print(f"[{gen_time:.1f}s]")
        print(f"\n{response}")
        print(f"\n{'-'*60}")


def main():
    parser = argparse.ArgumentParser(description="微调模型推理测试")
    parser.add_argument("--quick", action="store_true", help="快速跑预设用例")
    parser.add_argument("--interactive", action="store_true", help="交互模式")
    args = parser.parse_args()

    if not MODEL_DIR.exists():
        print(f"错误: 找不到模型目录 {MODEL_DIR}")
        print("请先运行训练: python -m backend.finetune.train")
        return

    model, tokenizer = load_model()

    # 默认先跑预设用例，再进入交互模式
    run_quick_test(model, tokenizer)

    if args.interactive or not args.quick:
        run_interactive(model, tokenizer)

    print(f"\n完成。")


if __name__ == "__main__":
    main()
