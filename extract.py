import json
import os
from typing import Dict, List, Any, Optional

# ============================================================
# 配置区
# ============================================================
USE_LLM = False  # True=调用LLM, False=使用本地Mock
DEEPSEEK_API_KEY = "你的DeepSeek-API-Key"  # 从 platform.deepseek.com 获取
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
MODEL_NAME = "deepseek-chat"

# 如果不想把Key写死在代码里，也可以从环境变量读取：
# DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# ============================================================
# Prompt 设计（用于LLM提取所有字段）
# ============================================================
EXTRACTION_PROMPT = """
你是一个专业的客服对话分析专家。请从以下客服对话中提取结构化信息，并以 **严格的 JSON 格式** 输出。

**对话内容**（用户和客服交替发言）：
{dialog_text}

**你需要提取的字段及要求**：
1. `conversation_id`: 对话ID（输入中给出的id）
2. `channel`: 渠道（输入中给出的channel）
3. `agent`: 客服名称（输入中给出的agent）
4. `user_summary`: 用户诉求的简短概括，不超过20个字，必须抓住核心问题。
5. `main_category`: 问题大类，从以下列表中选择一个最合适的：
   - 售后（涉及退换货、退款、维修、质量问题等）
   - 物流（快递、送货、取件、改地址等）
   - 账号（登录、安全、密码、验证等）
   - 产品咨询（产品功能、参数、使用方法、推荐等）
   - 投诉（对服务或产品表达强烈不满，要求投诉）
   - 其他（不属于以上任何类）
6. `sub_category`: 二级分类（自由文本，如“退款”、“换货”、“快递查询”、“优惠券”、“成分咨询”等，若无则留空字符串）
7. `resolution_status`: 解决状态，从以下选择：
   - 已解决（客服明确提供了解决方案并得到用户认可，或问题已处理完成）
   - 未解决（对话结束时问题未解决，或用户未得到满意答复）
   - 部分解决（多个诉求中只解决了一部分）
   - 待跟进（客服承诺后续联系或需等待处理）
8. `user_sentiment`: 用户整体情绪，从“正面”、“中性”、“负面”中选择。
9. `escalated_to_human`: 是否转人工客服（若对话中提到转接、或角色切换，设置为true，否则false）
10. `turn_count`: 对话轮次数（每个“用户→客服”交替计为1轮，例如用户+客服+用户+客服，计2轮）
11. `key_entities`: 列表中每个元素是一个对象，包含`entity`和`value`。实体类型包括：订单号、手机号、产品名、金额、优惠券等。只提取明确提到的，不要编造。
12. `unresolved_reason`: 如果`resolution_status`不是“已解决”，请简要说明原因；若已解决则为null。

**输出格式**：必须是合法的JSON对象，不要有任何额外文字或解释。
请严格按照上述字段输出。
"""

# ============================================================
# LLM 调用函数（使用OpenAI兼容接口）
# ============================================================
def call_llm(prompt: str) -> str:
    import openai
    openai.api_key = DEEPSEEK_API_KEY
    openai.base_url = DEEPSEEK_BASE_URL
    try:
        response = openai.ChatCompletion.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        raise RuntimeError(f"LLM调用失败: {e}")

# ============================================================
# Mock 模式（原有关键词规则）
# ============================================================
def extract_mock(conv: Dict) -> Dict[str, Any]:
    user_text = ""
    for t in conv.get("turns", []):
        if t["role"] == "user":
            user_text += t["content"]
    
    category = "其他"
    sub = ""
    if "退款" in user_text or "退货" in user_text:
        category = "售后"
        sub = "退换货"
    elif "快递" in user_text or "签收" in user_text:
        category = "物流"
        sub = "快递查询"
    elif "投诉" in user_text or "破服务" in user_text:
        category = "投诉"
        sub = "服务投诉"
    elif "功能" in user_text or "怎么" in user_text:
        category = "产品咨询"
        sub = "使用咨询"
    
    sentiment = "中性"
    if "谢谢" in user_text or "好的" in user_text:
        sentiment = "正面"
    elif "投诉" in user_text or "破" in user_text:
        sentiment = "负面"
    
    resolved = "已解决"
    if "算了" in user_text or "不用了" in user_text:
        resolved = "未解决"
    
    return {
        "conversation_id": conv.get("id"),
        "channel": conv.get("channel"),
        "agent": conv.get("agent"),
        "user_summary": user_text[:20] + "..." if len(user_text) > 20 else user_text,
        "main_category": category,
        "sub_category": sub,
        "resolution_status": resolved,
        "user_sentiment": sentiment,
        "escalated_to_human": False,
        "turn_count": len(conv.get("turns", [])),
        "key_entities": [],
        "unresolved_reason": None if resolved == "已解决" else "用户未完成"
    }

# ============================================================
# LLM 提取函数（调用API）
# ============================================================
def extract_llm(conv: Dict) -> Dict[str, Any]:
    # 组装对话文本
    dialog_lines = []
    for turn in conv.get("turns", []):
        role = "用户" if turn["role"] == "user" else "客服"
        dialog_lines.append(f"{role}: {turn['content']}")
    dialog_text = "\n".join(dialog_lines)
    
    # 构建Prompt
    prompt = EXTRACTION_PROMPT.format(dialog_text=dialog_text)
    
    # 调用LLM
    result_text = call_llm(prompt)
    
    # 清理可能的markdown包裹
    if result_text.startswith("```json"):
        result_text = result_text[7:-3]
    elif result_text.startswith("```"):
        result_text = result_text[3:-3]
    
    try:
        parsed = json.loads(result_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM返回的不是有效JSON: {result_text[:200]} ... 错误: {e}")
    
    # 补全可能缺失的字段
    required_fields = ["conversation_id", "channel", "agent", "user_summary", 
                       "main_category", "sub_category", "resolution_status",
                       "user_sentiment", "escalated_to_human", "turn_count",
                       "key_entities", "unresolved_reason"]
    for field in required_fields:
        if field not in parsed:
            parsed[field] = None
    
    # 确保conversation_id正确
    parsed["conversation_id"] = conv.get("id")
    return parsed

# ============================================================
# 主处理函数
# ============================================================
def process_all(conversations: List[Dict], use_llm: bool = USE_LLM) -> List[Dict]:
    results = []
    for idx, conv in enumerate(conversations):
        try:
            if use_llm:
                result = extract_llm(conv)
            else:
                result = extract_mock(conv)
            results.append(result)
            print(f"进度: {idx+1}/{len(conversations)} - {conv.get('id')} 处理完成")
        except Exception as e:
            print(f"处理 {conv.get('id')} 时出错: {e}")
            # 出错时返回一个默认结构
            results.append({
                "conversation_id": conv.get("id"),
                "error": str(e),
                "channel": conv.get("channel"),
                "agent": conv.get("agent"),
                "user_summary": "",
                "main_category": "其他",
                "sub_category": "",
                "resolution_status": "未解决",
                "user_sentiment": "中性",
                "escalated_to_human": False,
                "turn_count": len(conv.get("turns", [])),
                "key_entities": [],
                "unresolved_reason": "解析失败"
            })
    return results

# ============================================================
# 主程序入口
# ============================================================
if __name__ == "__main__":
    # 1. 读取数据
    try:
        with open("task2_conversations.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("错误：找不到 task2_conversations.json 文件！")
        exit(1)
    
    # 2. 执行提取
    extracted = process_all(data, use_llm=USE_LLM)
    
    # 3. 保存结果
    with open("extracted_results.json", "w", encoding="utf-8") as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 完成！共处理 {len(extracted)} 条对话，结果已保存到 extracted_results.json")