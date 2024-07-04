// see: https://linux.do/t/topic/78301 | https://linux.do/t/topic/78679

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

        // 请求 body
        const requestData = await request.json()

        const newRequest = new Request('https://ele.oaifree.com/v1/chat/completions', {
            method: 'POST',
            headers: {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Language": "zh-CN,zh-Hans;q=0.9",
                "Authorization": `Bearer ${chatbotId}`
            },
            body: JSON.stringify(requestData)
        })

        return await fetch(newRequest)
    }

    return new Response(JSON.stringify({ message: 'Invalid request method or path', success: false }), {
        status: 405,
        headers: { 'Content-Type': 'application/json' }
    });
}