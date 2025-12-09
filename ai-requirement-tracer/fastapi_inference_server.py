#!/usr/bin/env python3
"""
FastAPI Inference Server
FastAPI推理服务 - 大语言模型推理API服务

文件功能：
- 加载和运行GGUF格式的大语言模型
- 提供/generate接口进行文本生成
- 支持模型量化和GPU加速
- 提供健康检查和API文档
- 专为AutoDL服务器环境优化
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
import json
import logging
import os

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SU模型推理服务",
    description="基于FastAPI的大语言模型推理服务",
    version="1.0.0"
)

# 请求模型
class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: Optional[int] = 2000
    temperature: Optional[float] = 0.1
    top_p: Optional[float] = 0.8
    model: Optional[str] = "su-model"

# 响应模型
class GenerateResponse(BaseModel):
    response: str
    model: str
    tokens_used: int

# 全局模型实例
model = None
tokenizer = None
model_name = "su-model"

def load_model():
    """加载Safetensors格式模型"""
    global model, tokenizer, model_name
    
    try:
        # 模型配置
        model_path = "/root/autodl-tmp/models/su-model/"  # 模型目录路径
        
        logger.info(f"正在加载Safetensors模型: {model_path}")
        
        # 检查模型目录是否存在
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"模型目录不存在: {model_path}")
        
        # 检查是否有safetensors文件
        safetensors_files = [f for f in os.listdir(model_path) if f.endswith('.safetensors')]
        if not safetensors_files:
            raise FileNotFoundError(f"在 {model_path} 中未找到safetensors文件")
        
        logger.info(f"找到safetensors文件: {safetensors_files}")
        
        # 配置量化（可选）
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )
        
        # 加载tokenizer
        tokenizer = AutoTokenizer.from_pretrained(
            model_path,
            trust_remote_code=True
        )
        
        # 如果没有pad_token，设置为eos_token
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        
        # 加载模型 - Safetensors格式
        logger.info("正在加载模型...")
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            trust_remote_code=True,
            device_map="auto",
            quantization_config=quantization_config,
            torch_dtype=torch.float16
        )
        
        logger.info("✅ 模型加载成功")
        return True
        
    except Exception as e:
        logger.error(f"❌ 模型加载失败: {e}")
        return False

def generate_text(prompt: str, max_tokens: int = 2000, temperature: float = 0.1, top_p: float = 0.8) -> str:
    """生成文本"""
    global model, tokenizer
    
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="模型未加载")
    
    try:
        # 编码输入
        inputs = tokenizer(prompt, return_tensors="pt", padding=True, truncation=True)
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
        
        # 生成参数
        generate_kwargs = {
            "max_new_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "do_sample": True,
            "pad_token_id": tokenizer.eos_token_id,
            "eos_token_id": tokenizer.eos_token_id,
        }
        
        # 生成文本
        with torch.no_grad():
            outputs = model.generate(**inputs, **generate_kwargs)
        
        # 解码输出
        input_length = inputs["input_ids"].shape[1]
        generated_tokens = outputs[0][input_length:]
        response = tokenizer.decode(generated_tokens, skip_special_tokens=True)
        
        return response.strip()
        
    except Exception as e:
        logger.error(f"生成失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")

def generate_structured_analysis(prompt: str, max_tokens: int = 2000, temperature: float = 0.1, top_p: float = 0.8) -> dict:
    """生成结构化的需求分析JSON响应 - 纯大模型分析

    说明：此函数不会进行本地规则推理，只负责：
    1) 以清晰的JSON规范向大模型发问；
    2) 解析返回；
    3) 当个别字段缺失时，做最小化的数据填充与格式整理（非推理），
       例如把已有条目映射为图节点/连线，确保前端可视化正常工作。
    """
    global model, tokenizer
    
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="模型未加载")
    
    try:
        # 构建专门的需求分析提示词
        structured_prompt = f"""
你是一个专业的需求分析专家。请分析以下需求，并严格按照JSON格式返回分析结果，不要添加任何其他文字：

需求内容：{prompt}

请返回如下字段的标准JSON（必须是有效JSON）：
{{
  "summary": "一句话总结当前需求",
  "requirement_text": "原始需求文本",
  "current_requirement": {{"name": "当前需求类型名称", "level": 3, "text": "简述"}},
  "upward_trace": [{{"name": "上级需求名称", "level": 4, "text": "简述"}}],
  "downward_trace": [{{"name": "下级需求名称", "level": 2, "text": "简述", "priority": "high|medium|low"}}],
  "trace_network": {{
    "nodes": [
      {{"id": "current", "name": "当前需求", "text": "简述", "level": 3, "is_current": true}}
    ],
    "links": [
      {{"source": "up_1", "target": "current", "type": "derives_from", "label": "来源于"}},
      {{"source": "current", "target": "down_1", "type": "breaks_down_into", "label": "分解为"}}
    ]
  }},
  "complexity": "低|中|高",
  "keywords": ["关键词1", "关键词2"],
  "dependencies": [{{"from": "依赖源", "to": "依赖目标", "type": "依赖类型"}}],
  "suggestions": ["建议1", "建议2"],
  "ai_insights": "详细的AI分析洞察",
  "analysis_method": "AI智能分析",
  "confidence": 0.9
}}

严格要求：
- 仅输出JSON，不要任何多余说明或代码块标记；
- upward_trace 至少 2 项，downward_trace 至少 3 项；
- 为 upward/downward 生成对应的 trace_network 节点与连线：
  - 上级：节点 id 使用 up_1、up_2…，连线 {source: up_i, target: "current", type: "derives_from"}
  - 下级：节点 id 使用 down_1、down_2…，连线 {source: "current", target: down_i, type: "breaks_down_into"}
- level 建议范围：战略/业务目标 5-4，功能/特性 3-2，用户故事/任务 2-1；
- id需唯一；数组长度适中（每类3-6项）。
"""
        
        # 编码输入
        inputs = tokenizer(structured_prompt, return_tensors="pt", padding=True, truncation=True)
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
        
        # 生成参数 - 降低随机性以获得更一致的JSON格式
        generate_kwargs = {
            "max_new_tokens": max_tokens,
            "temperature": 0.1,  # 更低的温度
            "top_p": 0.8,
            "do_sample": True,
            "pad_token_id": tokenizer.eos_token_id,
            "eos_token_id": tokenizer.eos_token_id,
        }
        
        # 生成文本
        with torch.no_grad():
            outputs = model.generate(**inputs, **generate_kwargs)
        
        # 解码输出
        input_length = inputs["input_ids"].shape[1]
        generated_tokens = outputs[0][input_length:]
        response = tokenizer.decode(generated_tokens, skip_special_tokens=True)
        
        # 解析JSON响应
        try:
            import json
            import re
            
            # 清理响应文本
            cleaned_response = response.strip()
            
            # 尝试提取JSON部分
            json_match = re.search(r'\{.*?\}', cleaned_response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                analysis_result = json.loads(json_str)
                
                # 确保包含核心字段（若缺失则进行最小化填充）
                required_fields = [
                    "summary", "requirement_text", "current_requirement",
                    "upward_trace", "downward_trace", "trace_network",
                    "complexity", "keywords", "dependencies", "suggestions",
                    "ai_insights", "analysis_method", "confidence"
                ]
                for field in required_fields:
                    if field not in analysis_result:
                        if field == "summary":
                            analysis_result[field] = "AI分析完成"
                        elif field == "requirement_text":
                            analysis_result[field] = prompt
                        elif field == "current_requirement":
                            analysis_result[field] = {"name": "当前需求", "level": 3, "text": prompt[:60]}
                        elif field == "upward_trace":
                            analysis_result[field] = []
                        elif field == "downward_trace":
                            analysis_result[field] = []
                        elif field == "trace_network":
                            analysis_result[field] = {"nodes": [], "links": []}
                        elif field == "complexity":
                            analysis_result[field] = "中"
                        elif field in ["keywords", "dependencies", "suggestions"]:
                            analysis_result[field] = []
                        elif field == "ai_insights":
                            analysis_result[field] = "AI分析完成"
                        elif field == "analysis_method":
                            analysis_result[field] = "AI智能分析"
                        elif field == "confidence":
                            analysis_result[field] = 0.8
                
                # 若缺少trace_network但有基本条目，则按最小规则构建节点/连线（仅数据整形，无推理）
                try:
                    tn = analysis_result.get("trace_network") or {"nodes": [], "links": []}
                    nodes = tn.get("nodes") or []
                    links = tn.get("links") or []

                    # 是否已有current节点
                    if not any(str(n.get("id")) == "current" for n in nodes):
                        nodes.append({
                            "id": "current",
                            "name": analysis_result.get("current_requirement", {}).get("name", "当前需求"),
                            "text": analysis_result.get("current_requirement", {}).get("text", ""),
                            "level": analysis_result.get("current_requirement", {}).get("level", 3),
                            "is_current": True
                        })

                    # 补充上级/下级为节点与连线
                    for idx, up in enumerate(analysis_result.get("upward_trace", [])[:6]):
                        node_id = f"up_{idx+1}"
                        if not any(str(n.get("id")) == node_id for n in nodes):
                            nodes.append({
                                "id": node_id,
                                "name": up.get("name", "上级需求"),
                                "text": up.get("text", ""),
                                "level": up.get("level", 4)
                            })
                        links.append({
                            "source": node_id,
                            "target": "current",
                            "type": "derives_from",
                            "label": "来源于"
                        })

                    for idx, down in enumerate(analysis_result.get("downward_trace", [])[:6]):
                        node_id = f"down_{idx+1}"
                        if not any(str(n.get("id")) == node_id for n in nodes):
                            nodes.append({
                                "id": node_id,
                                "name": down.get("name", "下级需求"),
                                "text": down.get("text", ""),
                                "level": down.get("level", 2)
                            })
                        links.append({
                            "source": "current",
                            "target": node_id,
                            "type": "breaks_down_into",
                            "label": "分解为"
                        })

                    analysis_result["trace_network"] = {"nodes": nodes, "links": links}
                except Exception as _:
                    # 如果整形失败也不影响主流程
                    pass

                return analysis_result
            else:
                # 如果无法提取JSON，返回最小可视化结构（非推理，仅格式补全）
                current_node = {
                    "id": "current",
                    "name": "当前需求",
                    "text": prompt[:60],
                    "level": 3,
                    "is_current": True
                }
                return {
                    "summary": "AI分析完成",
                    "requirement_text": prompt,
                    "current_requirement": {"name": "当前需求", "level": 3, "text": prompt[:60]},
                    "upward_trace": [],
                    "downward_trace": [],
                    "trace_network": {"nodes": [current_node], "links": []},
                    "complexity": "中",
                    "keywords": ["需求分析"],
                    "dependencies": [],
                    "suggestions": ["建议进行详细分析"],
                    "ai_insights": cleaned_response[:500] if cleaned_response else "分析完成",
                    "analysis_method": "AI智能分析",
                    "confidence": 0.7
                }
                
        except json.JSONDecodeError as je:
            logger.error(f"JSON解析失败: {je}, 原始响应: {response[:200]}")
            # JSON解析失败，返回最小可视化结构（非推理，仅格式补全）
            current_node = {
                "id": "current",
                "name": "当前需求",
                "text": prompt[:60],
                "level": 3,
                "is_current": True
            }
            return {
                "summary": "AI分析完成",
                "requirement_text": prompt,
                "current_requirement": {"name": "当前需求", "level": 3, "text": prompt[:60]},
                "upward_trace": [],
                "downward_trace": [],
                "trace_network": {"nodes": [current_node], "links": []},
                "complexity": "中",
                "keywords": ["需求分析"],
                "dependencies": [],
                "suggestions": ["建议进行详细分析"],
                "ai_insights": response[:500] if response else "分析完成",
                "analysis_method": "AI智能分析",
                "confidence": 0.6
            }
        
    except Exception as e:
        logger.error(f"结构化分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"结构化分析失败: {str(e)}")

@app.on_event("startup")
async def startup_event():
    """启动时加载模型"""
    logger.info("🚀 启动FastAPI推理服务...")
    success = load_model()
    if not success:
        logger.error("❌ 模型加载失败，服务可能无法正常工作")

@app.get("/health")
async def health_check():
    """健康检查"""
    global model, tokenizer
    
    status = "healthy" if (model is not None and tokenizer is not None) else "unhealthy"
    
    return {
        "status": status,
        "service": "SU模型推理服务",
        "version": "1.0.0",
        "model_loaded": model is not None,
        "tokenizer_loaded": tokenizer is not None,
        "model_name": model_name,
        "format": "safetensors"
    }

@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest):
    """生成文本接口"""
    try:
        # 生成响应
        response_text = generate_text(
            prompt=request.prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p
        )
        
        # 计算token数量（近似）
        tokens_used = len(request.prompt.split()) + len(response_text.split())
        
        return GenerateResponse(
            response=response_text,
            model=request.model,
            tokens_used=tokens_used
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成请求失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")

@app.post("/analyze")
async def analyze_requirement(request: GenerateRequest):
    """需求分析接口 - 返回结构化JSON，纯大模型分析"""
    try:
        logger.info(f"🔍 开始需求分析: {request.prompt[:50]}...")
        
        # 生成结构化分析
        analysis_result = generate_structured_analysis(
            prompt=request.prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p
        )
        
        logger.info(f"✅ 需求分析完成，复杂度: {analysis_result.get('complexity', 'unknown')}")
        return analysis_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"需求分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"需求分析失败: {str(e)}")

# 需求关系分析请求模型
class RelationAnalysisRequest(BaseModel):
    high_level_requirement: str
    low_level_requirement: str
    max_tokens: Optional[int] = 1000
    temperature: Optional[float] = 0.1
    top_p: Optional[float] = 0.8

# 批量需求关系分析请求模型
class BatchRelationAnalysisRequest(BaseModel):
    high_level_requirements: List[str]
    low_level_requirements: List[str]
    max_tokens: Optional[int] = 800
    temperature: Optional[float] = 0.1
    top_p: Optional[float] = 0.8

@app.post("/analyze-relation")
async def analyze_requirement_relation(request: RelationAnalysisRequest):
    """需求关系分析接口 - 判断顶层需求和底层需求之间的追溯关系"""
    try:
        logger.info(f"🔗 开始关系分析...")
        
        # 构建关系分析的提示词
        relation_prompt = f"""请判断以下高层需求和底层需求之间是否存在直接的追溯关系。请从以下几个方面进行分析：

高层需求：{request.high_level_requirement}

底层需求：{request.low_level_requirement}

请按照以下格式返回JSON分析结果（必须是有效JSON）：
{{
  "has_relation": true/false,
  "relation_type": "implementation/support/dependency/decomposition/general",
  "confidence": 0.0-1.0,
  "analysis_details": "详细分析说明为什么有/没有关系",
  "keywords": ["关键词1", "关键词2"],
  "summary": "一句话总结关系判断结果",
  "suggestions": ["建议1", "建议2"]
}}

分析要求：
1. 仔细分析两个需求的内容和语义
2. 判断是否存在实现、支持、依赖或分解关系
3. 给出置信度评分
4. 提取关键技术术语
5. 严格输出JSON格式，不要添加其他文字"""

        # 生成关系分析
        response_text = generate_text(
            prompt=relation_prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p
        )
        
        # 解析JSON响应
        try:
            import json
            import re
            
            # 清理响应文本
            cleaned_response = response_text.strip()
            
            # 尝试提取JSON部分
            json_match = re.search(r'\{.*?\}', cleaned_response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                relation_result = json.loads(json_str)
                
                # 构建完整的返回结果
                result = {
                    'high_level_requirement': request.high_level_requirement,
                    'low_level_requirement': request.low_level_requirement,
                    'has_relation': relation_result.get('has_relation', False),
                    'relation_type': relation_result.get('relation_type', 'unknown'),
                    'confidence': relation_result.get('confidence', 0.5),
                    'analysis_details': relation_result.get('analysis_details', ''),
                    'summary': relation_result.get('summary', '分析完成'),
                    'keywords': relation_result.get('keywords', []),
                    'suggestions': relation_result.get('suggestions', []),
                    'trace_network': build_relation_network(
                        request.high_level_requirement,
                        request.low_level_requirement,
                        relation_result.get('has_relation', False),
                        relation_result.get('relation_type', 'unknown')
                    )
                }
                
                logger.info(f"✅ 关系分析完成，有关系: {result['has_relation']}")
                return result
            else:
                # 如果无法提取JSON，返回默认结构
                logger.warning("无法解析AI响应为JSON，返回默认结果")
                return build_default_relation_result(
                    request.high_level_requirement,
                    request.low_level_requirement,
                    cleaned_response
                )
                
        except json.JSONDecodeError as je:
            logger.error(f"JSON解析失败: {je}")
            return build_default_relation_result(
                request.high_level_requirement,
                request.low_level_requirement,
                response_text
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"关系分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"关系分析失败: {str(e)}")

@app.post("/batch-analyze-relation")
async def batch_analyze_requirement_relation(request: BatchRelationAnalysisRequest):
    """批量需求关系分析接口 - 分析多对顶层需求和底层需求的追溯关系"""
    try:
        logger.info(f"🔗 开始批量关系分析: {len(request.high_level_requirements)} x {len(request.low_level_requirements)}")
        
        # 构建批量分析的提示词
        batch_prompt = f"""请分析以下多对高层需求和底层需求之间的追溯关系。

高层需求列表：
{chr(10).join([f"{i+1}. {req}" for i, req in enumerate(request.high_level_requirements)])}

底层需求列表：
{chr(10).join([f"{i+1}. {req}" for i, req in enumerate(request.low_level_requirements)])}

请按照以下格式返回JSON分析结果（必须是有效JSON）：
{{
  "batch_analysis": [
    {{
      "high_level_index": 0,
      "low_level_index": 0,
      "high_level_requirement": "具体的高层需求",
      "low_level_requirement": "具体的底层需求",
      "has_relation": true/false,
      "relation_type": "implementation/support/dependency/decomposition/general",
      "confidence": 0.0-1.0,
      "analysis_details": "详细分析说明",
      "keywords": ["关键词1", "关键词2"],
      "summary": "一句话总结"
    }}
  ],
  "summary": "整体批量分析总结",
  "statistics": {{
    "total_combinations": 总数,
    "relations_found": 发现的关系数,
    "relation_rate": 关系发现率
  }}
}}

分析要求：
1. 分析所有可能的组合（{len(request.high_level_requirements)} x {len(request.low_level_requirements)} = {len(request.high_level_requirements) * len(request.low_level_requirements)} 个组合）
2. 对每个组合判断是否存在实现、支持、依赖或分解关系
3. 给出置信度评分
4. 提取关键技术术语
5. 严格输出JSON格式，不要添加其他文字"""

        # 生成批量关系分析
        response_text = generate_text(
            prompt=batch_prompt,
            max_tokens=request.max_tokens * 2,  # 批量分析需要更多token
            temperature=request.temperature,
            top_p=request.top_p
        )
        
        # 解析JSON响应
        try:
            import json
            import re
            
            # 清理响应文本
            cleaned_response = response_text.strip()
            
            # 尝试提取JSON部分
            json_match = re.search(r'\{.*?\}', cleaned_response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                batch_result = json.loads(json_str)
                
                # 验证和补充结果
                if 'batch_analysis' not in batch_result:
                    batch_result['batch_analysis'] = []
                
                # 确保每个组合都被分析
                expected_combinations = len(request.high_level_requirements) * len(request.low_level_requirements)
                if len(batch_result['batch_analysis']) < expected_combinations:
                    logger.warning(f"AI返回的分析结果不完整，期望 {expected_combinations} 个，实际 {len(batch_result['batch_analysis'])} 个")
                
                logger.info(f"✅ 批量关系分析完成，分析了 {len(batch_result['batch_analysis'])} 个组合")
                return batch_result
            else:
                # 如果无法提取JSON，返回默认结构
                logger.warning("无法解析AI批量分析响应为JSON，返回默认结果")
                return build_default_batch_result(
                    request.high_level_requirements,
                    request.low_level_requirements,
                    cleaned_response
                )
                
        except json.JSONDecodeError as je:
            logger.error(f"批量分析JSON解析失败: {je}")
            return build_default_batch_result(
                request.high_level_requirements,
                request.low_level_requirements,
                response_text
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量关系分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量关系分析失败: {str(e)}")

def build_relation_network(high_level_req: str, low_level_req: str, has_relation: bool, relation_type: str):
    """构建关系网络图"""
    nodes = [
        {
            'id': 'high_level',
            'name': '顶层需求',
            'text': high_level_req[:100] + '...' if len(high_level_req) > 100 else high_level_req,
            'level': 4,
            'type': 'high_level'
        },
        {
            'id': 'low_level',
            'name': '底层需求',
            'text': low_level_req[:100] + '...' if len(low_level_req) > 100 else low_level_req,
            'level': 2,
            'type': 'low_level'
        }
    ]
    
    links = []
    if has_relation:
        relation_labels = {
            'implementation': '实现关系',
            'support': '支持关系',
            'dependency': '依赖关系',
            'decomposition': '分解关系',
            'general': '追溯关系',
            'unknown': '未知关系'
        }
        
        links.append({
            'source': 'high_level',
            'target': 'low_level',
            'type': relation_type,
            'label': relation_labels.get(relation_type, '追溯关系')
        })
    
    return {'nodes': nodes, 'links': links}

def build_default_relation_result(high_level_req: str, low_level_req: str, ai_response: str):
    """构建默认的关系分析结果"""
    return {
        'high_level_requirement': high_level_req,
        'low_level_requirement': low_level_req,
        'has_relation': False,
        'relation_type': 'unknown',
        'confidence': 0.5,
        'analysis_details': ai_response[:500] if ai_response else 'AI分析服务暂时不可用',
        'summary': '无法确定需求关系',
        'keywords': [],
        'suggestions': ['建议检查需求描述的完整性', '考虑重新表述需求'],
        'trace_network': build_relation_network(high_level_req, low_level_req, False, 'unknown')
    }

def build_default_batch_result(high_level_requirements: List[str], low_level_requirements: List[str], ai_response: str):
    """构建默认的批量分析结果"""
    batch_analysis = []
    for i, high_req in enumerate(high_level_requirements):
        for j, low_req in enumerate(low_level_requirements):
            batch_analysis.append({
                'high_level_index': i,
                'low_level_index': j,
                'high_level_requirement': high_req,
                'low_level_requirement': low_req,
                'has_relation': False,
                'relation_type': 'unknown',
                'confidence': 0.5,
                'analysis_details': ai_response[:200] if ai_response else 'AI分析服务暂时不可用',
                'keywords': [],
                'summary': '无法确定需求关系'
            })
    
    return {
        'batch_analysis': batch_analysis,
        'summary': f'批量分析了 {len(high_level_requirements)} x {len(low_level_requirements)} 个组合，但分析过程中出现错误',
        'statistics': {
            'total_combinations': len(high_level_requirements) * len(low_level_requirements),
            'relations_found': 0,
            'relation_rate': 0.0
        }
    }

@app.get("/models")
async def list_models():
    """列出可用模型"""
    return {
        "models": [
            {
                "name": model_name,
                "loaded": model is not None,
                "description": "SU大语言模型 (GGUF格式)"
            }
        ]
    }

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "SU模型FastAPI推理服务",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

if __name__ == "__main__":
    import uvicorn
    
    print("🎯 启动FastAPI推理服务...")
    print("📍 服务地址: http://0.0.0.0:8000")
    print("🔗 API文档: http://localhost:8000/docs")
    print("🔗 健康检查: http://localhost:8000/health")
    print("=" * 50)
    
    uvicorn.run(
        "fastapi_inference_server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )