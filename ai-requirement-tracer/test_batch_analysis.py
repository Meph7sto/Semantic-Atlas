#!/usr/bin/env python3
"""
批量需求关系分析测试脚本
测试新的批量分析功能
"""

import requests
import json
import time

# 配置
BACKEND_URL = "http://localhost:5000/api"
FASTAPI_URL = "http://localhost:8000"

def test_batch_analysis():
    """测试批量分析功能"""
    
    # 测试数据
    high_level_requirements = [
        "系统应提供用户登录功能",
        "系统应支持用户权限管理", 
        "系统应提供数据统计功能"
    ]
    
    low_level_requirements = [
        "实现用户名密码验证机制",
        "实现角色权限分配功能",
        "实现用户行为数据收集",
        "实现数据可视化展示"
    ]
    
    print("🧪 开始测试批量需求关系分析...")
    print(f"📊 顶层需求数量: {len(high_level_requirements)}")
    print(f"📊 底层需求数量: {len(low_level_requirements)}")
    print(f"📊 总组合数: {len(high_level_requirements) * len(low_level_requirements)}")
    print()
    
    # 测试后端API
    print("🔗 测试后端批量分析API...")
    try:
        response = requests.post(
            f"{BACKEND_URL}/batch-trace-relation",
            json={
                "high_level_requirements": high_level_requirements,
                "low_level_requirements": low_level_requirements,
                "save_to_db": False
            },
            timeout=120  # 批量分析可能需要更长时间
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                data = result['data']
                print("✅ 后端批量分析成功!")
                print(f"📈 分析组合数: {data.get('total_combinations', 0)}")
                print(f"🔗 发现关系数: {data.get('total_relations_found', 0)}")
                print(f"📊 关系发现率: {data.get('statistics', {}).get('relation_rate', 0):.2%}")
                
                # 显示关系类型统计
                relation_types = data.get('relation_types_count', {})
                if relation_types:
                    print("\n📋 关系类型统计:")
                    for rel_type, count in relation_types.items():
                        print(f"  - {rel_type}: {count} 个")
                
                # 显示前几个关系详情
                relations = data.get('relations', [])
                found_relations = [r for r in relations if r.get('has_relation')]
                if found_relations:
                    print(f"\n🔍 发现的关系详情 (前3个):")
                    for i, relation in enumerate(found_relations[:3]):
                        print(f"  {i+1}. 顶层需求#{relation.get('high_level_index', 0)+1} -> 底层需求#{relation.get('low_level_index', 0)+1}")
                        print(f"     关系类型: {relation.get('relation_type', 'unknown')}")
                        print(f"     置信度: {relation.get('confidence', 0):.2%}")
                        print(f"     摘要: {relation.get('summary', '')}")
                        print()
                
                return True
            else:
                print(f"❌ 后端批量分析失败: {result.get('error', '未知错误')}")
                return False
        else:
            print(f"❌ 后端API请求失败: {response.status_code}")
            print(f"响应内容: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 后端批量分析测试失败: {e}")
        return False

def test_fastapi_batch_analysis():
    """测试FastAPI批量分析接口"""
    
    high_level_requirements = [
        "系统应提供用户登录功能",
        "系统应支持用户权限管理"
    ]
    
    low_level_requirements = [
        "实现用户名密码验证机制",
        "实现角色权限分配功能"
    ]
    
    print("\n🔗 测试FastAPI批量分析接口...")
    try:
        response = requests.post(
            f"{FASTAPI_URL}/batch-analyze-relation",
            json={
                "high_level_requirements": high_level_requirements,
                "low_level_requirements": low_level_requirements,
                "max_tokens": 800,
                "temperature": 0.1
            },
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ FastAPI批量分析成功!")
            print(f"📊 分析结果: {result.get('summary', '')}")
            
            batch_analysis = result.get('batch_analysis', [])
            print(f"📈 分析组合数: {len(batch_analysis)}")
            
            found_relations = [r for r in batch_analysis if r.get('has_relation')]
            print(f"🔗 发现关系数: {len(found_relations)}")
            
            return True
        else:
            print(f"❌ FastAPI批量分析失败: {response.status_code}")
            print(f"响应内容: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ FastAPI批量分析测试失败: {e}")
        return False

def test_health_checks():
    """测试服务健康状态"""
    print("🏥 检查服务健康状态...")
    
    # 检查后端
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ 后端服务正常")
        else:
            print(f"❌ 后端服务异常: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 后端服务不可用: {e}")
        return False
    
    # 检查FastAPI
    try:
        response = requests.get(f"{FASTAPI_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ FastAPI服务正常")
        else:
            print(f"❌ FastAPI服务异常: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ FastAPI服务不可用: {e}")
        return False
    
    return True

def main():
    """主测试函数"""
    print("🚀 批量需求关系分析功能测试")
    print("=" * 50)
    
    # 健康检查
    if not test_health_checks():
        print("\n❌ 服务健康检查失败，请确保服务正常运行")
        return
    
    print()
    
    # 测试FastAPI批量分析
    fastapi_success = test_fastapi_batch_analysis()
    
    # 测试后端批量分析
    backend_success = test_batch_analysis()
    
    print("\n" + "=" * 50)
    print("📊 测试结果总结:")
    print(f"FastAPI批量分析: {'✅ 通过' if fastapi_success else '❌ 失败'}")
    print(f"后端批量分析: {'✅ 通过' if backend_success else '❌ 失败'}")
    
    if fastapi_success and backend_success:
        print("\n🎉 批量分析功能测试全部通过!")
    else:
        print("\n⚠️ 部分测试失败，请检查服务状态")

if __name__ == "__main__":
    main()
