from typing import List, Optional, Any, Dict
from langchain.embeddings.base import Embeddings
import requests
import os
import numpy as np

class SiliconFlowEmbeddings(Embeddings):
    """SiliconFlow API embedding模型的Langchain封装。
    
    Attributes:
        model (str): embedding模型名称
        api_key (str): SiliconFlow API密钥
        encoding_format (str): 返回格式，可选 'float' 或 'base64'
    """
    
    def __init__(
        self,
        model: str = "BAAI/bge-m3",
        api_key: Optional[str] = None,
        encoding_format: str = "float",
    ):
        """初始化SiliconFlow Embeddings。

        Args:
            model (str): 要使用的模型名称，可选值:
                - BAAI/bge-large-zh-v1.5
                - BAAI/bge-large-en-v1.5 
                - netease-youdao/bce-embedding-base_v1
                - BAAI/bge-m3
                - Pro/BAAI/bge-m3
            api_key (str, optional): API密钥。如果未提供，将从环境变量OPENAI_API_KEY中获取
            encoding_format (str): 返回格式，默认为'float'
        """
        self.model = model
        self.api_key = api_key or os.getenv("SILICONFLOW_API_KEY")
        if self.api_key is None:

            raise ValueError(
                "SiliconFlow API key must be provided either through "
                "api_key parameter or SILICONFLOW_API_KEY environment variable"
            )
        self.encoding_format = encoding_format
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
    def _embed(self, texts: List[str]) -> List[List[float]]:
        """调用API获取文本嵌入向量。"""
        
        response = requests.post(
            "https://api.siliconflow.cn/v1/embeddings",
            headers=self.headers,
            json={
                "model": self.model,
                "input": texts,
                "encoding_format": self.encoding_format
            }
        )
        
        if response.status_code != 200:
            raise ValueError(
                f"API调用失败: {response.status_code}\n{response.text}"
            )
            
        data = response.json()
        # 按索引排序确保顺序正确
        embeddings = sorted(
            data["data"], 
            key=lambda x: x["index"]
        )
        return [item["embedding"] for item in embeddings]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """获取文档列表的嵌入向量。

        Args:
            texts: 要嵌入的文本列表

        Returns:
            文档嵌入向量列表
        """
        return self._embed(texts)

    def embed_query(self, text: str) -> List[float]:
        """获取单个查询文本的嵌入向量。

        Args:
            text: 要嵌入的查询文本

        Returns:
            查询文本的嵌入向量
        """
        return self._embed([text])[0] 