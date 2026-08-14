# Good Answer -> Fine-Tuning Loop

This document provides a comprehensive overview of the NETTRADES.AI platform architecture.

---

## Good Answer ? Fine?Tuning Loop

```mermaid
graph LR
    Vote[(good_answer_vote)] --> Collector[Data Collector cron]
    Collector --> Exporter[Exporter to JSONL]
    Exporter --> Launcher[Direct LangGraph call]
    Launcher --> NVIDIAdynamoJob[NVIDIA Dynamo Training Job]
    NVIDIAdynamoJob --> Unsloth[Unsloth single GPU] & Axolotl[Axolotl FSDP2 multi?GPU]
    Unsloth & Axolotl --> FineTuned[Fine?tuned model]
    FineTuned --> ProviderModel[llm.provider in Odoo]
    ProviderModel --> Field[(nettrades.field)]