"""
代码生成和执行工具 - 使用LLM生成Python代码并安全执行

该模块提供以下功能:
1. 基于用户需求使用LLM生成Python代码
2. 安全执行生成的代码
3. 集成LangGraph流式输出，实时展示代码生成和执行过程
"""

import os
import sys
import tempfile
import logging
import uuid
import json
import time
import subprocess
import traceback
from typing import Dict, List, Any, Optional, Union, Callable, Tuple
from enum import Enum
from pathlib import Path
import importlib.util
import io
import contextlib
import inspect
import locale

# 导入LangGraph相关组件
from langgraph.config import get_stream_writer

# 导入LangChain相关组件
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 导入项目内模块
from app.tools.registry import register_tool
from app.tools.schemas import GenerateCodeSchema, ExecuteCodeSchema, CodeAssistantSchema
try:
    from app.utils.qwen_chat import SFChatOpenAI
except ImportError:
    # 创建一个模拟的LLM类，用于在没有真实LLM时使用
    from langchain_core.language_models.llms import BaseLLM
    class MockLLM(BaseLLM):
        def _call(self, prompt, **kwargs):
            return "模拟代码输出 - LLM未初始化"
            
        def _generate(self, prompts, **kwargs):
            return "模拟代码输出 - LLM未初始化"
    
    SFChatOpenAI = MockLLM

try:
    from app.core.state import StateManager
except ImportError:
    # 如果没有StateManager，创建一个简单的占位实现
    class StateManager:
        @staticmethod
        def update_messages(state, message):
            return state

# 配置日志
logger = logging.getLogger(__name__)

# 定义代码执行安全级别
class CodeSafetyLevel(str, Enum):
    """代码安全级别枚举"""
    LOW = "low"            # 低安全级别，几乎无限制
    MEDIUM = "medium"      # 中等安全级别，限制部分系统操作
    HIGH = "high"          # 高安全级别，严格限制文件和网络操作
    SANDBOX = "sandbox"    # 沙箱模式，隔离执行环境

# 定义系统消息模板
CODE_GENERATION_SYSTEM_PROMPT = """你是一位专业的Python代码生成助手。
你的任务是根据用户的需求生成有效、安全且高质量的Python代码。

请遵循以下规则：
1. 代码必须是完整且可直接执行的
2. 必须包含所有必要的导入语句
3. 提供全面的代码注释
4. 使用明确的变量名和函数名
5. 错误处理必须完善
6. 所有文件路径必须使用相对路径或完整的绝对路径
7. 代码逻辑必须清晰，分步骤执行
8. 代码完成后必须有明确的输出，表明任务的完成状态
9. 不要包含任何伪代码或不完整的代码片段
10. 所有参数设置必须在代码中明确定义，不能依赖外部输入

请直接输出完整的Python代码，不要有其他解释。我将直接执行你生成的代码。
"""

# 代码安全限制列表
RESTRICTED_MODULES = {
    "high": [
        "os.system", "subprocess", "shutil.rmtree", "eval", "exec", 
        "pty", "pexpect", "socket", "requests.delete", "rmtree", "remove"
    ],
    "medium": [
        "os.system", "subprocess.call", "subprocess.run", "eval", "exec"
    ],
    "low": [
        "os.system"  # 仅禁止直接系统调用
    ]
}

# 为测试环境创建模拟代码示例
MOCK_CODE_SAMPLE = """
import random
import time
from datetime import datetime

# 生成10个随机数
numbers = [random.randint(1, 100) for _ in range(10)]
average = sum(numbers) / len(numbers)

# 打印结果
print(f"生成的随机数: {numbers}")
print(f"平均值: {average:.2f}")
print(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# 保存到文件
with open('random_numbers.txt', 'w') as f:
    f.write(f"随机数列表: {numbers}\\n")
    f.write(f"平均值: {average:.2f}\\n")
    f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n")

print("结果已保存到 random_numbers.txt")
"""

def safe_get_stream_writer():
    """安全获取流写入器
    
    如果不在LangGraph上下文中，返回None
    
    Returns:
        流写入器或None
    """
    try:
        return get_stream_writer()
    except RuntimeError:
        return None

class StreamWriterProxy:
    """流写入器代理，用于在不同环境中统一流式输出处理"""
    
    def __init__(self, verbose: bool = True):
        """初始化流写入器代理
        
        Args:
            verbose: 是否启用详细输出
        """
        self.verbose = verbose
        # 尝试获取LangGraph流写入器
        self.writer = safe_get_stream_writer()
        # 设置备用输出方法
        self.fallback_output = []
    
    def __call__(self, data: Dict[str, Any]) -> None:
        """调用流写入器
        
        Args:
            data: 要写入的数据
        """
        # 如果有LangGraph流写入器，优先使用
        if self.writer:
            self.writer(data)
        elif self.verbose:
            # 备用方式：打印到控制台
            if "custom_step" in data:
                message = f"[代码执行器] {data['custom_step']}"
                print(message)
                self.fallback_output.append(data)
            elif "agent_thinking" in data:
                message = f"[思考] {data['agent_thinking']}"
                print(message)
                self.fallback_output.append(data)
    
    def get_output(self) -> List[Dict[str, Any]]:
        """获取备用输出
        
        Returns:
            备用输出列表
        """
        return self.fallback_output

class CodeExecutionResult:
    """代码执行结果类"""
    
    def __init__(
        self, 
        success: bool, 
        output: str, 
        error: Optional[str] = None,
        execution_time: float = 0.0,
        generated_files: Optional[List[str]] = None
    ):
        """初始化代码执行结果
        
        Args:
            success: 执行是否成功
            output: 标准输出内容
            error: 错误信息，如果有
            execution_time: 执行时间（秒）
            generated_files: 生成的文件列表
        """
        self.success = success
        self.output = output
        self.error = error
        self.execution_time = execution_time
        self.generated_files = generated_files or []
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示
        
        Returns:
            结果字典
        """
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "execution_time": f"{self.execution_time:.2f}秒",
            "generated_files": self.generated_files
        }
    
    def __str__(self) -> str:
        """字符串表示
        
        Returns:
            格式化的结果字符串
        """
        if self.success:
            result = f"✅ 代码执行成功 (耗时: {self.execution_time:.2f}秒)\n\n"
            result += f"输出:\n{self.output}\n"
            if self.generated_files:
                result += f"\n生成的文件:\n" + "\n".join(f"- {f}" for f in self.generated_files)
        else:
            result = f"❌ 代码执行失败 (耗时: {self.execution_time:.2f}秒)\n\n"
            result += f"错误:\n{self.error}\n"
            if self.output:
                result += f"\n部分输出:\n{self.output}"
        
        return result

class CodeExecutor:
    """代码生成和执行器
    
    负责生成和安全执行Python代码
    """
    
    def __init__(
        self, 
        llm: Optional[Any] = None,
        safety_level: CodeSafetyLevel = CodeSafetyLevel.MEDIUM,
        working_dir: Optional[str] = None,
        timeout: int = 60,
        mock_mode: bool = False
    ):
        """初始化代码执行器
        
        Args:
            llm: 用于代码生成的语言模型，如果为None则创建默认模型
            safety_level: 代码执行安全级别
            working_dir: 代码执行工作目录，如果为None则使用临时目录
            timeout: 代码执行超时时间（秒）
            mock_mode: 是否启用模拟模式，无需真实LLM
        """
        self.mock_mode = mock_mode
        if not mock_mode:
            self.llm = llm or self._create_default_llm()
        else:
            self.llm = None
            logger.info("代码执行器以模拟模式初始化")
            
        self.safety_level = safety_level
        self.working_dir = working_dir or os.getcwd()
        self.timeout = timeout
        
        # 确保工作目录存在
        os.makedirs(self.working_dir, exist_ok=True)
        
        logger.info(f"代码执行器初始化完成，安全级别: {safety_level}")
    
    def _create_default_llm(self) -> Any:
        """创建默认的语言模型
        
        Returns:
            默认配置的语言模型
        """
        try:
            # 使用项目中已有的LLM实现
            llm = SFChatOpenAI(
                model="Qwen/Qwen2.5-72B-Instruct", 
                temperature=0.2,  # 低温度值，生成更确定性的代码
                request_timeout=120,
                model_kwargs={"tool_choice": "auto"}
            )
            logger.info("创建默认代码生成LLM: Qwen2.5-72B-Instruct")
            return llm
        except Exception as e:
            logger.warning(f"创建默认LLM失败: {str(e)}，将使用模拟模式")
            self.mock_mode = True
            return None
    
    def generate_code(self, task_description: str) -> str:
        """生成Python代码
        
        Args:
            task_description: 任务描述
            
        Returns:
            生成的Python代码
        """
        # 创建流写入器代理
        writer = StreamWriterProxy()
        
        writer({"custom_step": "开始生成代码..."})
        writer({"custom_step": f"任务描述: {task_description}"})
        
        # 如果处于模拟模式，返回示例代码
        if self.mock_mode or self.llm is None:
            writer({"custom_step": "模拟模式下生成代码..."})
            time.sleep(1)  # 模拟延迟
            writer({"custom_step": "代码生成完成"})
            return MOCK_CODE_SAMPLE
        
        try:
            # 构建提示
            prompt = ChatPromptTemplate.from_messages([
                ("system", CODE_GENERATION_SYSTEM_PROMPT),
                ("human", f"请为我生成Python代码，完成以下任务:\n\n{task_description}\n\n只需要输出可执行的Python代码，不要有任何其他解释。")
            ])
            
            writer({"custom_step": "代码生成中，请稍候..."})
            
            # 调用LLM生成代码
            code_chain = prompt | self.llm | StrOutputParser()
            code = code_chain.invoke({})
            
            # 清理代码（移除Markdown格式等）
            code = self._clean_code(code)
            
            writer({"custom_step": "代码生成完成"})
            writer({"custom_step": f"代码长度: {len(code)} 字符"})
            
            logger.info(f"代码生成成功，长度: {len(code)} 字符")
            return code
        
        except Exception as e:
            error_msg = f"代码生成失败: {str(e)}"
            logger.error(error_msg)
            
            writer({"custom_step": error_msg})
            
            # 出错时返回示例代码
            writer({"custom_step": "回退到示例代码..."})
            return MOCK_CODE_SAMPLE
    
    def _clean_code(self, code: str) -> str:
        """清理生成的代码
        
        从生成的代码中移除Markdown格式、解释性文本等
        
        Args:
            code: 原始生成的代码
            
        Returns:
            清理后的代码
        """
        # 移除可能的Markdown代码块标记
        if code.startswith("```python"):
            code = code.replace("```python", "", 1)
            if code.endswith("```"):
                code = code[:-3]
        elif code.startswith("```"):
            code = code.replace("```", "", 1)
            if code.endswith("```"):
                code = code[:-3]
        
        # 清理代码
        return code.strip()
    
    def _check_code_safety(self, code: str) -> Tuple[bool, Optional[str]]:
        """检查代码安全性
        
        Args:
            code: 要检查的代码
            
        Returns:
            (是否安全, 不安全原因)
        """
        # 获取流写入器
        writer = StreamWriterProxy()
        
        writer({"custom_step": "执行代码安全检查..."})
        
        # 根据安全级别获取受限模块和函数
        restricted = RESTRICTED_MODULES.get(self.safety_level, [])
        
        # 安全性检查
        for item in restricted:
            if item in code:
                reason = f"代码包含受限内容: {item}"
                
                writer({"custom_step": f"❌ 安全性检查失败: {reason}"})
                
                return False, reason
        
        # 沙箱模式下的额外检查
        if self.safety_level == CodeSafetyLevel.SANDBOX:
            # 检查文件操作
            if "open(" in code and ("'w'" in code or '"w"' in code or "'a'" in code or '"a"' in code):
                reason = "沙箱模式下不允许写入文件"
                
                writer({"custom_step": f"❌ 安全性检查失败: {reason}"})
                
                return False, reason
        
        writer({"custom_step": "✅ 代码安全性检查通过"})
            
        return True, None
    
    def _get_generated_files(self, base_dir: str, before_files: List[str]) -> List[str]:
        """获取代码执行过程中新生成的文件
        
        Args:
            base_dir: 基础目录
            before_files: 执行前的文件列表
            
        Returns:
            新生成的文件列表
        """
        current_files = []
        for root, _, files in os.walk(base_dir):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, base_dir)
                current_files.append(rel_path)
        
        # 找出新增的文件
        new_files = [f for f in current_files if f not in before_files]
        return new_files
    
    def execute_code(self, code: str, execution_dir: Optional[str] = None) -> CodeExecutionResult:
        """执行Python代码
        
        Args:
            code: 要执行的Python代码
            execution_dir: 代码执行目录，默认使用working_dir
            
        Returns:
            代码执行结果
        """
        # 确定执行目录
        exec_dir = execution_dir or self.working_dir
        os.makedirs(exec_dir, exist_ok=True)
        
        # 创建流写入器代理
        writer = StreamWriterProxy()
        
        writer({"custom_step": f"准备执行代码，执行目录: {exec_dir}"})
        
        # 安全检查
        is_safe, reason = self._check_code_safety(code)
        if not is_safe:
            error_msg = f"代码安全检查未通过: {reason}"
            logger.warning(error_msg)
            
            return CodeExecutionResult(
                success=False,
                output="",
                error=error_msg,
                execution_time=0.0
            )
        
        # 获取执行前的文件列表，用于后续比较找出新生成的文件
        before_files = []
        for root, _, files in os.walk(exec_dir):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, exec_dir)
                before_files.append(rel_path)
        
        # 创建临时代码文件
        script_name = f"code_execution_{uuid.uuid4().hex[:8]}.py"
        script_path = os.path.join(exec_dir, script_name)
        
        try:
            # 写入代码到文件
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)
            
            writer({"custom_step": f"代码已保存至临时文件: {script_name}"})
            writer({"custom_step": "开始执行代码..."})
            
            # 记录开始时间
            start_time = time.time()
            
            # 使用子进程执行代码（更安全）
            result = self._execute_in_subprocess(script_path, exec_dir)
            
            # 计算执行时间
            execution_time = time.time() - start_time
            
            # 获取新生成的文件
            generated_files = self._get_generated_files(exec_dir, before_files)
            
            # 构建执行结果
            execution_result = CodeExecutionResult(
                success=result["success"],
                output=result["output"],
                error=result["error"],
                execution_time=execution_time,
                generated_files=generated_files
            )
            
            if result["success"]:
                writer({"custom_step": f"✅ 代码执行成功，耗时: {execution_time:.2f}秒"})
                if generated_files:
                    writer({"custom_step": f"生成了 {len(generated_files)} 个文件: {', '.join(generated_files)}"})
            else:
                writer({"custom_step": f"❌ 代码执行失败，耗时: {execution_time:.2f}秒"})
                writer({"custom_step": f"错误信息: {result['error']}"})
            
            # 返回执行结果
            return execution_result
            
        except Exception as e:
            error_msg = f"代码执行过程出错: {str(e)}"
            logger.error(error_msg)
            traceback.print_exc()
            
            writer({"custom_step": f"❌ 执行过程出错: {str(e)}"})
            
            return CodeExecutionResult(
                success=False,
                output="",
                error=error_msg,
                execution_time=0.0
            )
        finally:
            # 根据安全级别决定是否清理临时文件
            if self.safety_level == CodeSafetyLevel.SANDBOX:
                try:
                    os.remove(script_path)
                    writer({"custom_step": f"临时代码文件已清理: {script_name}"})
                except:
                    pass
    
    def _execute_in_subprocess(self, script_path: str, cwd: str) -> Dict[str, Any]:
        """在子进程中执行Python脚本
        
        Args:
            script_path: 脚本路径
            cwd: 工作目录
            
        Returns:
            执行结果字典
        """
        try:
            # 获取系统编码
            system_encoding = locale.getpreferredencoding(False)
            
            # 在子进程中执行
            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                text=True,
                encoding=system_encoding,  # 使用系统编码
                errors='replace'  # 替换无法解码的字符
            )
            
            # 设置超时
            try:
                stdout, stderr = process.communicate(timeout=self.timeout)
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                return {
                    "success": False,
                    "output": stdout,
                    "error": f"执行超时 (超过 {self.timeout} 秒)"
                }
            
            # 检查执行结果
            if exit_code == 0:
                return {
                    "success": True,
                    "output": stdout,
                    "error": None
                }
            else:
                return {
                    "success": False,
                    "output": stdout,
                    "error": stderr
                }
                
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": f"执行过程错误: {str(e)}"
            }

# 创建一个默认的代码执行器实例 - 使用模拟模式以避免API密钥问题
try:
    default_executor = CodeExecutor()
except Exception as e:
    logger.warning(f"使用标准模式初始化代码执行器失败: {str(e)}，回退到模拟模式")
    default_executor = CodeExecutor(mock_mode=True)

@register_tool(category="code", use_structured_tool=True)
def generate_code(task_description: str) -> str:
    """生成Python代码
    
    根据任务描述，使用大模型生成Python代码。
    
    Args:
        task_description: 详细的任务描述
        
    Returns:
        生成的Python代码
    """
    # 创建流写入器代理
    writer = StreamWriterProxy()
    
    writer({"custom_step": "调用代码生成工具..."})
    
    try:
        # 使用默认执行器生成代码
        code = default_executor.generate_code(task_description)
        
        writer({"custom_step": "代码生成完成"})
            
        return f"```python\n{code}\n```"
    except Exception as e:
        error_msg = f"代码生成失败: {str(e)}"
        logger.error(error_msg)
        
        writer({"custom_step": f"❌ {error_msg}"})
            
        return f"代码生成失败: {str(e)}"

# 为generate_code工具设置schema
generate_code.args_schema = GenerateCodeSchema

@register_tool(category="code", use_structured_tool=True)
def execute_code(code: str, safety_level: str = "medium") -> str:
    """执行Python代码
    
    安全地执行提供的Python代码，并返回执行结果。
    
    Args:
        code: 要执行的Python代码
        safety_level: 安全级别，可选"low"、"medium"、"high"、"sandbox"
        
    Returns:
        代码执行结果
    """
    # 创建流写入器代理
    writer = StreamWriterProxy()
    
    writer({"custom_step": "调用代码执行工具..."})
    
    try:
        # 清理代码（移除可能的Markdown标记）
        if code.startswith("```python"):
            code = code.replace("```python", "", 1)
        elif code.startswith("```"):
            code = code.replace("```", "", 1)
            
        if code.endswith("```"):
            code = code[:-3]
        
        code = code.strip()
        
        # 验证安全级别
        if safety_level not in [e.value for e in CodeSafetyLevel]:
            safety_level = "medium"  # 默认使用中等安全级别
        
        # 创建具有指定安全级别的执行器
        try:
            executor = CodeExecutor(safety_level=safety_level)
        except Exception as e:
            logger.warning(f"创建标准代码执行器失败: {str(e)}，使用模拟模式")
            executor = CodeExecutor(safety_level=safety_level, mock_mode=True)
        
        # 执行代码
        result = executor.execute_code(code)
        
        if result.success:
            writer({"custom_step": f"✅ 代码执行成功，耗时: {result.execution_time:.2f}秒"})
        else:
            writer({"custom_step": f"❌ 代码执行失败: {result.error}"})
        
        # 返回格式化结果
        return str(result)
    
    except Exception as e:
        error_msg = f"代码执行工具调用失败: {str(e)}"
        logger.error(error_msg)
        
        writer({"custom_step": f"❌ {error_msg}"})
            
        return f"代码执行失败: {str(e)}"

# 为execute_code工具设置schema
execute_code.args_schema = ExecuteCodeSchema

@register_tool(category="code", use_structured_tool=True)
def code_assistant(task_description: str, safety_level: str = "medium") -> str:
    """代码助手工具 - 生成并执行代码
    
    根据任务描述，生成Python代码并安全执行，返回执行结果。
    这是一个集成了代码生成和执行的便捷工具。
    
    Args:
        task_description: 详细的任务描述
        safety_level: 安全级别，可选"low"、"medium"、"high"、"sandbox"
        
    Returns:
        代码执行结果
    """
    # 创建流写入器代理
    writer = StreamWriterProxy()
    
    writer({"custom_step": "调用代码助手工具..."})
    writer({"custom_step": f"任务描述: {task_description}"})
    
    try:
        # 验证安全级别
        if safety_level not in [e.value for e in CodeSafetyLevel]:
            safety_level = "medium"  # 默认使用中等安全级别
        
        # 创建执行器
        try:
            executor = CodeExecutor(safety_level=safety_level)
        except Exception as e:
            logger.warning(f"创建标准代码执行器失败: {str(e)}，使用模拟模式")
            executor = CodeExecutor(safety_level=safety_level, mock_mode=True)
        
        # 生成代码
        writer({"custom_step": "第1步: 生成代码..."})
            
        code = executor.generate_code(task_description)
        
        writer({"custom_step": "第2步: 执行生成的代码..."})
        code_preview = code[:200] + "..." if len(code) > 200 else code
        writer({"custom_step": f"生成的代码预览:\n```python\n{code_preview}\n```"})
        
        # 执行代码
        result = executor.execute_code(code)
        
        if result.success:
            writer({"custom_step": f"✅ 代码执行成功，耗时: {result.execution_time:.2f}秒"})
        else:
            writer({"custom_step": f"❌ 代码执行失败: {result.error}"})
        
        # 构建响应
        response = f"## 任务执行结果\n\n"
        response += f"**任务**: {task_description}\n\n"
        response += f"**生成的代码**:\n```python\n{code}\n```\n\n"
        response += f"**执行结果**:\n{str(result)}"
        
        return response
    
    except Exception as e:
        error_msg = f"代码助手工具调用失败: {str(e)}"
        logger.error(error_msg)
        
        writer({"custom_step": f"❌ {error_msg}"})
            
        return f"代码助手工具调用失败: {str(e)}" 

# 为code_assistant工具设置schema
code_assistant.args_schema = CodeAssistantSchema 