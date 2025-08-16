from typing import List, Optional, Any, Dict, Union, Callable
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage
from langchain_core.callbacks.manager import Callbacks
from dotenv import load_dotenv, find_dotenv

_ = load_dotenv(find_dotenv(), override=True)
class SFChatOpenAI(ChatOpenAI):
    def __init__(
        self,
        model: str = "Qwen/Qwen2.5-72B-Instruct",
        temperature: float = 0.1,
        streaming: bool = True,  # 默认启用流式输出
        callbacks: Callbacks = None,
        enable_thinking: bool = True,  # 添加enable_thinking参数
        thinking_budget: Optional[int] = None,  # 添加thinking_budget参数
        **kwargs
    ):
        """初始化SFChatOpenAI类
        
        Args:
            model: 要使用的模型名称
            temperature: 温度参数，控制生成文本的随机性
            streaming: 是否启用流式输出，默认为True
            callbacks: 回调函数列表
            enable_thinking: 是否启用思考过程，默认为False
            thinking_budget: 最大推理过程Token数，默认为None
            **kwargs: 其他参数
        """
        # 构建extra_body参数
        extra_body = kwargs.pop("extra_body", {}) or {}
        
        # 将thinking相关参数放入chat_template_kwargs中
        chat_template_kwargs = extra_body.get("chat_template_kwargs", {})
        
        chat_template_kwargs["enable_thinking"] = enable_thinking
        
        chat_template_kwargs["thinking_budget"] = thinking_budget
        
        # 如果有thinking相关参数，更新chat_template_kwargs
        if chat_template_kwargs:
            extra_body["chat_template_kwargs"] = chat_template_kwargs
        
        # 如果extra_body不为空，添加到kwargs中
        if extra_body:
            kwargs["extra_body"] = extra_body
            
        super().__init__(
            model=model,
            temperature=temperature,
            streaming=streaming,
            callbacks=callbacks,
            **kwargs
        )
    
    def get_num_tokens_from_messages(self, messages: List[BaseMessage]) -> int:
        """自定义token计算方法"""
        # 这里使用一个简单的估算方法
        return sum(len(str(message.content)) for message in messages)
    
class DeepSeekChatOpenAI(ChatOpenAI):
    def __init__(
        self,
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        streaming: bool = False,
        callbacks: Callbacks = None,
        **kwargs
    ):
        """初始化DeepSeekChatOpenAI类
        
        Args:
            model: 要使用的模型名称
            temperature: 温度参数，控制生成文本的随机性
            streaming: 是否启用流式输出
            callbacks: 回调函数列表
            **kwargs: 其他参数
        """
        super().__init__(
            model=model,
            temperature=temperature,
            streaming=streaming,
            callbacks=callbacks,
            **kwargs
        )
    
    def get_num_tokens_from_messages(self, messages: List[BaseMessage]) -> int:
        """自定义token计算方法"""
        # 这里使用一个简单的估算方法
        return sum(len(str(message.content)) for message in messages)
    

