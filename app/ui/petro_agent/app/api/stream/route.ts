import { NextRequest } from 'next/server';

// 内部工具函数：创建流式消息
function createStreamMessage(type: string, data: any, sessionId: string) {
  return {
    type,
    id: `${type}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
    timestamp: new Date().toISOString(),
    session_id: sessionId,
    ...data
  };
}

// 内部消息类型示例
const mockStreamMessages = {
  nodeStart: (sessionId: string, nodeName: string, agentName?: string) => 
    createStreamMessage('node_start', {
      node_id: `node-${Date.now()}`,
      node_name: nodeName,
      agent_name: agentName,
      details: `开始执行节点: ${nodeName}`
    }, sessionId),
    
  toolProgress: (sessionId: string, toolName: string, progress: number) =>
    createStreamMessage('tool_progress', {
      tool_name: toolName,
      progress,
      status: `执行中... ${progress}%`
    }, sessionId),
    
  fileGenerated: (sessionId: string, fileName: string, fileType: string) =>
    createStreamMessage('file_generated', {
      file_id: `file-${Date.now()}`,
      file_name: fileName,
      file_path: `generated/${fileName}`,
      file_type: fileType,
      file_size: Math.floor(Math.random() * 1000000),
      category: fileType.includes('image') ? '图表' : '数据文件',
      description: `自动生成的${fileName}`
    }, sessionId),
    
  agentThinking: (sessionId: string, agentName: string, content: string) =>
    createStreamMessage('agent_thinking', {
      agent_name: agentName,
      content,
      reasoning_step: 1,
      total_steps: 3
    }, sessionId),
    
  systemInfo: (sessionId: string, message: string) =>
    createStreamMessage('system_info', {
      message,
      priority: 'normal'
    }, sessionId)
}; 

// SSE流式消息推送API
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const sessionId = searchParams.get('sessionId');
  
  if (!sessionId) {
    return new Response('Session ID is required', { status: 400 });
  }

  console.log(`[SSE] 建立流式连接，会话ID: ${sessionId}`);

  // 创建SSE响应流
  const stream = new ReadableStream({
    start(controller) {
      console.log(`[SSE] 流式连接已建立: ${sessionId}`);
      
      // 发送连接确认消息
      const connectMessage = {
        type: 'session_start',
        id: `connect-${Date.now()}`,
        timestamp: new Date().toISOString(),
        session_id: sessionId,
        session_info: {
          connected_at: new Date().toISOString()
        }
      };
      
      const data = `data: ${JSON.stringify(connectMessage)}\n\n`;
      controller.enqueue(new TextEncoder().encode(data));
      
      // 模拟周期性发送流式消息（在实际应用中，这些消息应该来自后端系统）
      const intervalId = setInterval(() => {
        // 发送系统信息消息
        const systemMessage = {
          type: 'system_info',
          id: `sys-${Date.now()}`,
          timestamp: new Date().toISOString(),
          session_id: sessionId,
          message: `会话 ${sessionId} 运行正常`,
          priority: 'low'
        };
        
        const sysData = `data: ${JSON.stringify(systemMessage)}\n\n`;
        controller.enqueue(new TextEncoder().encode(sysData));
      }, 30000); // 每30秒发送一次心跳
      
      // 清理函数
      const cleanup = () => {
        clearInterval(intervalId);
        console.log(`[SSE] 流式连接已断开: ${sessionId}`);
      };
      
      // 监听连接关闭
      req.signal.addEventListener('abort', cleanup);
      
      // 在一定时间后自动清理（可选）
      setTimeout(() => {
        cleanup();
        controller.close();
      }, 30 * 60 * 1000); // 30分钟后自动关闭
    },
    
    cancel() {
      console.log(`[SSE] 流式连接被取消: ${sessionId}`);
    }
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET',
      'Access-Control-Allow-Headers': 'Cache-Control'
    }
  });
} 