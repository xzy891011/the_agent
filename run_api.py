#!/usr/bin/env python3
"""
API服务启动脚本 - 阶段4前后端分离架构的后端服务启动器

功能：
1. 启动FastAPI应用
2. 配置服务参数
3. 环境检查和初始化
4. 端口检查和占用清理
5. 优雅的启动和关闭
"""

import os
import sys
import argparse
import logging
import signal
import socket
import time
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

_ = load_dotenv(find_dotenv(), override=True)
# 添加项目根目录到Python路径
project_root = Path(__file__).parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_port_in_use(host: str, port: int) -> bool:
    """检查端口是否被占用
    
    Args:
        host: 主机地址
        port: 端口号
        
    Returns:
        True if port is in use, False otherwise
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            return result == 0
    except Exception as e:
        logger.debug(f"检查端口时发生异常: {e}")
        return False

def get_process_using_port(port: int) -> list:
    """获取占用指定端口的进程信息
    
    Args:
        port: 端口号
        
    Returns:
        占用端口的进程信息列表
    """
    try:
        import psutil
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                for conn in proc.connections():
                    if conn.laddr.port == port:
                        processes.append({
                            'pid': proc.info['pid'],
                            'name': proc.info['name'],
                            'cmdline': ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                        })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return processes
    except ImportError:
        logger.warning("psutil未安装，无法获取详细进程信息")
        return []

def kill_processes_on_port(port: int, force: bool = False) -> bool:
    """杀死占用指定端口的进程
    
    Args:
        port: 端口号
        force: 是否强制杀死进程
        
    Returns:
        True if successful, False otherwise
    """
    try:
        import psutil
        killed_processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                for conn in proc.connections():
                    if conn.laddr.port == port:
                        proc_info = f"PID={proc.info['pid']} ({proc.info['name']})"
                        logger.info(f"发现占用端口{port}的进程: {proc_info}")
                        
                        # 尝试优雅终止
                        if not force:
                            logger.info(f"尝试优雅终止进程 {proc_info}")
                            proc.terminate()
                            try:
                                proc.wait(timeout=5)
                                logger.info(f"✅ 成功优雅终止进程 {proc_info}")
                                killed_processes.append(proc_info)
                            except psutil.TimeoutExpired:
                                logger.warning(f"优雅终止超时，强制杀死进程 {proc_info}")
                                proc.kill()
                                killed_processes.append(proc_info)
                        else:
                            logger.info(f"强制杀死进程 {proc_info}")
                            proc.kill()
                            killed_processes.append(proc_info)
                            
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        if killed_processes:
            logger.info(f"已终止 {len(killed_processes)} 个占用端口{port}的进程")
            time.sleep(1)  # 等待进程完全退出
            return True
        else:
            logger.info(f"未发现占用端口{port}的进程")
            return False
            
    except ImportError:
        logger.error("psutil未安装，无法杀死占用端口的进程")
        logger.info("请安装psutil: pip install psutil")
        return False
    except Exception as e:
        logger.error(f"杀死进程时发生异常: {e}")
        return False

def ensure_port_available(host: str, port: int, max_retries: int = 3) -> bool:
    """确保端口可用，如果被占用则尝试清理
    
    Args:
        host: 主机地址
        port: 端口号
        max_retries: 最大重试次数
        
    Returns:
        True if port is available, False otherwise
    """
    for attempt in range(max_retries + 1):
        if not check_port_in_use(host, port):
            logger.info(f"✅ 端口 {port} 可用")
            return True
        
        if attempt == max_retries:
            logger.error(f"❌ 端口 {port} 仍被占用，已达到最大重试次数")
            return False
        
        logger.warning(f"⚠️ 端口 {port} 被占用 (尝试 {attempt + 1}/{max_retries + 1})")
        
        # 获取占用进程信息
        processes = get_process_using_port(port)
        if processes:
            logger.info("占用端口的进程：")
            for proc in processes:
                logger.info(f"  - PID: {proc['pid']}, 名称: {proc['name']}")
                if proc['cmdline']:
                    logger.info(f"    命令行: {proc['cmdline'][:100]}...")
        
        # 尝试清理端口
        logger.info(f"🔧 正在清理端口 {port}...")
        force_kill = attempt >= 1  # 第二次尝试时使用强制杀死
        if kill_processes_on_port(port, force=force_kill):
            logger.info(f"等待端口 {port} 释放...")
            time.sleep(2)
        else:
            logger.warning(f"无法清理端口 {port}")
            time.sleep(1)
    
    return False

def check_dependencies():
    """检查依赖包是否安装"""
    required_packages = [
        'fastapi',
        'uvicorn',
        'websockets',
        'pydantic',
        'psutil'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        logger.error(f"缺少依赖包: {', '.join(missing_packages)}")
        logger.info("请运行: pip install fastapi uvicorn websockets pydantic psutil")
        return False
    
    return True

def check_environment():
    """检查环境配置"""
    # 检查必要的目录
    required_dirs = [
        "data",
        "data/temp",
        "data/uploads", 
        "data/generated",
        "data/files",
        "config",
        "memories"
    ]
    
    for dir_path in required_dirs:
        full_path = project_root / dir_path
        if not full_path.exists():
            logger.info(f"创建目录: {full_path}")
            full_path.mkdir(parents=True, exist_ok=True)
    
    # 检查配置文件
    config_file = project_root / "config" / "default_config.json"
    if not config_file.exists():
        logger.warning(f"配置文件不存在: {config_file}")
        logger.info("将使用默认配置")
    
    return True

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="启动天然气碳同位素智能分析系统API服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听主机地址")
    parser.add_argument("--port", type=int, default=7102, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="启用热重载（开发模式）")
    parser.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"], help="日志级别")
    parser.add_argument("--workers", type=int, default=1, help="工作进程数")
    parser.add_argument("--env", default="sweet", help="Conda环境名称")
    parser.add_argument("--force-port", action="store_true", help="强制清理端口占用")
    
    args = parser.parse_args()
    
    print("🚀 天然气碳同位素智能分析系统 - API服务启动器")
    print("=" * 60)
    
    # 环境检查
    logger.info("检查运行环境...")
    if not check_dependencies():
        sys.exit(1)
    
    if not check_environment():
        sys.exit(1)
    
    # 端口检查和清理
    logger.info(f"检查端口 {args.port} 可用性...")
    if not ensure_port_available(args.host, args.port):
        if args.force_port:
            logger.warning("强制模式：尝试继续启动服务...")
        else:
            logger.error(f"端口 {args.port} 无法使用，请检查或使用 --force-port 参数")
            sys.exit(1)
    
    # 检查conda环境
    conda_env = os.environ.get('CONDA_DEFAULT_ENV')
    if conda_env != args.env:
        logger.warning(f"当前Conda环境: {conda_env}，建议环境: {args.env}")
        logger.info(f"请运行: conda activate {args.env}")
    
    # 显示启动信息
    logger.info("启动配置:")
    logger.info(f"  - 主机地址: {args.host}")
    logger.info(f"  - 监听端口: {args.port}")
    logger.info(f"  - 热重载: {'开启' if args.reload else '关闭'}")
    logger.info(f"  - 日志级别: {args.log_level.upper()}")
    logger.info(f"  - 工作进程: {args.workers}")
    logger.info(f"  - 项目路径: {project_root}")
    
    # 启动提示
    print("\n🌐 服务地址:")
    print(f"  - API根路径: http://{args.host}:{args.port}")
    print(f"  - API文档: http://{args.host}:{args.port}/docs")
    print(f"  - 健康检查: http://{args.host}:{args.port}/health")
    print(f"  - WebSocket: ws://{args.host}:{args.port}/ws/{{session_id}}")
    
    print("\n📋 主要功能:")
    print("  - RESTful API接口")
    print("  - WebSocket实时通信")
    print("  - 多模态数据传输")
    print("  - 流式响应处理")
    print("  - 会话状态管理")
    print("  - 文件上传下载")
    print("  - 系统监控管理")
    
    print("\n⚡ 启动API服务...")
    print("=" * 60)
    
    try:
        # 导入并启动API服务
        from app.api.main import run_api_server
        
        run_api_server(
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=args.log_level
        )
        
    except KeyboardInterrupt:
        print("\n\n🛑 收到中断信号，正在关闭服务...")
        logger.info("API服务已停止")
    except Exception as e:
        logger.error(f"启动API服务失败: {str(e)}")
        # 如果是端口占用错误，提供额外帮助信息
        if "address already in use" in str(e).lower():
            logger.info("💡 提示：端口仍被占用，请尝试以下方案：")
            logger.info("  1. 使用 --force-port 参数强制清理端口")
            logger.info("  2. 手动停止占用端口的进程")
            logger.info("  3. 更换其他端口号")
        sys.exit(1)

if __name__ == "__main__":
    main() 