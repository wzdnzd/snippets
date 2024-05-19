// see: https://linux.do/t/topic/78301

addEventListener('fetch', event => {
    event.respondWith(handleRequest(event.request))
})

async function handleRequest(request) {
    const url = new URL(request.url)

    if (request.method === "OPTIONS") {
        return new Response(null, {
            headers: {
                'Access-Control-Allow-Origin': '*',
                "Access-Control-Allow-Headers": '*',
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            },
            status: 204
        })
    }

    // 校验请求头
    const accessToken = request.headers.get('Authorization');
    if (!accessToken
        || !accessToken.startsWith('Bearer ')
        || accessToken.substring(7) !== (SECRET_KEY || '')) {
        return new Response(JSON.stringify({ message: 'Unauthorized', success: false }), {
            status: 401,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    if (url.pathname === '/v1/models' && request.method === 'GET') {
        return new Response(JSON.stringify({
            "data": [
                {
                    "id": "gpt-3.5-turbo",
                    "object": "model",
                    "created": 1685474247,
                    "owned_by": "openai",
                    "permission": [],
                    "root": "gpt-3.5-turbo",
                    "parent": null
                },
                {
                    "id": "gpt-4",
                    "object": "model",
                    "created": 1677649963,
                    "owned_by": "openai",
                    "permission": [],
                    "root": "gpt-4",
                    "parent": null
                },
                {
                    "id": "gpt-4-turbo",
                    "object": "model",
                    "created": 1712592000,
                    "owned_by": "openai",
                    "permission": [],
                    "root": "gpt-4-turbo",
                    "parent": null
                },
            ],
            "object": "list"
        }), {
            status: 200, headers: {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': '*',
                'Content-Type': 'application/json',
            }
        });
    } else if (url.pathname === '/v1/chat/completions' && request.method === 'POST') {
        const requestData = await request.json()

        const chatbotIdList = (CHATBOT_IDS || '').trim()
            .split(',')
            .map(s => s.trim())
            .filter(s => s !== '');

        if (chatbotIdList.length === 0) {
            return new Response(JSON.stringify({ message: 'Service temporarily unavailable', success: false }), {
                status: 502,
                headers: { 'Content-Type': 'application/json' }
            });
        }

        // 随机选取 chatbot id
        const chatbotId = chatbotIdList[Math.floor(Math.random() * chatbotIdList.length)];

        // 随机生成 conversationId
        const conversationId = crypto.randomUUID();

        // 是否流式响应
        const isStreamReq = requestData.stream || false;

        const newRequestData = {
            query: '',
            chatbot_id: chatbotId,
            conversation_id: conversationId,
            messages: requestData.messages.map(msg => ({
                role: msg.role,
                content: msg.content,
                timestamp: Date.now(),
                isImage: false,
                imageUrl: null,
                feedback: 0,
                confidence: null,
                sources: null,
                image_description: null
            }))
        }

        const newRequest = new Request('https://embed.elephant.ai/api/v1/send-message', {
            method: 'POST',
            headers: {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Language": "zh-CN,zh-Hans;q=0.9",
                "Host": "embed.elephant.ai",
                "Origin": "https://bot.elephant.ai",
                "Referer": "https://bot.elephant.ai/",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Site": "same-site",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
            },
            body: JSON.stringify(newRequestData)
        })

        const response = await fetch(newRequest)
        if (!response || ![200, 201, 204].includes(response.status)) {
            return new Response(JSON.stringify({ message: 'Request failed', success: false }), {
                status: 503,
                headers: { 'Content-Type': 'application/json' }
            });
        }

        const originalJson = await response.json()

        // 提取 answer 内容
        const answer = originalJson.answer || '';

        const commonHeaders = {
            'Access-Control-Allow-Origin': '*',
            "Access-Control-Allow-Headers": '*',
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive'
        }

        // 非流请求
        if (!isStreamReq) {
            const data = {
                "id": originalJson.id || `chatcmpl-${conversationId}`,
                "object": "chat.completion",
                "created": originalJson.created || Math.floor(Date.now() / 1000),
                "model": originalJson.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": answer
                        },
                        "finish_reason": null
                    }
                ]
            }

            commonHeaders['Content-Type'] = 'application/json';
            return new Response(JSON.stringify(data), {
                status: 200,
                headers: commonHeaders
            });
        }

        // 创建一个可读流
        const { readable, writable } = new TransformStream();
        const writer = writable.getWriter();

        // 创建一个异步函数用于发送数据块
        async function sendChunks() {
            // 发送开始数据
            const startData = createDataChunk(originalJson, "start");
            await writer.write(new TextEncoder().encode('data: ' + JSON.stringify(startData) + '\n\n'));

            // 将 answer 分批次发送
            const chunkSize = 50; // 每个数据块的字符数
            let index = 0;

            while (index < answer.length) {
                const chunk = answer.slice(index, index + chunkSize);
                const newData = createDataChunk(originalJson, "data", chunk);
                await writer.write(new TextEncoder().encode('data: ' + JSON.stringify(newData) + '\n\n'));
                index += chunkSize;

                // 添加一个短暂的延迟，模拟流式传输的效果
                await new Promise(resolve => setTimeout(resolve, 50));
            }

            // 发送结束数据
            const endData = createDataChunk(originalJson, "end");
            await writer.write(new TextEncoder().encode('data: ' + JSON.stringify(endData) + '\n\n'));

            await writer.write(new TextEncoder().encode('data: [DONE]'));
            // 标记流的结束
            await writer.close();
        }

        // 调用异步函数发送数据块
        sendChunks();

        return new Response(readable, {
            status: 200,
            headers: commonHeaders
        });
    }

    return new Response(JSON.stringify({ message: 'Invalid request method or path', success: false }), {
        status: 405,
        headers: { 'Content-Type': 'application/json' }
    });
}

// 根据类型创建不同的数据块
function createDataChunk(json, type, content = '') {
    switch (type) {
        case "start":
            return {
                id: json.id,
                object: "chat.completion.chunk",
                created: json.created,
                model: json.model,
                choices: [{ delta: {}, index: 0, finish_reason: null }]
            };
        case "data":
            return {
                id: json.id,
                object: "chat.completion.chunk",
                created: json.created,
                model: json.model,
                choices: [{ delta: { content }, index: 0, finish_reason: null }]
            };
        case "end":
            return {
                id: json.id,
                object: "chat.completion.chunk",
                created: json.created,
                model: json.model,
                choices: [{ delta: {}, index: 0, finish_reason: 'stop' }]
            };
        default:
            return {};
    }
}