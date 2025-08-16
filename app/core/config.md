# 配置管理模块 (config.py)

配置管理模块是天然气碳同位素数据解释智能体系统的核心组件之一，负责系统配置的加载、访问和环境变量的管理。该模块提供了灵活的配置方案，支持不同格式的配置文件和环境变量的管理。

## 主要组件

### 1. 配置管理器 (ConfigManager)

`ConfigManager` 类负责配置文件的加载、访问和更新，提供以下主要功能：

- 加载配置文件（支持YAML和JSON格式）
- 获取不同类别的配置（模型、工具、UI等）
- 更新配置
- 保存配置到文件
- 获取环境变量

配置结构采用分层设计，包括：

```python
{
    "model": {
        "provider": "openai",
        "model_name": "gpt-4o",
        "temperature": 0.7,
        "max_tokens": 4000,
        "top_p": 1.0,
        "timeout": 120
    },
    "tools": {
        "enabled": ["file_reader", "isotope_calculator", "data_visualizer"],
        "default_timeout": 30
    },
    "ui": {
        "theme": "light",
        "chat_history_limit": 50,
        "show_debug_info": False,
        "default_language": "zh-CN"
    },
    "system": {
        "log_level": "INFO",
        "max_history_messages": 100,
        "checkpoint_interval": 5,
        "data_dir": "data"
    }
}
```

### 2. 环境管理器 (EnvironmentManager)

`EnvironmentManager` 类负责环境变量的加载和验证，提供以下主要功能：

- 加载 `.env` 文件
- 设置环境变量
- 验证环境变量是否正确设置
- 获取环境变量信息

系统使用的环境变量包括：

1. **必需环境变量**:
   - `OPENAI_API_KEY` - OpenAI API密钥
   - `ISOTOPE_DATA_PATH` - 同位素数据存储路径

2. **可选环境变量**:
   - `LOG_LEVEL` - 日志级别（DEBUG, INFO, WARNING, ERROR）
   - `MODEL_PROVIDER` - 模型提供商（openai, azure等）
   - `MODEL_NAME` - 模型名称
   - `PROXY_URL` - 代理服务器URL

## 使用示例

### 1. 基本配置加载和访问

```python
from app.core.config import ConfigManager

# 创建配置管理器
config_manager = ConfigManager()

# 加载配置
config = config_manager.load_config()

# 访问配置
model_config = config_manager.get_model_config()
print(f"使用模型: {model_config['provider']}/{model_config['model_name']}")

# 使用点路径访问嵌套配置
temperature = config_manager.get_config_value("model.temperature")
print(f"温度设置: {temperature}")

# 更新配置
config_manager.update_config("model.temperature", 0.5)
```

### 2. 自定义配置文件

```python
from app.core.config import ConfigManager

# 指定配置目录
config_manager = ConfigManager("./custom_config")

# 加载特定配置文件
config = config_manager.load_config("./custom_config/production.yaml")

# 保存配置
config_manager.update_config("model.max_tokens", 8000)
config_manager.save_config("./custom_config/updated_config.yaml")
```

### 3. 环境变量管理

```python
from app.core.config import EnvironmentManager

# 创建环境管理器
env_manager = EnvironmentManager()

# 加载环境变量
env_manager.setup_environment()

# 验证环境变量
missing_vars = env_manager.validate_environment()
if missing_vars:
    print(f"缺少必需的环境变量: {', '.join(missing_vars)}")
    print("请在.env文件中设置这些变量")

# 获取所有OpenAI相关环境变量
openai_vars = config_manager.get_environment_variables("OPENAI_")
```

## 配置与环境变量优先级

系统使用以下优先级处理配置：

1. 命令行参数（如果提供）
2. 环境变量
3. 配置文件
4. 默认值

这确保了系统可以灵活适应不同的运行环境，同时保持了配置的一致性和可追踪性。

## 最佳实践

1. **使用配置文件** - 对于稳定的配置，使用配置文件存储
2. **使用环境变量** - 对于敏感信息（API密钥等）和环境特定的设置，使用环境变量
3. **版本控制** - 将配置模板（不含敏感信息）纳入版本控制
4. **配置分离** - 将开发、测试和生产环境的配置分开

## 扩展

配置管理模块设计为可扩展的：

1. 支持添加新的配置类别
2. 支持不同格式的配置文件
3. 可集成第三方配置管理服务

通过良好的配置管理，系统可以在不同环境中保持一致的行为，同时适应不同的部署场景和用户需求。 