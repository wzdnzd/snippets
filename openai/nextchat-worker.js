/**
 * Filename: nextchat-worker.js
 * Description: Cloudflare Worker Script for converting NextChat API to standard OpenAI API
 * Date: 2024-03-27
 * Version: 0.0.1
 * Author: wzdnzd
 * License: MIT License
 * 
 * usage:
 * 1. create a KV namespace named `openapis` and bind it to the script variable `openapis`
 * 2. add a secret key named `SECRET_KEY = 'your-secret-key'` as environment variable
 * 3. deploy the script to Cloudflare Worker
 * 4. add NextChat API endpoints and access tokens to the KV namespace
 * 5. use the Cloudflare Worker URL as the API endpoint and add the secret key set in step 2 as the Authorization header
 * 6. use ${CLOUDFLARE_WORKER_URL}/v1/chat/completions as the request URL, and then send the request to the endpoint with the same body
 */

addEventListener('fetch', event => {
    event.respondWith(handleRequest(event.request))
})

const KV = openapis;
const maxRetries = 3;

async function handleRequest(request) {
    const corsHeaders = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'OPTIONS,POST,GET',
        'Access-Control-Allow-Headers': '*',
    };

    if (request.method === 'OPTIONS') {
        return new Response(null, { headers: corsHeaders });
    }

    const accessToken = request.headers.get('Authorization');
    if (!accessToken
        || !accessToken.startsWith('Bearer ')
        || accessToken.substring(7) !== (SECRET_KEY || '')) {
        return new Response(JSON.stringify({ message: 'Unauthorized', success: false }), {
            status: 401,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    const url = new URL(request.url);
    let response;

    if (url.pathname === '/v1/models' && request.method === 'GET') {
        response = await handleListModels();
    } else if (url.pathname === '/v1/chat/completions' && request.method === 'POST') {
        response = await handleProxy(request);
    } else {
        response = new Response(JSON.stringify({ message: 'Invalid request method or path', success: false }), {
            status: 405,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    return response;
}

async function handleListModels() {
    // list and return all openai models
    return new Response(JSON.stringify({
        "data": [
            {
                "id": "dall-e-2",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "dall-e-2",
                "parent": null
            },
            {
                "id": "dall-e-3",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "dall-e-3",
                "parent": null
            },
            {
                "id": "whisper-1",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "whisper-1",
                "parent": null
            },
            {
                "id": "tts-1",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "tts-1",
                "parent": null
            },
            {
                "id": "tts-1-1106",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "tts-1-1106",
                "parent": null
            },
            {
                "id": "tts-1-hd",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "tts-1-hd",
                "parent": null
            },
            {
                "id": "tts-1-hd-1106",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "tts-1-hd-1106",
                "parent": null
            },
            {
                "id": "gpt-3.5-turbo",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "gpt-3.5-turbo",
                "parent": null
            },
            {
                "id": "gpt-3.5-turbo-0301",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "gpt-3.5-turbo-0301",
                "parent": null
            },
            {
                "id": "gpt-3.5-turbo-0613",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "gpt-3.5-turbo-0613",
                "parent": null
            },
            {
                "id": "gpt-3.5-turbo-16k",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "gpt-3.5-turbo-16k",
                "parent": null
            },
            {
                "id": "gpt-3.5-turbo-16k-0613",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "gpt-3.5-turbo-16k-0613",
                "parent": null
            },
            {
                "id": "gpt-3.5-turbo-1106",
                "object": "model",
                "created": 1699593571,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "gpt-3.5-turbo-1106",
                "parent": null
            },
            {
                "id": "gpt-3.5-turbo-instruct",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "gpt-3.5-turbo-instruct",
                "parent": null
            },
            {
                "id": "gpt-4",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "gpt-4",
                "parent": null
            },
            {
                "id": "gpt-4-0314",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "gpt-4-0314",
                "parent": null
            },
            {
                "id": "gpt-4-0613",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "gpt-4-0613",
                "parent": null
            },
            {
                "id": "gpt-4-32k",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "gpt-4-32k",
                "parent": null
            },
            {
                "id": "gpt-4-32k-0314",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "gpt-4-32k-0314",
                "parent": null
            },
            {
                "id": "gpt-4-32k-0613",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "gpt-4-32k-0613",
                "parent": null
            },
            {
                "id": "gpt-4-1106-preview",
                "object": "model",
                "created": 1699593571,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "gpt-4-1106-preview",
                "parent": null
            },
            {
                "id": "gpt-4-vision-preview",
                "object": "model",
                "created": 1699593571,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "gpt-4-vision-preview",
                "parent": null
            },
            {
                "id": "text-embedding-ada-002",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "text-embedding-ada-002",
                "parent": null
            },
            {
                "id": "text-davinci-003",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "text-davinci-003",
                "parent": null
            },
            {
                "id": "text-davinci-002",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "text-davinci-002",
                "parent": null
            },
            {
                "id": "text-curie-001",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "text-curie-001",
                "parent": null
            },
            {
                "id": "text-babbage-001",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "text-babbage-001",
                "parent": null
            },
            {
                "id": "text-ada-001",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "text-ada-001",
                "parent": null
            },
            {
                "id": "text-moderation-latest",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "text-moderation-latest",
                "parent": null
            },
            {
                "id": "text-moderation-stable",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "text-moderation-stable",
                "parent": null
            },
            {
                "id": "text-davinci-edit-001",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "text-davinci-edit-001",
                "parent": null
            },
            {
                "id": "code-davinci-edit-001",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "code-davinci-edit-001",
                "parent": null
            },
            {
                "id": "davinci-002",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "davinci-002",
                "parent": null
            },
            {
                "id": "babbage-002",
                "object": "model",
                "created": 1677649963,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": true,
                        "allow_sampling": true,
                        "allow_logprobs": true,
                        "allow_search_indices": false,
                        "allow_view": true,
                        "allow_fine_tuning": false,
                        "organization": "*",
                        "group": null,
                        "is_blocking": false
                    }
                ],
                "root": "babbage-002",
                "parent": null
            }
        ],
        "object": "list"
    }), {
        status: 200, headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': '*',
            'Content-Type': 'application/json',
        }
    });
}

async function handleProxy(request) {
    const keys = await KV.list();
    const count = keys.keys.length;

    if (count <= 0) {
        return new Response(JSON.stringify({ message: 'Service is temporarily unavailable', success: false }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    const requestBody = await request.json();
    const headers = new Headers(request.headers);

    // add custom headers
    headers.set('Content-Type', 'application/json');
    headers.set('Path', 'v1/chat/completions');
    headers.set('Accept-Language', 'zh-CN,zh;q=0.9');
    headers.set('Accept-Encoding', 'gzip, deflate, br, zstd');
    headers.set('Accept', 'application/json, text/event-stream');
    headers.set('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36');

    let response;

    for (let retry = 0; retry < maxRetries; retry++) {
        const targetURL = keys.keys[Math.floor(Math.random() * count)].name;
        const accessToken = (await KV.get(targetURL) || '').trim();

        let proxyURL = targetURL;
        if (!proxyURL.endsWith('/api/chat-stream')
            && !proxyURL.endsWith('/v1/chat/completions')) {
            const url = new URL(proxyURL);
            if (!url.pathname.startsWith('/api/openai')) {
                proxyURL += '/api/chat-stream';
            } else {
                proxyURL += '/v1/chat/completions';
            }
        }

        headers.set('Referer', targetURL + '/');
        headers.set('Origin', targetURL);

        // remove old authorization header if exist
        headers.delete('Authorization');
        if (accessToken) {
            headers.set('Authorization', `Bearer ${accessToken}`);
        }

        try {
            response = await fetch(proxyURL, {
                method: 'POST',
                headers: headers,
                body: JSON.stringify(requestBody),
            });

            if (response && response.ok) {
                break;
            }
        } catch (error) {
            console.error(`Error during fetch with ${targetURL}: `, error);
        }
    }

    // no valid response after retries
    if (!response) {
        return new Response(JSON.stringify({ message: 'Internal server error', success: false }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    // return the original response
    const newHeaders = new Headers(response.headers);
    newHeaders.set('Access-Control-Allow-Origin', '*');
    newHeaders.set('Access-Control-Allow-Methods', '*');

    let newBody = response.body;
    const contentType = response.headers.get('Content-Type') || '';
    const stream = contentType.includes('text/event-stream') || false;

    if (!stream && response.status === 200) {
        const isPlain = contentType.includes('text/plain') || false;
        if (isPlain) {
            const content = (await response.text())
                .replace(/^\`\`\`json\n/, "").replace(/\n\`\`\`$/, "");

            // compress json data
            const text = JSON.stringify(JSON.parse(content));

            newBody = new ReadableStream({
                start(controller) {
                    controller.enqueue(new TextEncoder().encode(text));
                    controller.close();
                }
            });
        } else {
            const { readable, writable } = new TransformStream();

            // transform chunk data to event-stream
            streamResponse(response, writable, requestBody.model, generateUUID());
            newBody = readable;

            newHeaders.set('Content-Type', 'text/event-stream');
        }
    }

    const newResponse = new Response(newBody, {
        ...response,
        headers: newHeaders
    });

    return newResponse;
}

function transformToJSON(text, model, messageId) {
    return JSON.stringify({
        'id': `chatcmpl-${messageId}`,
        "object": "chat.completion.chunk",
        'model': model || 'gpt-3.5-turbo',
        "created": Math.floor(Date.now() / 1000),
        'choices': [{
            "index": 0,
            "delta": {
                "content": text || ''
            },
            "logprobs": null,
            "finish_reason": null
        }],
        "system_fingerprint": null
    });
}

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        const r = (Math.random() * 16) | 0;
        const v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}

async function streamResponse(response, writable, model, messageId) {
    const reader = response.body.getReader();
    const writer = writable.getWriter();
    const encoder = new TextEncoder();
    const decoder = new TextDecoder("utf-8");

    function push() {
        reader.read().then(({ done, value }) => {
            if (done) {
                writer.close();
                return;
            }

            const chunk = decoder.decode(value, { stream: true });
            const toSend = `data: ${transformToJSON(chunk, model, messageId)}\n\n`;

            writer.write(encoder.encode(toSend));
            push();
        }).catch(error => {
            console.error(error);
            writer.close();
        });
    }

    push();
}