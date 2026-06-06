#!/usr/bin/env python3
import os, json, argparse
from unsloth import FastLanguageModel
from datasets import load_dataset
from transformers import TrainingArguments
from unsloth import UnslothTrainer

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model_name', default='deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B')
    parser.add_argument('--dataset_path', required=True, help='JSONL file with field training data')
    parser.add_argument('--output_dir', required=True)
    parser.add_argument('--lora_r', type=int, default=16)
    parser.add_argument('--epochs', type=int, default=3)
    parser.add_argument('--max_seq_length', type=int, default=2048)
    args = parser.parse_args()

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model_name,
        max_seq_length=args.max_seq_length,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        target_modules=["q_proj","k_proj","v_proj","o_proj"],
        lora_alpha=args.lora_r*2,
        use_gradient_checkpointing="unsloth",
    )
    dataset = load_dataset("json", data_files=args.dataset_path, split="train")
    trainer = UnslothTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=TrainingArguments(
            output_dir=args.output_dir,
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            num_train_epochs=args.epochs,
            learning_rate=2e-4,
            fp16=True,
            logging_steps=1,
        ),
    )
    trainer.train()
    model.save_pretrained_merged(args.output_dir + "/merged", tokenizer)
    model.export_gguf(args.output_dir + "/merged", quantize="q4_k_m")

if __name__ == "__main__":
    main()