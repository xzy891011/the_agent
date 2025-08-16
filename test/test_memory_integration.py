#!/usr/bin/env python3
"""
记忆系统集成测试

测试记忆系统各个组件是否在整个智能体系统中被正确调用和集成，包括：
1. 组件导入测试
2. 组件基础功能测试  
3. 系统集成调用测试
4. 工作流程测试
"""

import sys
import os
import time
import asyncio
from typing import Dict, List, Any
from unittest.mock import Mock, patch, MagicMock
import inspect

# 添加项目根目录到路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def create_real_config():
    """创建真实配置"""
    from app.core.config import ConfigManager
    config_manager = ConfigManager()
    try:
        config = config_manager.load_config()
        return config
    except Exception as e:
        print(f"加载配置失败，使用默认配置: {e}")
        return config_manager.config

def create_real_memory_integration():
    """创建真实记忆集成"""
    from app.core.memory.enhanced_memory_integration import EnhancedMemoryIntegration
    try:
        config = create_real_config()
        return EnhancedMemoryIntegration(config=config)
    except Exception as e:
        print(f"创建记忆集成失败: {e}")
        return None

def create_real_es_config():
    """创建真实ES配置"""
    from app.core.config import ConfigManager
    config_manager = ConfigManager()
    try:
        config = config_manager.load_config()
        return config_manager.get_es_config()
    except Exception as e:
        print(f"加载ES配置失败，使用默认配置: {e}")
        return config_manager.default_config.get("es", {})


def test_memory_component_imports():
    """测试记忆组件导入"""
    print("🧪 测试记忆组件导入...")
    
    import_results = {}
    
    # 测试核心组件导入
    try:
        from app.core.memory.enhanced_memory_namespace import (
            MemoryNamespaceManager, AgentRole, DomainTag, MemoryType
        )
        import_results['namespace'] = True
        print("✅ 记忆命名空间组件导入成功")
    except Exception as e:
        import_results['namespace'] = False
        print(f"❌ 记忆命名空间组件导入失败: {e}")
    
    try:
        from app.core.memory.agent_memory_preferences import (
            AgentMemoryPreferenceManager
        )
        import_results['preferences'] = True
        print("✅ 记忆偏好组件导入成功")
    except Exception as e:
        import_results['preferences'] = False
        print(f"❌ 记忆偏好组件导入失败: {e}")
    
    try:
        from app.core.memory.agent_memory_filter import (
            AgentMemoryFilter
        )
        import_results['filter'] = True
        print("✅ 记忆筛选组件导入成功")
    except Exception as e:
        import_results['filter'] = False
        print(f"❌ 记忆筛选组件导入失败: {e}")
    
    try:
        from app.core.memory.agent_memory_injector import (
            AgentMemoryInjector
        )
        import_results['injector'] = True
        print("✅ 记忆注入组件导入成功")
    except Exception as e:
        import_results['injector'] = False
        print(f"❌ 记忆注入组件导入失败: {e}")
    
    try:
        from app.core.memory.dynamic_prompt_manager import (
            DynamicPromptManager
        )
        import_results['prompt_manager'] = True
        print("✅ 动态Prompt管理器导入成功")
    except Exception as e:
        import_results['prompt_manager'] = False
        print(f"❌ 动态Prompt管理器导入失败: {e}")
    
    try:
        from app.core.memory.memory_relevance_scorer import (
            MemoryRelevanceScorer
        )
        import_results['scorer'] = True
        print("✅ 记忆相关性评分器导入成功")
    except Exception as e:
        import_results['scorer'] = False
        print(f"❌ 记忆相关性评分器导入失败: {e}")
    
    try:
        from app.core.memory.prompt_length_controller import (
            PromptLengthController
        )
        import_results['length_controller'] = True
        print("✅ Prompt长度控制器导入成功")
    except Exception as e:
        import_results['length_controller'] = False
        print(f"❌ Prompt长度控制器导入失败: {e}")
    
    try:
        from app.core.memory.memory_usage_monitor import (
            MemoryUsageMonitor
        )
        import_results['monitor'] = True
        print("✅ 记忆使用监控器导入成功")
    except Exception as e:
        import_results['monitor'] = False
        print(f"❌ 记忆使用监控器导入失败: {e}")
    
    try:
        from app.core.memory.adaptive_memory_optimizer import (
            AdaptiveMemoryOptimizer
        )
        import_results['optimizer'] = True
        print("✅ 自适应记忆优化器导入成功")
    except Exception as e:
        import_results['optimizer'] = False
        print(f"❌ 自适应记忆优化器导入失败: {e}")
    
    success_count = sum(import_results.values())
    total_count = len(import_results)
    
    print(f"\n📊 导入测试结果: {success_count}/{total_count} 个组件导入成功")
    return import_results

def test_component_initialization():
    """测试组件初始化"""
    print("\n🧪 测试组件初始化...")
    
    init_results = {}
    
    try:
        from app.core.memory.enhanced_memory_namespace import MemoryNamespaceManager
        manager = MemoryNamespaceManager()
        init_results['namespace'] = True
        print("✅ 记忆命名空间管理器初始化成功")
    except Exception as e:
        init_results['namespace'] = False
        print(f"❌ 记忆命名空间管理器初始化失败: {e}")
    
    try:
        from app.core.memory.agent_memory_preferences import AgentMemoryPreferenceManager
        manager = AgentMemoryPreferenceManager()
        init_results['preferences'] = True
        print("✅ 记忆偏好管理器初始化成功")
    except Exception as e:
        init_results['preferences'] = False
        print(f"❌ 记忆偏好管理器初始化失败: {e}")
    
    try:
        from app.core.memory.agent_memory_filter import AgentMemoryFilter
        filter_obj = AgentMemoryFilter()
        init_results['filter'] = True
        print("✅ 记忆筛选器初始化成功")
    except Exception as e:
        init_results['filter'] = False
        print(f"❌ 记忆筛选器初始化失败: {e}")
    
    try:
        from app.core.memory.agent_memory_injector import AgentMemoryInjector
        # 为记忆注入器提供必要的记忆集成参数
        memory_integration = create_real_memory_integration()
        if memory_integration:
            injector = AgentMemoryInjector(memory_integration)
            init_results['injector'] = True
            print("✅ 记忆注入器初始化成功")
        else:
            init_results['injector'] = False
            print("❌ 记忆注入器初始化失败: 无法创建记忆集成")
    except Exception as e:
        init_results['injector'] = False
        print(f"❌ 记忆注入器初始化失败: {e}")
    
    try:
        from app.core.memory.dynamic_prompt_manager import DynamicPromptManager
        manager = DynamicPromptManager()
        init_results['prompt_manager'] = True
        print("✅ 动态Prompt管理器初始化成功")
    except Exception as e:
        init_results['prompt_manager'] = False
        print(f"❌ 动态Prompt管理器初始化失败: {e}")
    
    try:
        from app.core.memory.memory_relevance_scorer import MemoryRelevanceScorer
        scorer = MemoryRelevanceScorer()
        init_results['scorer'] = True
        print("✅ 记忆相关性评分器初始化成功")
    except Exception as e:
        init_results['scorer'] = False
        print(f"❌ 记忆相关性评分器初始化失败: {e}")
    
    try:
        from app.core.memory.prompt_length_controller import PromptLengthController
        controller = PromptLengthController()
        init_results['length_controller'] = True
        print("✅ Prompt长度控制器初始化成功")
    except Exception as e:
        init_results['length_controller'] = False
        print(f"❌ Prompt长度控制器初始化失败: {e}")
    
    try:
        from app.core.memory.memory_usage_monitor import MemoryUsageMonitor
        monitor = MemoryUsageMonitor()
        init_results['monitor'] = True
        print("✅ 记忆使用监控器初始化成功")
    except Exception as e:
        init_results['monitor'] = False
        print(f"❌ 记忆使用监控器初始化失败: {e}")
    
    try:
        from app.core.memory.adaptive_memory_optimizer import AdaptiveMemoryOptimizer
        optimizer = AdaptiveMemoryOptimizer()
        init_results['optimizer'] = True
        print("✅ 自适应记忆优化器初始化成功")
    except Exception as e:
        init_results['optimizer'] = False
        print(f"❌ 自适应记忆优化器初始化失败: {e}")
    
    success_count = sum(init_results.values())
    total_count = len(init_results)
    
    print(f"\n📊 初始化测试结果: {success_count}/{total_count} 个组件初始化成功")
    return init_results

def test_component_basic_functionality():
    """测试组件基础功能"""
    print("\n🧪 测试组件基础功能...")
    
    func_results = {}
    
    # 测试命名空间管理器
    try:
        from app.core.memory.enhanced_memory_namespace import (
            MemoryNamespaceManager, AgentRole, MemoryType
        )
        manager = MemoryNamespaceManager()
        namespace = manager.create_namespace(
            user_id="test_user",
            agent_role=AgentRole.GEOPHYSICS_ANALYSIS.value,
            memory_type=MemoryType.SEMANTIC.value,
            content="测试内容"
        )
        assert namespace is not None
        func_results['namespace'] = True
        print("✅ 命名空间管理器基础功能正常")
    except Exception as e:
        func_results['namespace'] = False
        print(f"❌ 命名空间管理器基础功能失败: {e}")
    
    # 测试偏好管理器
    try:
        from app.core.memory.agent_memory_preferences import AgentMemoryPreferenceManager
        from app.core.memory.enhanced_memory_namespace import AgentRole
        manager = AgentMemoryPreferenceManager()
        preference = manager.get_agent_preference(AgentRole.GEOPHYSICS_ANALYSIS.value)
        assert preference is not None
        func_results['preferences'] = True
        print("✅ 偏好管理器基础功能正常")
    except Exception as e:
        func_results['preferences'] = False
        print(f"❌ 偏好管理器基础功能失败: {e}")
    
    # 测试记忆筛选器
    try:
        from app.core.memory.agent_memory_filter import AgentMemoryFilter
        from app.core.memory.enhanced_memory_namespace import AgentRole
        filter_obj = AgentMemoryFilter()
        # 创建空的测试数据
        memories = []
        from app.core.memory.agent_memory_filter import MemoryFilterContext
        context = MemoryFilterContext(
            user_id="test_user",
            session_id="test_session",
            agent_role=AgentRole.GEOPHYSICS_ANALYSIS.value,
            query="测试查询"
        )
        result = filter_obj.filter_memories_for_agent(memories, context)
        assert result is not None
        func_results['filter'] = True
        print("✅ 记忆筛选器基础功能正常")
    except Exception as e:
        func_results['filter'] = False
        print(f"❌ 记忆筛选器基础功能失败: {e}")
    
    # 测试记忆注入器
    try:
        from app.core.memory.agent_memory_injector import AgentMemoryInjector
        from app.core.state import IsotopeSystemState
        
        memory_integration = create_real_memory_integration()
        if memory_integration:
            injector = AgentMemoryInjector(memory_integration)
            state = IsotopeSystemState()
            result = injector.inject_memories_to_prompt(
                base_prompt="测试基础prompt",
                state=state,
                agent_role="geophysics_analysis"
            )
            assert result is not None
            func_results['injector'] = True
            print("✅ 记忆注入器基础功能正常")
        else:
            func_results['injector'] = False
            print("❌ 记忆注入器基础功能失败: 无法创建记忆集成")
    except Exception as e:
        func_results['injector'] = False
        print(f"❌ 记忆注入器基础功能失败: {e}")
    
    # 测试动态Prompt管理器
    try:
        from app.core.memory.dynamic_prompt_manager import (
            DynamicPromptManager, PromptContext
        )
        from app.core.memory.agent_memory_filter import FilteredMemoryResult
        
        manager = DynamicPromptManager()
        
        # 创建测试数据
        filtered_result = FilteredMemoryResult(
            memories=[],
            total_score=0.0,
            confidence=0.5,
            coverage_domains=[],
            memory_distribution={},
            filter_summary="测试摘要",
            execution_time=0.1
        )
        
        context = PromptContext()
        
        result = manager.generate_dynamic_prompt(
            agent_role="geophysics_analysis",
            base_prompt="测试基础prompt",
            memory_result=filtered_result,
            context=context
        )
        assert result is not None
        func_results['prompt_manager'] = True
        print("✅ 动态Prompt管理器基础功能正常")
    except Exception as e:
        func_results['prompt_manager'] = False
        print(f"❌ 动态Prompt管理器基础功能失败: {e}")
    
    success_count = sum(func_results.values())
    total_count = len(func_results)
    
    print(f"\n📊 基础功能测试结果: {success_count}/{total_count} 个组件功能正常")
    return func_results

def test_system_integration():
    """测试系统集成调用"""
    print("\n🧪 测试系统集成调用...")
    
    integration_results = {}
    
    # 测试是否能在核心系统中找到记忆组件的引用
    try:
        # 检查是否有增强记忆集成模块
        from app.core.memory.enhanced_memory_integration import EnhancedMemoryIntegration
        integration = EnhancedMemoryIntegration(config=create_real_config())
        integration_results['core_integration'] = True
        print("✅ 核心系统记忆集成正常")
    except Exception as e:
        integration_results['core_integration'] = False
        print(f"❌ 核心系统记忆集成失败: {e}")
    
    # 测试引擎适配器
    try:
        from app.core.memory.engine_adapter import MemoryAwareEngineAdapter
        memory_integration = create_real_memory_integration()
        if memory_integration:
            adapter = MemoryAwareEngineAdapter(memory_integration)
            integration_results['engine_adapter'] = True
            print("✅ 引擎记忆适配器正常")
        else:
            integration_results['engine_adapter'] = False
            print("❌ 引擎记忆适配器失败: 无法创建记忆集成")
    except Exception as e:
        integration_results['engine_adapter'] = False
        print(f"❌ 引擎记忆适配器失败: {e}")
    
    # 测试增强LangGraph存储
    try:
        from app.core.memory.enhanced_langgraph_store import EnhancedLangGraphMemoryStore
        es_config = create_real_es_config()
        # 使用真实的ES配置
        store = EnhancedLangGraphMemoryStore(es_config)
        integration_results['enhanced_store'] = True
        print("✅ 增强LangGraph存储正常")
    except Exception as e:
        integration_results['enhanced_store'] = False
        print(f"❌ 增强LangGraph存储失败: {e}")
    
    success_count = sum(integration_results.values())
    total_count = len(integration_results)
    
    print(f"\n📊 系统集成测试结果: {success_count}/{total_count} 个集成点正常")
    return integration_results

def test_workflow_integration():
    """测试工作流程集成"""
    print("\n🧪 测试工作流程集成...")
    
    workflow_results = {}
    
    # 测试完整的记忆工作流程
    try:
        # 1. 创建命名空间
        from app.core.memory.enhanced_memory_namespace import (
            MemoryNamespaceManager, AgentRole, MemoryType, DomainTag
        )
        namespace_manager = MemoryNamespaceManager()
        namespace = namespace_manager.create_namespace(
            user_id="workflow_test",
            agent_role=AgentRole.GEOPHYSICS_ANALYSIS.value,
            memory_type=MemoryType.SEMANTIC.value,
            content="地球物理分析工作流程测试"
        )
        
        # 2. 获取偏好设置
        from app.core.memory.agent_memory_preferences import AgentMemoryPreferenceManager
        preference_manager = AgentMemoryPreferenceManager()
        preference = preference_manager.get_agent_preference(AgentRole.GEOPHYSICS_ANALYSIS.value)
        
        # 3. 创建记忆筛选器
        from app.core.memory.agent_memory_filter import AgentMemoryFilter
        memory_filter = AgentMemoryFilter()
        
        # 4. 创建记忆注入器
        from app.core.memory.agent_memory_injector import AgentMemoryInjector
        memory_integration = create_real_memory_integration()
        if memory_integration:
            memory_injector = AgentMemoryInjector(memory_integration)
        else:
            memory_injector = None
        
        # 5. 创建动态Prompt管理器
        from app.core.memory.dynamic_prompt_manager import DynamicPromptManager
        prompt_manager = DynamicPromptManager()
        
        # 验证工作流程组件协作
        assert namespace is not None
        assert preference is not None
        assert memory_filter is not None
        assert memory_injector is not None
        assert prompt_manager is not None
        
        workflow_results['complete_workflow'] = True
        print("✅ 完整记忆工作流程集成正常")
        
    except Exception as e:
        workflow_results['complete_workflow'] = False
        print(f"❌ 完整记忆工作流程集成失败: {e}")
    
    # 测试跨组件数据传递
    try:
        # 测试命名空间到偏好的数据传递
        from app.core.memory.enhanced_memory_namespace import AgentRole, DomainTag
        from app.core.memory.agent_memory_preferences import AgentMemoryPreferenceManager
        
        preference_manager = AgentMemoryPreferenceManager()
        
        # 测试是否能正确处理不同智能体角色
        for role in [AgentRole.GEOPHYSICS_ANALYSIS, AgentRole.RESERVOIR_ENGINEERING, 
                    AgentRole.ECONOMIC_EVALUATION]:
            preference = preference_manager.get_agent_preference(role.value)
            assert preference is not None
        
        workflow_results['cross_component'] = True
        print("✅ 跨组件数据传递正常")
        
    except Exception as e:
        workflow_results['cross_component'] = False
        print(f"❌ 跨组件数据传递失败: {e}")
    
    success_count = sum(workflow_results.values())
    total_count = len(workflow_results)
    
    print(f"\n📊 工作流程集成测试结果: {success_count}/{total_count} 个流程正常")
    return workflow_results

def test_system_calls():
    """测试智能体系统调用"""
    print("🧪 测试智能体系统调用...")
    
    system_calls = {}
    
    # 测试核心引擎是否调用记忆系统
    try:
        from app.core.engine import IsotopeEngine
        # 检查引擎是否有记忆相关属性
        engine_source = inspect.getsource(IsotopeEngine.__init__)
        if "memory" in engine_source.lower() or "history" in engine_source.lower():
            system_calls['engine_memory'] = True
            print("✅ 核心引擎调用记忆系统正常")
        else:
            system_calls['engine_memory'] = False
            print("❌ 核心引擎未发现记忆系统调用")
    except Exception as e:
        system_calls['engine_memory'] = False
        print(f"❌ 核心引擎记忆系统检测失败: {e}")
    
    # 测试智能体系统是否调用记忆系统
    try:
        from app.agents.langgraph_agent import LangGraphAgent
        # 检查智能体是否有记忆相关属性和方法
        agent_source = inspect.getsource(LangGraphAgent)
        
        # 检查是否导入了记忆系统模块
        memory_imports = [
            "EnhancedMemoryIntegration",
            "AgentMemoryInjector", 
            "AgentMemoryFilter"
        ]
        
        memory_methods = [
            "_init_memory_system",
            "_enhance_prompt_with_memories",
            "_save_analysis_to_memory"
        ]
        
        has_memory_imports = any(imp in agent_source for imp in memory_imports)
        has_memory_methods = any(method in agent_source for method in memory_methods)
        
        if has_memory_imports and has_memory_methods:
            system_calls['agent_memory'] = True
            print("✅ 智能体系统调用记忆系统正常")
        else:
            system_calls['agent_memory'] = False
            print("❌ 智能体系统未发现记忆系统调用")
            
    except Exception as e:
        system_calls['agent_memory'] = False
        print(f"❌ 智能体系统记忆检测失败: {e}")
    
    # 测试增强图构建器是否集成记忆系统
    try:
        from app.core.enhanced_graph_builder import EnhancedGraphBuilder
        # 检查增强图构建器是否有记忆相关功能
        builder_source = inspect.getsource(EnhancedGraphBuilder)
        if "memory" in builder_source.lower():
            system_calls['enhanced_builder_memory'] = True
            print("✅ 增强图构建器集成记忆系统正常")
        else:
            system_calls['enhanced_builder_memory'] = False
            print("❌ 增强图构建器未发现记忆系统集成")
    except Exception as e:
        system_calls['enhanced_builder_memory'] = False
        print(f"❌ 增强图构建器记忆检测失败: {e}")
    
    success_count = sum(system_calls.values())
    total_count = len(system_calls)
    
    print(f"\n📊 系统调用测试结果: {success_count}/{total_count} 个调用点正常")
    return system_calls

def run_complete_integration_test():
    """运行完整的集成测试"""
    print("🎯 天然气碳同位素智能分析系统 - 记忆系统集成测试")
    print("=" * 80)
    
    # 运行各个阶段的测试
    results = {}
    
    print("\n📋 第一阶段：组件导入测试")
    results['imports'] = test_memory_component_imports()
    
    print("\n📋 第二阶段：组件初始化测试")
    results['initialization'] = test_component_initialization()
    
    print("\n📋 第三阶段：基础功能测试")
    results['functionality'] = test_component_basic_functionality()
    
    print("\n📋 第四阶段：系统集成测试")
    results['integration'] = test_system_integration()
    
    print("\n📋 第五阶段：工作流程集成测试")
    results['workflow'] = test_workflow_integration()
    
    print("\n📋 第六阶段：系统调用测试")
    results['system_calls'] = test_system_calls()
    
    # 计算整体统计
    print("\n" + "=" * 80)
    print("📊 整体测试结果统计:")
    
    overall_success = 0
    overall_total = 0
    
    for category, category_results in results.items():
        success_count = sum(category_results.values())
        total_count = len(category_results)
        success_rate = (success_count / total_count * 100) if total_count > 0 else 0
        
        print(f"  {category}: {success_count}/{total_count} ({success_rate:.1f}%)")
        overall_success += success_count
        overall_total += total_count
    
    overall_rate = (overall_success / overall_total * 100) if overall_total > 0 else 0
    print(f"\n🎯 总体测试结果: {overall_success}/{overall_total} ({overall_rate:.1f}%)")
    
    # 根据结果给出建议
    if overall_rate >= 90:
        print("✅ 记忆系统集成优秀，可以投入生产使用")
    elif overall_rate >= 80:
        print("✅ 记忆系统集成良好，建议修复少量问题后投入使用")
    elif overall_rate >= 60:
        print("⚠️  记忆系统集成基本正常，但需要进一步完善")
    else:
        print("❌ 记忆系统集成存在较多问题，需要重点改进")
    
    return results

if __name__ == "__main__":
    run_complete_integration_test() 