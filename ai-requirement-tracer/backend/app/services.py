"""
Backend Services - 后端服务模块
原本的需求分析服务，现已禁用本地规则引擎

文件功能：
- 原本包含本地规则引擎的需求分析
- 现已完全移除本地推理逻辑
- 系统完全依赖AI模型进行分析
- 保留数据库操作功能
"""
import re
import json
import requests
from typing import Dict, List, Any
from .models import Requirement, TraceRecord, Risk, Suggestion
from . import db

class RequirementAnalysisService:
    """需求分析服务 - 完全依赖AI模型"""
    
    def __init__(self):
        # AI服务器地址
        self.ai_server_url = "http://localhost:8000"  # FastAPI推理服务地址
        # 系统完全依赖AI，不再使用本地规则引擎
        pass
    
    
    def analyze_requirement_relation(self, high_level_req: str, low_level_req: str) -> Dict[str, Any]:
        """分析顶层需求和底层需求的追溯关系"""
        try:
            # 调用AI服务进行关系判断
            ai_result = self._call_ai_for_relation_analysis(high_level_req, low_level_req)
            
            # 构建追溯链网络图
            trace_network = self._build_trace_network(high_level_req, low_level_req, ai_result)
            
            return {
                'high_level_requirement': high_level_req,
                'low_level_requirement': low_level_req,
                'has_relation': ai_result.get('has_relation', False),
                'relation_type': ai_result.get('relation_type', ''),
                'confidence': ai_result.get('confidence', 0.0),
                'trace_network': trace_network,
                'analysis_details': ai_result.get('analysis_details', ''),
                'summary': self._generate_relation_summary(high_level_req, low_level_req, ai_result),
                'keywords': ai_result.get('keywords', []),
                'suggestions': ai_result.get('suggestions', [])
            }
            
        except Exception as e:
            print(f"需求关系分析失败: {e}")
            # 返回默认结构
            return {
                'high_level_requirement': high_level_req,
                'low_level_requirement': low_level_req,
                'has_relation': False,
                'relation_type': 'unknown',
                'confidence': 0.0,
                'trace_network': self._build_default_network(high_level_req, low_level_req),
                'analysis_details': f'分析过程中出现错误: {str(e)}',
                'summary': '无法确定需求关系',
                'keywords': [],
                'suggestions': ['建议检查需求描述的完整性', '考虑重新表述需求']
            }
    
    def _call_ai_for_relation_analysis(self, high_level_req: str, low_level_req: str) -> Dict[str, Any]:
        """调用AI服务进行需求关系分析"""
        try:
            # 构建用于AI分析的提示词
            prompt = f"""请分析以下高层需求和底层需求之间是否存在直接的追溯关系。

高层需求：{high_level_req}

底层需求：{low_level_req}

请从以下几个方面进行分析：
1. 需求关系判断：是否存在直接追溯关系（是/否）
2. 关系类型：如果有关系，请说明是什么类型的关系（实现关系、支持关系、依赖关系等）
3. 置信度：对判断结果的信心程度（0-1之间的小数）
4. 详细分析：解释为什么认为有/没有关系
5. 关键词：提取两个需求中的关键概念
6. 改进建议：针对需求表述的建议

请返回结构化的分析结果。"""

            # 调用AI服务的关系分析接口
            response = requests.post(
                f"{self.ai_server_url}/analyze-relation",
                json={
                    "high_level_requirement": high_level_req,
                    "low_level_requirement": low_level_req,
                    "max_tokens": 1000,
                    "temperature": 0.1
                },
                timeout=30
            )
            
            if response.status_code == 200:
                ai_response = response.json()
                # AI服务直接返回结构化的JSON数据
                return {
                    'has_relation': ai_response.get('has_relation', False),
                    'relation_type': ai_response.get('relation_type', 'unknown'),
                    'confidence': ai_response.get('confidence', 0.5),
                    'analysis_details': ai_response.get('analysis_details', ''),
                    'keywords': ai_response.get('keywords', []),
                    'suggestions': ai_response.get('suggestions', [])
                }
            else:
                print(f"AI服务调用失败: {response.status_code}")
                return self._get_default_ai_response()
                
        except Exception as e:
            print(f"调用AI服务失败: {e}")
            return self._get_default_ai_response()
    
    def _parse_ai_relation_response(self, ai_response: str) -> Dict[str, Any]:
        """解析AI的关系分析响应"""
        try:
            # 简单的关键词检测来判断关系
            response_lower = ai_response.lower()
            
            # 判断是否有关系
            has_relation = any(keyword in response_lower for keyword in [
                '是', '存在', 'yes', 'true', '有关系', '相关', '追溯', '实现', '支持'
            ])
            
            # 判断关系类型
            relation_type = 'unknown'
            if '实现' in response_lower:
                relation_type = 'implementation'
            elif '支持' in response_lower:
                relation_type = 'support'
            elif '依赖' in response_lower:
                relation_type = 'dependency'
            elif '分解' in response_lower:
                relation_type = 'decomposition'
            elif has_relation:
                relation_type = 'general'
            
            # 估算置信度
            confidence = 0.8 if has_relation else 0.7
            
            return {
                'has_relation': has_relation,
                'relation_type': relation_type,
                'confidence': confidence,
                'analysis_details': ai_response,
                'keywords': self._extract_keywords(ai_response),
                'suggestions': self._extract_suggestions(ai_response)
            }
            
        except Exception as e:
            print(f"解析AI响应失败: {e}")
            return self._get_default_ai_response()
    
    def _get_default_ai_response(self) -> Dict[str, Any]:
        """获取默认的AI响应"""
        return {
            'has_relation': False,
            'relation_type': 'unknown',
            'confidence': 0.5,
            'analysis_details': 'AI分析服务暂时不可用',
            'keywords': [],
            'suggestions': ['建议稍后重试分析']
        }
    
    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中提取关键词"""
        # 简单的关键词提取逻辑
        keywords = []
        common_tech_terms = [
            'DPU', 'BOOT', 'CSC', 'DRAM', 'BIT', 'EEPROM', 'CPU', 'VME', 'IOCC',
            'Bootstrap', 'Monitor', 'PROM', 'EDAC', 'RS-232', 'SCM'
        ]
        
        for term in common_tech_terms:
            if term.lower() in text.lower():
                keywords.append(term)
        
        return keywords[:5]  # 最多返回5个关键词
    
    def _extract_suggestions(self, text: str) -> List[str]:
        """从文本中提取建议"""
        suggestions = []
        if '建议' in text:
            # 简单提取包含建议的句子
            sentences = text.split('。')
            for sentence in sentences:
                if '建议' in sentence:
                    suggestions.append(sentence.strip())
        
        if not suggestions:
            suggestions = ['建议进一步明确需求描述', '考虑添加更多技术细节']
        
        return suggestions[:3]  # 最多返回3个建议
    
    def _build_trace_network(self, high_level_req: str, low_level_req: str, ai_result: Dict) -> Dict[str, Any]:
        """构建追溯网络图"""
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
        if ai_result.get('has_relation', False):
            links.append({
                'source': 'high_level',
                'target': 'low_level',
                'type': ai_result.get('relation_type', 'general'),
                'label': self._get_relation_label(ai_result.get('relation_type', 'general')),
                'confidence': ai_result.get('confidence', 0.5)
            })
        
        return {'nodes': nodes, 'links': links}
    
    def _build_default_network(self, high_level_req: str, low_level_req: str) -> Dict[str, Any]:
        """构建默认的网络图（无连接）"""
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
        
        return {'nodes': nodes, 'links': []}
    
    def _get_relation_label(self, relation_type: str) -> str:
        """获取关系类型的标签"""
        labels = {
            'implementation': '实现关系',
            'support': '支持关系',
            'dependency': '依赖关系',
            'decomposition': '分解关系',
            'general': '追溯关系',
            'unknown': '未知关系'
        }
        return labels.get(relation_type, '追溯关系')
    
    def _generate_relation_summary(self, high_level_req: str, low_level_req: str, ai_result: Dict) -> str:
        """生成关系分析摘要"""
        if ai_result.get('has_relation', False):
            relation_label = self._get_relation_label(ai_result.get('relation_type', 'general'))
            confidence = ai_result.get('confidence', 0.5)
            return f"检测到{relation_label}，置信度: {confidence:.1%}"
        else:
            return "未检测到直接的追溯关系"
    
    def batch_analyze_requirement_relations(self, high_level_requirements: List[str], low_level_requirements: List[str]) -> Dict[str, Any]:
        """批量分析多对顶层需求和底层需求的追溯关系"""
        try:
            print(f"开始批量分析 {len(high_level_requirements)} 个顶层需求和 {len(low_level_requirements)} 个底层需求")
            
            # 存储所有分析结果
            all_relations = []
            all_nodes = []
            all_links = []
            node_id_counter = 0
            
            # 为每个顶层需求创建节点
            high_level_nodes = {}
            for i, req in enumerate(high_level_requirements):
                node_id = f"high_{i}"
                high_level_nodes[i] = node_id
                all_nodes.append({
                    'id': node_id,
                    'name': f'顶层需求{i+1}',
                    'text': req[:100] + '...' if len(req) > 100 else req,
                    'level': 4,
                    'type': 'high_level',
                    'original_index': i
                })
                node_id_counter += 1
            
            # 为每个底层需求创建节点
            low_level_nodes = {}
            for i, req in enumerate(low_level_requirements):
                node_id = f"low_{i}"
                low_level_nodes[i] = node_id
                all_nodes.append({
                    'id': node_id,
                    'name': f'底层需求{i+1}',
                    'text': req[:100] + '...' if len(req) > 100 else req,
                    'level': 2,
                    'type': 'low_level',
                    'original_index': i
                })
                node_id_counter += 1
            
            # 分析所有可能的组合
            total_combinations = len(high_level_requirements) * len(low_level_requirements)
            print(f"需要分析 {total_combinations} 个需求组合")
            
            for i, high_req in enumerate(high_level_requirements):
                for j, low_req in enumerate(low_level_requirements):
                    try:
                        # 调用AI服务分析单个关系
                        relation_result = self._call_ai_for_relation_analysis(high_req, low_req)
                        
                        # 构建关系记录
                        relation_record = {
                            'high_level_index': i,
                            'low_level_index': j,
                            'high_level_requirement': high_req,
                            'low_level_requirement': low_req,
                            'has_relation': relation_result.get('has_relation', False),
                            'relation_type': relation_result.get('relation_type', 'unknown'),
                            'confidence': relation_result.get('confidence', 0.0),
                            'analysis_details': relation_result.get('analysis_details', ''),
                            'keywords': relation_result.get('keywords', []),
                            'suggestions': relation_result.get('suggestions', [])
                        }
                        all_relations.append(relation_record)
                        
                        # 如果有关系，添加连线
                        if relation_result.get('has_relation', False):
                            link = {
                                'source': high_level_nodes[i],
                                'target': low_level_nodes[j],
                                'type': relation_result.get('relation_type', 'general'),
                                'label': self._get_relation_label(relation_result.get('relation_type', 'general')),
                                'confidence': relation_result.get('confidence', 0.5),
                                'high_level_index': i,
                                'low_level_index': j
                            }
                            all_links.append(link)
                        
                        print(f"完成分析 {i+1}/{len(high_level_requirements)} x {j+1}/{len(low_level_requirements)}")
                        
                    except Exception as e:
                        print(f"分析需求对 ({i}, {j}) 失败: {e}")
                        # 添加失败记录
                        all_relations.append({
                            'high_level_index': i,
                            'low_level_index': j,
                            'high_level_requirement': high_req,
                            'low_level_requirement': low_req,
                            'has_relation': False,
                            'relation_type': 'error',
                            'confidence': 0.0,
                            'analysis_details': f'分析失败: {str(e)}',
                            'keywords': [],
                            'suggestions': ['建议检查需求描述']
                        })
            
            # 统计信息
            total_relations = len([r for r in all_relations if r['has_relation']])
            relation_types = {}
            for relation in all_relations:
                if relation['has_relation']:
                    rel_type = relation['relation_type']
                    relation_types[rel_type] = relation_types.get(rel_type, 0) + 1
            
            # 构建完整的批量分析结果
            batch_result = {
                'summary': f'批量分析了 {len(high_level_requirements)} 个顶层需求和 {len(low_level_requirements)} 个底层需求，共 {total_combinations} 个组合，发现 {total_relations} 个追溯关系',
                'high_level_requirements': high_level_requirements,
                'low_level_requirements': low_level_requirements,
                'total_combinations': total_combinations,
                'total_relations_found': total_relations,
                'relation_types_count': relation_types,
                'relations': all_relations,
                'trace_network': {
                    'nodes': all_nodes,
                    'links': all_links
                },
                'statistics': {
                    'high_level_count': len(high_level_requirements),
                    'low_level_count': len(low_level_requirements),
                    'total_combinations': total_combinations,
                    'relations_found': total_relations,
                    'relation_rate': total_relations / total_combinations if total_combinations > 0 else 0,
                    'relation_types': relation_types
                }
            }
            
            print(f"✅ 批量分析完成，发现 {total_relations} 个追溯关系")
            return batch_result
            
        except Exception as e:
            print(f"批量需求关系分析失败: {e}")
            return {
                'error': f'批量分析失败: {str(e)}',
                'summary': '批量分析过程中出现错误',
                'high_level_requirements': high_level_requirements,
                'low_level_requirements': low_level_requirements,
                'total_combinations': len(high_level_requirements) * len(low_level_requirements),
                'total_relations_found': 0,
                'relations': [],
                'trace_network': {'nodes': [], 'links': []},
                'statistics': {}
            }
    
    def save_batch_trace_relations_to_db(self, batch_result: Dict[str, Any]) -> int:
        """保存批量追溯关系分析结果到数据库"""
        try:
            # 创建批量分析记录
            combined_desc = f"批量分析 - 顶层需求: {len(batch_result.get('high_level_requirements', []))} 个, 底层需求: {len(batch_result.get('low_level_requirements', []))} 个"
            requirement = Requirement(
                title=f"批量需求关系分析 - {batch_result.get('summary', '')}",
                description=combined_desc
            )
            db.session.add(requirement)
            db.session.flush()
            
            # 保存所有关系分析记录
            for relation in batch_result.get('relations', []):
                if relation.get('has_relation', False):
                    trace_record = TraceRecord(
                        requirement_id=requirement.id,
                        stage=f"批量关系分析-{relation.get('high_level_index', 0)}-{relation.get('low_level_index', 0)}",
                        stage_type=relation.get('relation_type', 'unknown'),
                        description=relation.get('analysis_details', '')
                    )
                    db.session.add(trace_record)
            
            # 保存建议
            for relation in batch_result.get('relations', []):
                for suggestion in relation.get('suggestions', []):
                    suggestion_record = Suggestion(
                        requirement_id=requirement.id,
                        content=suggestion
                    )
                    db.session.add(suggestion_record)
            
            db.session.commit()
            return requirement.id
            
        except Exception as e:
            print(f"保存批量分析结果到数据库失败: {e}")
            db.session.rollback()
            return None

    def save_trace_relation_to_db(self, high_level_req: str, low_level_req: str, analysis_result: Dict) -> int:
        """保存追溯关系分析结果到数据库"""
        # 创建一个组合需求记录
        combined_desc = f"顶层需求: {high_level_req}\n\n底层需求: {low_level_req}"
        requirement = Requirement(
            title=f"需求关系分析 - {analysis_result.get('summary', '')}",
            description=combined_desc
        )
        db.session.add(requirement)
        db.session.flush()
        
        # 保存关系分析记录
        if analysis_result.get('has_relation', False):
            trace_record = TraceRecord(
                requirement_id=requirement.id,
                stage='关系分析',
                stage_type=analysis_result.get('relation_type', 'unknown'),
                description=analysis_result.get('analysis_details', '')
            )
            db.session.add(trace_record)
        
        # 保存建议
        for suggestion in analysis_result.get('suggestions', []):
            suggestion_record = Suggestion(
                requirement_id=requirement.id,
                content=suggestion
            )
            db.session.add(suggestion_record)
        
        db.session.commit()
        return requirement.id
    
    # 所有本地分析方法已移除，系统完全依赖AI模型
    
