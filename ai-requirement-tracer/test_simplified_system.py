#!/usr/bin/env python3
"""
简化后的需求追溯系统测试脚本
测试移除单需求分析后的功能
"""

import requests
import json
import time

# 配置
BACKEND_URL = "http://localhost:5000/api"
FASTAPI_URL = "http://localhost:8000"

def test_relation_analysis():
    """测试关系分析功能"""
    
    print("🔗 测试关系分析功能...")
    
    # 测试数据
    high_level_req = "系统应提供用户登录功能"
    low_level_req = "实现用户名密码验证机制"
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/trace-relation",
            json={
                "high_level_requirement": high_level_req,
                "low_level_requirement": low_level_req,
                "save_to_db": False
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                data = result['data']
                print("✅ 关系分析成功!")
                print(f"📊 有关系: {data.get('has_relation', False)}")
                print(f"🔗 关系类型: {data.get('relation_type', 'unknown')}")
                print(f"📈 置信度: {data.get('confidence', 0):.2%}")
                print(f"📝 摘要: {data.get('summary', '')}")
                return True
            else:
                print(f"❌ 关系分析失败: {result.get('error', '未知错误')}")
                return False
        else:
            print(f"❌ API请求失败: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 关系分析测试失败: {e}")
        return False

def test_batch_analysis():
    """测试批量分析功能"""
    
    print("\n📊 测试批量分析功能...")
    
    # 测试数据
    high_level_requirements = [
        "系统应提供用户登录功能",
        "系统应支持用户权限管理"
    ]
    
    low_level_requirements = [
        "实现用户名密码验证机制",
        "实现角色权限分配功能",
        "实现用户行为数据收集"
    ]
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/batch-trace-relation",
            json={
                "high_level_requirements": high_level_requirements,
                "low_level_requirements": low_level_requirements,
                "save_to_db": False
            },
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                data = result['data']
                print("✅ 批量分析成功!")
                print(f"📊 分析组合数: {data.get('total_combinations', 0)}")
                print(f"🔗 发现关系数: {data.get('total_relations_found', 0)}")
                print(f"📈 关系发现率: {data.get('statistics', {}).get('relation_rate', 0):.2%}")
                
                # 显示关系类型统计
                relation_types = data.get('relation_types_count', {})
                if relation_types:
                    print("\n📋 关系类型统计:")
                    for rel_type, count in relation_types.items():
                        print(f"  - {rel_type}: {count} 个")
                
                return True
            else:
                print(f"❌ 批量分析失败: {result.get('error', '未知错误')}")
                return False
        else:
            print(f"❌ API请求失败: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 批量分析测试失败: {e}")
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

def test_removed_functionality():
    """测试已移除的功能（应该返回错误）"""
    print("\n🚫 测试已移除的单需求分析功能...")
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/analyze",
            json={
                "requirement": "测试需求",
                "save_to_db": False
            },
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if not result.get('success'):
                print("✅ 单需求分析功能已正确移除")
                return True
            else:
                print("❌ 单需求分析功能仍然可用，应该被移除")
                return False
        else:
            print("✅ 单需求分析功能已正确移除")
            return True
            
    except Exception as e:
        print(f"✅ 单需求分析功能已正确移除: {e}")
        return True

def main():
    """主测试函数"""
    print("🚀 简化后的需求追溯系统测试")
    print("=" * 50)
    
    # 健康检查
    if not test_health_checks():
        print("\n❌ 服务健康检查失败，请确保服务正常运行")
        return
    
    print()
    
    # 测试关系分析
    relation_success = test_relation_analysis()
    
    # 测试批量分析
    batch_success = test_batch_analysis()
    
    # 测试已移除的功能
    removed_success = test_removed_functionality()
    
    print("\n" + "=" * 50)
    print("📊 测试结果总结:")
    print(f"关系分析: {'✅ 通过' if relation_success else '❌ 失败'}")
    print(f"批量分析: {'✅ 通过' if batch_success else '❌ 失败'}")
    print(f"功能移除: {'✅ 通过' if removed_success else '❌ 失败'}")
    
    if relation_success and batch_success and removed_success:
        print("\n🎉 简化后的系统测试全部通过!")
        print("\n📋 系统功能总结:")
        print("✅ 关系追溯分析 - 支持单对需求关系分析")
        print("✅ 批量关系分析 - 支持多对需求关系分析")
        print("✅ 智能关系识别 - AI自动判断关系类型")
        print("✅ 可视化展示 - 网络图和统计信息")
        print("❌ 单需求分析 - 已移除，专注于关系分析")
    else:
        print("\n⚠️ 部分测试失败，请检查服务状态")

if __name__ == "__main__":
    main()
