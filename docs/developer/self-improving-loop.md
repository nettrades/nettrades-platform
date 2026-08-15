## Self Improving Loop (MAPE)

The NETTRADES platform implements a closed-loop self-improving system based on the MAPE (Monitor-Analyze-Plan-Execute) architecture.

### MAPE Loop Diagram

```mermaid
graph TB
    subgraph Monitor["Monitor Phase"]
        GA["Good Answer Votes"]
        ES["Expert Sessions"]
        LI["LangGraph Interactions"]
        ROS["ROS 2 / Robotics"]
        GM["GPU Metrics"]
        GA --> DC1["data.episode"]
        ES --> DC1
        LI --> DC1
        ROS --> DC1
        GM --> DC2["data.metric"]
    end

    subgraph Analyze["Analyze Phase"]
        DC1 --> QE["Quality Evaluation"]
        DC2 --> SE["Success Rate"]
        DC1 --> VE["Volume Evaluation"]
        DC1 --> EE["Edge Case Detection"]
        QE --> T["Trigger Fired?"]
        SE --> T
        VE --> T
        EE --> T
        Manual["Manual Trigger"] --> T
    end

    subgraph Plan["Plan Phase"]
        T -->|Yes| Dataset["Dataset Creation"]
        Dataset --> DJ["Data-Juicer"]
        DJ --> DEITA["DEITA Scoring"]
        DEITA --> Training["Unsloth/Axolotl"]
        Training --> Model["Fine-tuned Model"]
    end

    subgraph Execute["Execute Phase"]
        Model --> Deploy["NVIDIA Dynamo Deployment"]
        Deploy --> A["LangGraph Agents"]
        Deploy --> B["Odoo Assistants"]
        Deploy --> C["ROS 2 / Robotics"]
        A --> Monitor
        B --> Monitor
        C --> Monitor
    end
    
```

### Monitor Phase

The Monitor phase collects data from all platform interactions:

| Source | Data Type | Description |
|------|--------|----------|
| **Good Answer Votes** | `data.episode` | User feedback on AI responses |
| **Expert Sessions** | `data.episode` | Expert-requester interactions |
| **LangGraph Interactions** | `data.episode` |  Agent conversation logs |
| **ROS 2 / Robotics** | `data.episode` | Robotic action data |
| **GPU Metrics** | `data.metric` | GPU utilisation, performance |



### Analyze Phase

The Analyze phase evaluates the collected data:
		

| Step | Output | Criteria |
|------|--------|----------|
| **Quality Evaluation** | Quality score (0-10) | THRESHOLD_QUALITY = 7.0 |
| **Success Rate** | Success percentage | > 80% success |
| **Volume Evaluation** | Episode count | THRESHOLD_EPISODES = 50 |
| **Edge Case Detection** | Novel patterns | LLM-as-Judge identification |



### Plan Phase

The Plan phase creates a fine-tuning dataset:

| Step | Tool | Purpose |
|------|--------|----------|
| **Dataset Creation** | JSONL export | Format training data |
| **Quality Filtering** | Data-Juicer | Remove low-quality examples |
| **DEITA Scoring** | LLM-as-Judge | Score complexity, quality, diversity |
| **Training** | Unsloth/Axolotl | Fine-tune the model |



### Execute Phase

The Execute phase deploys the fine-tuned model:

| Step | Tool | Purpose |
|------|--------|----------|
| **Model Deployment** | NVIDIA Dynamo | Deploy to inference engine |
| **Agent Update** | LangGraph | Update agent models |
| **Odoo Update** | Odoo | Update LLM provider configuration |
| **ROS 2 Update** | ROS 2 | Update robotic models |



### Training Triggers

Training is automatically triggered when:

* `THRESHOLD_EPISODES` ? 50

* `THRESHOLD_QUALITY` ? 7.0

* Manual trigger via Odoo UI