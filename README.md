# 0108 · 对话 → 结构化信息提取

本项目实现客服对话的自动化结构化信息提取，支持 **本地 Mock 规则匹配** 和 **真实 LLM 语义提取** 两种模式，满足不同场景下的效率和准确性需求。

---

## 1. Schema 设计思路

为了满足客服主管周报分析需求，设计了以下 12 个核心字段，覆盖用户诉求、处理结果、情绪、效率和关键业务信息：


| 字段名                  | 类型      | 说明                        | 设计理由       |
| -------------------- | ------- | ------------------------- | ---------- |
| `conversation_id`    | string  | 对话唯一标识                    | 便于追溯原始记录   |
| `channel`            | string  | 渠道（在线/电话）                 | 统计不同渠道服务质量 |
| `agent`              | string  | 客服姓名                      | 追踪个人绩效     |
| `user_summary`       | string  | 用户诉求简短概括（≤20字）            | 快速了解问题核心   |
| `main_category`      | enum    | 问题大类（售后/物流/账号/产品咨询/投诉/其他） | 统计各类型问题分布  |
| `sub_category`       | string  | 二级分类（如退款、快递查询）            | 更细粒度分析     |
| `resolution_status`  | enum    | 解决状态（已解决/未解决/部分解决/待跟进）    | 衡量客服处理效果   |
| `user_sentiment`     | enum    | 用户情绪（正面/中性/负面）            | 监控满意度趋势    |
| `escalated_to_human` | boolean | 是否转人工                     | 识别机器人失败场景  |
| `turn_count`         | integer | 对话轮次数                     | 评估沟通效率     |
| `key_entities`       | list    | 关键实体（订单号、手机号、产品名等）        | 便于业务关联查询   |
| `unresolved_reason`  | string  | 未解决原因（若适用）                | 帮助改进服务     |


所有字段均可从对话文本中合理推断，且满足统计和检索需求。

---

## 2. 任务拆解与实现

### 2.1 整体流程

读取 conversations.json → 遍历每条对话 → 选择提取模式（Mock/LLM） → 生成结构化 JSON → 保存结果

### 2.2 两种提取模式


| 模式           | 实现方式                            | 优点                 | 适用场景           |
| ------------ | ------------------------------- | ------------------ | -------------- |
| **Mock（默认）** | 基于关键词规则匹配（如“退款”→“售后”，“谢谢”→“正面”） | 零成本、零延迟、无需网络、无依赖   | 快速验证、离线环境、预算有限 |
| **LLM**      | 调用 DeepSeek API 进行语义理解          | 准确率高、能处理复杂上下文和同义表达 | 生产环境、对准确性要求高   |


### 2.3 边界情况处理策略


| 复杂情况              | 处理策略                                                                                               |
| ----------------- | -------------------------------------------------------------------------------------------------- |
| **多诉求**（用户提多个问题）  | `user_summary` 概括所有诉求，`main_category` 取最主要类别，`key_entities` 提取所有实体，`resolution_status` 根据整体解决情况判定。 |
| **转人工**           | 通过关键词“转人工”或角色切换判断，设置 `escalated_to_human = True`。                                                  |
| **话题切换**          | 以最终解决的主要问题为准，摘要中可提及变化。                                                                             |
| **信息缺失**（未提供订单号等） | `key_entities` 仅提取明确提到的，不补全。                                                                       |
| **用户未明确或放弃**      | 归类为“其他”，`resolution_status` 设为“未解决”，`unresolved_reason` 说明原因。                                      |
| **情绪识别**          | 基于关键词或模型语义判断，默认中性。                                                                                 |


### 2.4 企业级工程特性

- **环境变量管理**：API Key 等敏感信息通过环境变量注入，避免硬编码。
- **日志记录**：使用 `logging` 模块记录关键步骤，便于排障。
- **失败重试**（LLM 模式）：通过 `tenacity` 实现指数退避重试，应对网络波动。
- **本地缓存**（LLM 模式）：已提取的对话缓存至 `extracted_cache.json`，避免重复调用 API，节省成本。
- **优雅降级**（LLM 模式）：LLM 调用失败时自动回退到 Mock 结果，保证任务不中断。
- **速率控制**：LLM 模式下每条对话间隔 0.5 秒，避免触发 API 限流。

---

## 3. 验证准确性

随机从 25 条对话中抽取 5 条（`conv_01`、`conv_05`、`conv_12`、`conv_17`、`conv_23`），人工阅读原始对话内容，与提取结果逐字段比对。


| 对话ID    | 正确字段数 / 总字段数 | 准确率     |
| ------- | ------------ | ------- |
| conv_01 | 12/12        | 100%    |
| conv_05 | 11/12        | 91.7%   |
| conv_12 | 12/12        | 100%    |
| conv_17 | 10/12        | 83.3%   |
| conv_23 | 12/12        | 100%    |
| **平均**  | -            | **95%** |


> **注**：*注：本次采用 Mock 模式（关键词规则）进行评估，未调用真实 LLM API。准确率基于当前规则下的抽检结果计算。若后续接入 LLM，预计可进一步提升，但需要额外的 API 成本和配置。*

---

## 4. 运行方式

### 4.1 环境准备

- **Python 3.6+**（推荐 Anaconda）
- 依赖安装（仅 LLM 模式需要）：
  ```bash
  pip install openai tenacity
  ```

### **4.2 选择模式**

在 `extract.py` 顶部配置 `USE_LLM` 变量：

```
python

USE_LLM = False   # False = Mock模式（默认），True = LLM模式
```

### **4.3 配置 API（仅 LLM 模式）**

- 在 `extract.py` 中填写 `DEEPSEEK_API_KEY`（或通过环境变量 `DEEPSEEK_API_KEY` 设置）。
- 可选配置 `DEEPSEEK_BASE_URL` 和 `MODEL_NAME`（默认使用 DeepSeek）。

### **4.4 执行**

```
bash

python extract.py
```

程序会自动读取 `task2_conversations.json`，处理后生成 `extracted_results.json`。

### **4.5 输出示例**

```
json

{
  "conversation_id": "conv_01",
  "channel": "在线",
  "agent": "小王",
  "user_summary": "蓝牙耳机左耳无声，要求退款",
  "main_category": "售后",
  "sub_category": "退换货",
  "resolution_status": "已解决",
  "user_sentiment": "中性",
  "escalated_to_human": false,
  "turn_count": 5,
  "key_entities": [{"entity": "手机号", "value": "138xxxx5521"}],
  "unresolved_reason": null
}
```

---

## **5. 开发工具与运行截图**

### **5.1 代码概览**

```
![代码概览](code_overview.png)
```

### **5.2 终端运行结果**

```
![终端运行结果](terminal_run.png)
```

### **5.3 提取结果 JSON 示例**

```
![JSON结果示例](result_json.png)
```

### **5.4 项目文件结构**

```
![文件夹结构](folder_structure.png)
```

---

## **6. AI 工具使用情况**

- **Cursor**：作为代码编辑器，辅助编写和调试 Python 脚本。
- **DeepSeek API**：用于 LLM 模式下的语义提取（可选）。
- **Copilot / ChatGPT**：辅助设计 Prompt 和生成代码框架。

---

## **7. 项目文件结构**

```
text

.
├── extract.py                  # 主程序（双模式）
├── task2_conversations.json    # 输入数据（25条对话）
├── extracted_results.json      # 输出结果（自动生成）
├── extracted_cache.json        # LLM 缓存文件（本次未使用，仅在 USE_LLM=True 时生成）
├── README.md                   # 项目说明
├── terminal_run.png            # 终端截图
├── code_overview.png           # 代码截图
├── result_json.png             # 结果截图
└── folder_structure.png        # 文件夹结构
```

---

## **8. 改进方向**

- 支持更多实体类型（如日期、地址）。
- 支持流式处理大文件。
- 引入更精细的情绪分析（逐句情绪）。
- 集成更多 LLM 提供商（如智谱、通义千问）。

---

**作者**：[嘉宇国]  
**日期**：2026-06-16