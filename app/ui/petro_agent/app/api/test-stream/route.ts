import { NextRequest } from 'next/server';
import { createDataStreamResponse } from 'ai';

export async function POST(req: NextRequest) {
  console.log('🧪 测试流式API被调用');
  
  try {
    return createDataStreamResponse({
      execute: (dataStream) => {
        console.log('🧪 开始执行测试流式响应');
        
        const testTokens = ['Hello', ' ', 'World', '!', ' ', 'This', ' ', 'is', ' ', 'a', ' ', 'test', '.'];
        
        // 同步发送所有tokens
        testTokens.forEach((token, index) => {
          console.log(`🧪 发送测试token #${index + 1}: "${token}"`);
          
          dataStream.writeData({
            type: 'text-delta',
            textDelta: token
          });
        });
        
        console.log('🧪 测试流式响应完成');
      }
    });
  } catch (error) {
    console.error('🧪 测试流式API错误:', error);
    return new Response(JSON.stringify({ error: '测试失败' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

export async function GET(req: NextRequest) {
  return new Response('Test Stream API is working', {
    status: 200,
    headers: { 'Content-Type': 'text/plain' }
  });
} 