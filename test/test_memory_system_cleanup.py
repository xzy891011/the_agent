#!/usr/bin/env python3
"""
记忆系统清理验证测试
验证更新后的记忆系统是否正常工作
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import MagicMock, patch, Mock
from app.core.memory.enhanced_memory_integration import EnhancedMemoryIntegration
from app.core.memory.engine_adapter import MemoryAwareEngineAdapter
from app.core.critic_node import CriticNode
from app.core.engine import IsotopeEngine
from app.core.config import ConfigManager
import time


def create_mock_llm():
    """创建模拟的LLM"""
    mock_llm = MagicMock()
    mock_llm.invoke = MagicMock(return_value=MagicMock(content="测试响应"))
    return mock_llm


def create_real_config_manager():
    """创建真实的配置管理器"""
    config_manager = ConfigManager()
    try:
        # 尝试加载配置文件
        config_manager.load_config()
        print(f"✅ 加载配置文件成功")
    except Exception as e:
        print(f"⚠️ 配置文件加载失败: {e}，使用默认配置")
        # 使用默认配置
        config_manager.config = config_manager.default_config.copy()
    
    # 确保测试环境的配置适合测试
    # 为测试环境调整一些参数
    test_adjustments = {
        "memory.enabled": True,
        "memory.semantic_enabled": True,
        "memory.episodic_enabled": True,
        "es.index_name": "test_memories",  # 使用测试索引
        "es.username": "elastic",  # 确保有用户名
        "postgresql.database": "isotope",  # 使用测试数据库
        "system.log_level": "INFO"
    }
    
    for key_path, value in test_adjustments.items():
        config_manager.update_config(key_path, value)
    
    print(f"✅ 真实配置管理器创建完成")
    return config_manager


class TestMemorySystemCleanup:
    """测试记忆系统清理后的功能"""

    def test_enhanced_memory_integration_creation(self):
        """测试增强记忆集成创建"""
        print("🧪 测试增强记忆集成创建")
        
        with patch('elasticsearch.Elasticsearch') as mock_es:
            # 模拟ES连接
            mock_es.return_value.ping.return_value = True
            
            # 使用真实的配置管理器
            config_manager = create_real_config_manager()
            
            # 创建增强记忆集成
            from app.core.memory.enhanced_memory_integration import create_enhanced_memory_integration
            
            enhanced_integration = create_enhanced_memory_integration(config_manager)
            
            # 验证创建成功
            assert enhanced_integration is not None
            assert hasattr(enhanced_integration, 'enhance_state_with_agent_memories')
            assert hasattr(enhanced_integration, 'save_agent_interaction_memory')
            
            print("✅ 增强记忆集成创建成功")

    def test_memory_aware_adapter_creation(self):
        """测试记忆感知适配器创建"""
        print("🧪 测试记忆感知适配器创建")
        
        with patch('elasticsearch.Elasticsearch') as mock_es:
            mock_es.return_value.ping.return_value = True
            
            # 使用真实的配置管理器
            config_manager = create_real_config_manager()
            
            # 创建记忆感知适配器
            from app.core.memory.engine_adapter import create_memory_aware_adapter
            
            adapter = create_memory_aware_adapter(config_manager)
            
            # 验证创建成功
            assert adapter is not None
            assert hasattr(adapter, 'enhanced_memory_integration')
            assert hasattr(adapter, 'pre_execution_hook')
            assert hasattr(adapter, 'post_execution_hook')
            assert hasattr(adapter, 'session_end_hook')
            
            print("✅ 记忆感知适配器创建成功")

    def test_critic_node_with_enhanced_memory(self):
        """测试Critic节点使用增强记忆"""
        print("🧪 测试Critic节点使用增强记忆")
        
        with patch('elasticsearch.Elasticsearch') as mock_es:
            mock_es.return_value.ping.return_value = True
            
            # 使用真实的配置管理器
            config_manager = create_real_config_manager()
            llm = create_mock_llm()
            
            # 创建Critic节点，传入配置字典而不是ConfigManager
            critic = CriticNode(
                llm=llm,
                config=config_manager.config,  # 传入配置字典
                enable_rag_review=True
            )
            
            # 验证增强记忆初始化
            assert critic.enhanced_memory_integration is not None
            assert hasattr(critic.enhanced_memory_integration, 'enhance_state_with_agent_memories')
            
            print("✅ Critic节点增强记忆初始化成功")

    def test_engine_enhanced_memory_integration(self):
        """测试Engine增强记忆集成"""
        print("🧪 测试Engine增强记忆集成")
        
        with patch('elasticsearch.Elasticsearch') as mock_es:
            mock_es.return_value.ping.return_value = True
            
            # 使用真实的配置管理器
            config_manager = create_real_config_manager()
            
            # 创建Engine，传入配置字典
            engine = IsotopeEngine(config=config_manager.config)
            
            # 验证增强记忆系统存在
            assert hasattr(engine, 'enhanced_memory_integration')
            assert engine.enhanced_memory_integration is not None
            
            print("✅ Engine增强记忆集成成功")

    def test_memory_functionality_chain(self):
        """测试记忆功能链"""
        print("🧪 测试记忆功能链")
        
        with patch('elasticsearch.Elasticsearch') as mock_es:
            mock_es.return_value.ping.return_value = True
            
            # 使用真实的配置管理器
            config_manager = create_real_config_manager()
            
            # 创建Engine，传入配置字典
            engine = IsotopeEngine(config=config_manager.config)
            
            # 测试记忆保存
            session_id = "test_session"
            content = "测试记忆内容"
            
            memory_id = engine.add_to_memory(session_id, content, "semantic")
            assert memory_id is not None
            
            # 测试记忆检索
            memories = engine.get_relevant_memories(session_id, "测试", 3)
            assert isinstance(memories, list)
            
            print("✅ 记忆功能链测试成功")

    def test_deprecated_imports_compatibility(self):
        """测试弃用模块的兼容性"""
        print("🧪 测试弃用模块的兼容性")
        
        # 测试主要导出仍然可用
        from app.core.memory import (
            EnhancedMemoryIntegration,
            MemoryAwareEngineAdapter,
            MemoryStore,  # 传统存储仍然可用
            create_enhanced_memory_integration,
            create_memory_aware_adapter
        )
        
        # 验证导入成功
        assert EnhancedMemoryIntegration is not None
        assert MemoryAwareEngineAdapter is not None
        assert MemoryStore is not None
        assert create_enhanced_memory_integration is not None
        assert create_memory_aware_adapter is not None
        
        print("✅ 弃用模块兼容性测试成功")

    def test_memory_system_version_info(self):
        """测试记忆系统版本信息"""
        print("🧪 测试记忆系统版本信息")
        
        from app.core.memory import __version__, __stage__
        
        # 验证版本信息
        assert __version__ == "4.0.0"
        assert "Enhanced Memory System" in __stage__
        
        print(f"✅ 记忆系统版本: {__version__}")
        print(f"✅ 记忆系统阶段: {__stage__}")

    def test_real_config_integration(self):
        """测试真实配置集成"""
        print("🧪 测试真实配置集成")
        
        # 创建真实配置管理器
        config_manager = create_real_config_manager()
        
        # 验证配置完整性
        assert config_manager.config is not None
        
        # 验证关键配置项存在
        memory_config = config_manager.get_memory_config()
        assert memory_config is not None
        assert "semantic_enabled" in memory_config
        assert "episodic_enabled" in memory_config
        
        es_config = config_manager.get_es_config()
        assert es_config is not None
        assert "hosts" in es_config
        
        postgresql_config = config_manager.get_postgresql_config()
        assert postgresql_config is not None
        assert "host" in postgresql_config
        assert "database" in postgresql_config
        
        print("✅ 真实配置集成测试成功")

    def test_database_configs_validity(self):
        """测试数据库配置有效性"""
        print("🧪 测试数据库配置有效性")
        
        config_manager = create_real_config_manager()
        
        # 测试PostgreSQL配置
        pg_config = config_manager.get_postgresql_config()
        required_pg_fields = ["host", "port", "database", "user", "password"]
        for field in required_pg_fields:
            assert field in pg_config, f"PostgreSQL配置缺少必需字段: {field}"
            assert pg_config[field] is not None, f"PostgreSQL配置字段{field}为空"
        
        # 测试MySQL配置
        mysql_config = config_manager.get_mysql_config()
        required_mysql_fields = ["host", "port", "database", "user", "password"]
        for field in required_mysql_fields:
            assert field in mysql_config, f"MySQL配置缺少必需字段: {field}"
            assert mysql_config[field] is not None, f"MySQL配置字段{field}为空"
        
        # 测试Elasticsearch配置
        es_config = config_manager.get_es_config()
        assert "hosts" in es_config
        assert isinstance(es_config["hosts"], list)
        assert len(es_config["hosts"]) > 0
        
        print("✅ 数据库配置有效性测试成功")


def main():
    """主函数"""
    print("🔧 记忆系统清理验证测试")
    print("=" * 50)
    
    test_class = TestMemorySystemCleanup()
    
    tests = [
        test_class.test_enhanced_memory_integration_creation,
        test_class.test_memory_aware_adapter_creation,
        test_class.test_critic_node_with_enhanced_memory,
        test_class.test_engine_enhanced_memory_integration,
        test_class.test_memory_functionality_chain,
        test_class.test_deprecated_imports_compatibility,
        test_class.test_memory_system_version_info,
        test_class.test_real_config_integration,
        test_class.test_database_configs_validity
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} 失败: {e}")
            import traceback
            traceback.print_exc()
    
    print("=" * 50)
    print(f"测试结果: {passed}/{total} ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 所有测试通过！记忆系统清理成功！")
    else:
        print("⚠️  部分测试失败，需要进一步检查")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 