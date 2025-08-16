from dataclasses import dataclass
from typing import Optional

@dataclass
class UIState:
    """用于管理UI状态的数据类"""
    thought_process: str = ""
    result: str = ""
    origin_image: Optional[str] = None
    result_image: Optional[str] = None
    visualization_3d: Optional[str] = None

    def to_dict(self):
        """转换为字典格式"""
        return {
            "thought_process": self.thought_process,
            "result": self.result,
            "origin_image": self.origin_image,
            "result_image": self.result_image,
            "visualization_3d": self.visualization_3d
        } 