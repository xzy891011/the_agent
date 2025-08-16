#!/usr/bin/env python3
"""
错误修复验证测试
验证修复后的记忆系统错误
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import MagicMock, patch
from app.core.engine import IsotopeEngine
from app.agents.langgraph_agent import LangGraphAgent
from app.core.memory.enhanced_memory_integration import EnhancedMemoryIntegration
import time


class TestErrorFixes:
    """测试错误修复"""
    
    def test_engine_memory_retrieval_fix(self):
        """测试Engine记忆检索修复"""
        # 创建模拟的引擎和记忆系统
        config = {
            "memory": {
                "enabled": True,
                "es_config": {
                    "hosts": ["http://localhost:9200"],
                    "index_name": "test_memories"
                }
            }
        }
        
        engine = IsotopeEngine(config=config, verbose=True)
        
        # 模拟增强记忆系统
        mock_memory_integration = MagicMock()
        mock_memory_context = MagicMock()
        mock_memory_context.semantic_memories = [
            MagicMock(content="语义记忆1"),
            MagicMock(content="语义记忆2")
        ]
        mock_memory_context.episodic_memories = [
            MagicMock(content="情节记忆1")
        ]
        mock_memory_context.procedural_memories = [
            MagicMock(content="程序记忆1")
        ]
        
        mock_memory_integration.enhance_state_with_agent_memories.return_value = mock_memory_context
        engine.enhanced_memory_integration = mock_memory_integration
        
        # 测试记忆检索
        memories = engine.get_relevant_memories("test_session", "碳同位素分析", 3)
        
        # 验证结果：由于取了前3个，所以应该是3个
        assert len(memories) == 3
        assert "语义记忆1" in memories
        assert "语义记忆2" in memories
        assert "情节记忆1" in memories
        
        # 验证参数传递
        mock_memory_integration.enhance_state_with_agent_memories.assert_called_once()
        args, kwargs = mock_memory_integration.enhance_state_with_agent_memories.call_args
        assert kwargs['agent_role'] == 'system'
        assert kwargs['query'] == '碳同位素分析'
        assert kwargs['max_memories'] == {'semantic': 3, 'episodic': 3, 'procedural': 3}
    
    def test_langgraph_agent_memory_enhancement_fix(self):
        """测试LangGraph智能体记忆增强修复"""
        # 创建模拟的智能体
        mock_llm = MagicMock()
        
        config = {
            "memory": {"enabled": True}
        }
        
        agent = LangGraphAgent(
            name="测试智能体",
            role="data_analyst",
            llm=mock_llm,
            config=config
        )
        
        # 模拟记忆系统
        mock_memory_integration = MagicMock()
        mock_memory_context = MagicMock()
        mock_memory_context.confidence_score = 0.8
        mock_memory_context.semantic_memories = [
            MagicMock(content="相关语义记忆内容")
        ]
        mock_memory_context.episodic_memories = []
        mock_memory_context.procedural_memories = []
        mock_memory_context.memory_summary = "测试记忆摘要"
        
        mock_memory_integration.enhance_state_with_agent_memories.return_value = mock_memory_context
        agent.memory_integration = mock_memory_integration
        
        # 测试记忆增强
        state = {
            "metadata": {
                "user_id": "test_user",
                "session_id": "test_session"
            },
            "messages": []
        }
        
        enhanced_prompt = agent._enhance_prompt_with_memories("分析碳同位素数据", state)
        
        # 验证结果
        assert enhanced_prompt is not None
        assert "相关语义记忆内容" in enhanced_prompt
        assert "测试记忆摘要" in enhanced_prompt
        
        # 验证方法调用
        mock_memory_integration.enhance_state_with_agent_memories.assert_called_once()
        args, kwargs = mock_memory_integration.enhance_state_with_agent_memories.call_args
        assert kwargs['agent_role'] == 'data_analyst'
        assert kwargs['query'] == '分析碳同位素数据'
    
    def test_memory_saving_fix(self):
        """测试记忆保存修复"""
        # 创建模拟的智能体
        mock_llm = MagicMock()
        
        config = {
            "memory": {"enabled": True}
        }
        
        agent = LangGraphAgent(
            name="测试智能体",
            role="data_analyst",
            llm=mock_llm,
            config=config
        )
        
        # 模拟记忆系统
        mock_memory_integration = MagicMock()
        mock_memory_integration.save_agent_interaction_memory.return_value = "memory_id_123"
        agent.memory_integration = mock_memory_integration
        
        # 测试记忆保存
        state = {
            "metadata": {
                "user_id": "test_user",
                "session_id": "test_session"
            },
            "messages": []
        }
        
        analysis = {
            "tasks_to_execute": [
                {"task_name": "test_task", "parameters": {}}
            ],
            "reasoning": "测试推理过程"
        }
        
        # 调用保存方法
        agent._save_analysis_to_memory(state, analysis)
        
        # 验证方法调用
        mock_memory_integration.save_agent_interaction_memory.assert_called_once()
        args, kwargs = mock_memory_integration.save_agent_interaction_memory.call_args
        assert kwargs['agent_role'] == 'data_analyst'
        assert kwargs['session_id'] == 'test_session'
        assert "智能体 测试智能体 分析结果" in kwargs['interaction_summary']
    
    def test_memory_context_parameter_fix(self):
        """测试记忆上下文参数修复"""
        # 创建记忆集成实例
        config = {
            "memory": {
                "enabled": True,
                "es_config": {
                    "hosts": ["http://localhost:9200"],
                    "index_name": "test_memories"
                }
            }
        }
        
        # 模拟增强记忆存储
        with patch('app.core.memory.enhanced_memory_integration.create_enhanced_langgraph_store') as mock_store:
            mock_store_instance = MagicMock()
            mock_store.return_value = mock_store_instance
            
            # 模拟记忆上下文返回值
            mock_store_instance.get_agent_memory_context.return_value = {
                'semantic': [MagicMock(content="语义记忆")],
                'episodic': [MagicMock(content="情节记忆")],
                'procedural': [MagicMock(content="程序记忆")]
            }
            
            memory_integration = EnhancedMemoryIntegration(config)
            
            # 测试状态
            state = {
                "metadata": {
                    "user_id": "test_user",
                    "session_id": "test_session"
                },
                "messages": []
            }
            
            # 调用增强方法
            result = memory_integration.enhance_state_with_agent_memories(
                state=state,
                agent_role="data_analyst",
                query="测试查询",
                max_memories={'semantic': 2, 'episodic': 2, 'procedural': 2}
            )
            
            # 验证结果
            assert result is not None
            assert result.agent_role == "data_analyst"
            assert len(result.semantic_memories) == 1
            assert len(result.episodic_memories) == 1
            assert len(result.procedural_memories) == 1
    
    def test_integration_without_errors(self):
        """测试完整集成不会报错"""
        # 创建完整的Engine实例
        config = {
            "memory": {
                "enabled": True,
                "es_config": {
                    "hosts": ["http://localhost:9200"],
                    "index_name": "test_memories"
                }
            }
        }
        
        try:
            # 创建Engine
            engine = IsotopeEngine(config=config, verbose=True)
            
            # 测试记忆检索（应该不会报错）
            memories = engine.get_relevant_memories("test_session", "测试查询", 3)
            
            # 验证没有异常
            assert isinstance(memories, list)
            print("✅ Engine记忆检索测试通过")
            
        except Exception as e:
            print(f"❌ Engine记忆检索测试失败: {e}")
            raise
        
        try:
            # 创建智能体
            mock_llm = MagicMock()
            agent = LangGraphAgent(
                name="测试智能体",
                role="data_analyst",
                llm=mock_llm,
                config=config
            )
            
            # 测试记忆增强（应该不会报错）
            state = {
                "metadata": {
                    "user_id": "test_user",
                    "session_id": "test_session"
                },
                "messages": []
            }
            
            enhanced_prompt = agent._enhance_prompt_with_memories("测试查询", state)
            
            # 验证没有异常
            print("✅ 智能体记忆增强测试通过")
            
        except Exception as e:
            print(f"❌ 智能体记忆增强测试失败: {e}")
            raise


def run_error_fixes_test():
    """运行错误修复测试"""
    print("=" * 50)
    print("错误修复验证测试")
    print("=" * 50)
    
    test_suite = TestErrorFixes()
    
    tests = [
        ("Engine记忆检索修复", test_suite.test_engine_memory_retrieval_fix),
        ("智能体记忆增强修复", test_suite.test_langgraph_agent_memory_enhancement_fix),
        ("记忆保存修复", test_suite.test_memory_saving_fix),
        ("记忆上下文参数修复", test_suite.test_memory_context_parameter_fix),
        ("完整集成测试", test_suite.test_integration_without_errors)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            print(f"\n🔍 {test_name}...")
            test_func()
            print(f"✅ {test_name} 通过")
            passed += 1
        except Exception as e:
            print(f"❌ {test_name} 失败: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*50}")
    print(f"测试结果: {passed}/{total} ({passed/total*100:.1f}%)")
    print(f"{'='*50}")
    
    return passed == total


if __name__ == "__main__":
    success = run_error_fixes_test()
    sys.exit(0 if success else 1) 