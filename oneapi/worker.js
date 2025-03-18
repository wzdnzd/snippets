/**
 * Filename: worker.js
 * Description: Cloudflare Worker Script for converting NextChat API to standard OpenAI API
 * Date: 2025-01-10
 * Version: 0.0.1
 * Author: wzdnzd
 * License: MIT License
 * 
 * usage:
 * 1. create a KV namespace and bind it to the script variable `openAPIs`
 * 2. add a secret key named `SECRET_KEY = 'your-secret-key'` as environment variable
 * 3. add the environment variable `DEFAULT_MODEL`, with a value of KV namespace keys
 * 4. deploy the script to Cloudflare Worker
 * 5. add NextChat API endpoints and access tokens to the KV namespace
 * 6. use the Cloudflare Worker URL as the API endpoint and add the secret key set in step 2 as the Authorization header
 * 7. use ${CLOUDFLARE_WORKER_URL}/v1/chat/completions as the request URL, and then send the request to the endpoint with the same body
 */

addEventListener('fetch', event => {
    event.respondWith(handleRequest(event.request))
});

const KV = database;
const maxRetries = 5;
const defaultModel = (DEFAULT_MODEL || 'gpt-4o').trim();

// Default settings for functionCall
const commonFunctionCallModel = (COMMON_FC_MODEL || '').trim();
const unifyFunctionCallModel = ['true', '1'].includes((UNIFY_FC_MODEL || 'false').trim().toLowerCase());

const userAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36';

// Key expired status
const invalidStatus = 'dead';

// Cache key suffix for function call
const functionCallKeySuffix = "#function";

// Error http status code
const switchNextStatusCodes = new Set([401, 402, 403, 418, 422, 429]);

// Rate limit status code
const rateLimitStatusCodes = new Set([418, 429]);

// Maximum Freeze Time, 3 days
const maxFreezingDuration = 3 * 24 * 60 * 60 * 1000;

/**
 * Cache config
 */
const cacheConfig = {
    // Unit: ms, 7 days
    TTL: 7 * 24 * 60 * 60 * 1000,
    MAX_CACHE_SIZE: 10000,
};

/**
 * Valid roles
 */
const validRoles = new Set(["system", "user", "assistant", "tool", "function", "developer"]);

// Default request paths for different types of models
const defaultRequestPaths = {
    "completion": "/v1/chat/completions",
    "embedding": "/v1/embeddings",
    "speech": "/v1/audio/speech",
    "transcription": "/v1/audio/transcriptions",
    "translation": "/v1/audio/translations",
    "imageGeneration": "/v1/images/generations",
    "imageEdit": "/v1/images/edits",
    "imageVariation": "/v1/images/variations",
    "moderation": "/v1/moderations",
};

/**
 * Supported request paths
 */
const supportedRequestPaths = new Set(Object.values(defaultRequestPaths));

/**
 * Simple cache
 */
class SimpleCache {
    constructor() {
        this.cache = new Map();
        this.keyTimestamps = new Map();
    }

    generateKey(model, functionCall) {
        const modelName = (model || '').trim();
        if (!modelName) return '';

        return functionCall ? modelName + functionCallKeySuffix : modelName;
    }

    set(key, value) {
        // Check cache size
        if (this.cache.size >= cacheConfig.MAX_CACHE_SIZE) {
            // Delete oldest item
            const oldestKey = [...this.keyTimestamps.entries()].sort(
                ([, a], [, b]) => a - b
            )[0][0];
            this.cache.delete(oldestKey);
            this.keyTimestamps.delete(oldestKey);
        }

        this.cache.set(key, value);
        this.keyTimestamps.set(key, Date.now());
    }

    get(key) {
        const timestamp = this.keyTimestamps.get(key);
        if (!timestamp) return null;

        // Check whether expired
        if (Date.now() - timestamp > cacheConfig.TTL) {
            this.cache.delete(key);
            this.keyTimestamps.delete(key);
            return null;
        }

        return this.cache.get(key);
    }

    has(key) {
        const timestamp = this.keyTimestamps.get(key);
        if (!timestamp) return false;

        // Check whether expired
        if (Date.now() - timestamp > cacheConfig.TTL) {
            this.cache.delete(key);
            this.keyTimestamps.delete(key);
        }

        return this.cache.has(key);
    }

    clear() {
        this.cache.clear();
        this.keyTimestamps.clear();
    }

    remove(key) {
        this.cache.delete(key);
        this.keyTimestamps.delete(key);
    }
}

// Cache provider selecotr
const providerSelectorCache = new SimpleCache();

/**
 * Alias method sampler
 */
class AliasMethodSampler {
    constructor(weights) {
        this.length = weights.length;

        // Probability table
        this.prob = new Array(this.length);

        // Alias table
        this.alias = new Array(this.length);

        // Calculate total weight
        const sum = weights.reduce((a, b) => a + b, 0);

        // Normalize weights to make sum equals to n
        const normalized = weights.map(w => (w * this.length) / sum);

        // Separate probabilities into those larger and smaller than 1
        const small = [];
        const large = [];

        normalized.forEach((prob, i) => {
            if (prob < 1) {
                small.push(i);
            } else {
                large.push(i);
            }
        });

        // Pairing process
        while (small.length > 0 && large.length > 0) {
            const less = small.pop();
            const more = large.pop();

            this.prob[less] = normalized[less];
            this.alias[less] = more;

            // Update remaining probability for the larger probability event
            normalized[more] = (normalized[more] + normalized[less] - 1);

            if (normalized[more] < 1) {
                small.push(more);
            } else {
                large.push(more);
            }
        }

        // Handle remaining items (might exist due to floating point precision)
        while (large.length > 0) {
            this.prob[large.pop()] = 1;
        }
        while (small.length > 0) {
            this.prob[small.pop()] = 1;
        }
    }

    sample() {
        // Randomly select a cell
        const i = Math.floor(Math.random() * this.length);
        // Choose between original event or alias event based on probability
        return Math.random() < this.prob[i] ? i : this.alias[i];
    }
}

/**
 * Model provider
 */
class ModelProvider {
    constructor(address, token, realModel, priority, streamEnabled, instable) {
        // API address
        this.address = address;

        // API key
        this.token = token;

        // Target model name
        this.realModel = realModel;

        // Priority
        this.priority = priority;

        // Stream enabled
        this.streamEnabled = streamEnabled;

        // If true then need to check whether the response content is empty or not
        this.instable = instable;
    }

    valueOf() {
        return `${this.address}@${this.token}`;
    }

    toString() {
        return JSON.stringify({ "address": this.address, "token": this.token });
    }
}

/**
 * Model provider selector
 */
class ModelProviderSelector {
    constructor(providers) {
        if (!providers || providers.length <= 0) {
            throw new Error("Instantiate error, providers cannot be empty");
        }

        const weights = [];
        providers.forEach(provider => {
            let priority = provider.priority;
            if (priority <= 0) {
                priority = Math.ceil(1 / providers.length * 100);
            }

            weights.push(priority);
        });

        // AliasMethodSampler
        this.sampler = new AliasMethodSampler(weights);

        // Candidate service list
        this.providers = providers;

        // Frozen providers
        this.frozenProviders = new Map();

        // Number of failures
        this.failures = new Map();
    }

    select(last, strict) {
        if (!this.providers?.length) {
            return null;
        } else if (this.providers.length === 1) {
            console.log(`Only one provider, address: ${this.providers[0].address}, token: ${this.providers[0].token}, frozen: ${this.onHold(this.providers[0])}`);
            return this.providers[0];
        }

        const startTime = Date.now();

        // Last request failed, need to cool down for a while
        this.freeze(last);

        let provider = this.providers[this.sampler.sample()];
        const isSame = this.isSameProvider(last, provider, strict);
        const cooling = this.onHold(provider);

        if (isSame) {
            console.log(`The result of sampling is consistent with the provider which was failed in last request, try to downgraded and switch, selected: ${provider.valueOf()}, last: ${last.valueOf()}, strict: ${strict}`);
            provider = this.selectAlternativeProvider(last, strict);
        } else if (cooling) {
            const timestamp = this.frozenProviders.get(provider.valueOf());
            const releaseTime = new Date(timestamp).toLocaleString('zh-CN', {
                timeZone: 'Asia/Shanghai',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false
            });
            console.info(`The result of sampling has been frozen, address: ${provider.address}, token: ${provider.token}, release: ${releaseTime}`);
            provider = this.selectUnfrozenProvider(last, strict) || provider;
        }

        const text = last ? last.valueOf() : "null";
        const cost = Date.now() - startTime;
        console.log(`Selection finished, address: ${provider.address}, token: ${provider.token}, frozen: ${this.onHold(provider)}, last: ${text}, cost: ${cost}ms`);

        return provider;
    }

    selectAlternativeProvider(last, strict) {
        const otherProviders = [];
        const adequateProviders = [];
        const unFrozenProviders = [];

        for (const item of this.providers) {
            if (item.address === last?.address && (strict || item.token === last?.token)) {
                if (item.token !== last?.token) {
                    otherProviders.push(item);
                }
                continue;
            }

            adequateProviders.push(item);
            if (!this.onHold(item)) {
                unFrozenProviders.push(item);
            }
        }

        // Priority: not frozen > different service addresses > different tokens
        const availableProviders = unFrozenProviders.length > 0 ? unFrozenProviders :
            adequateProviders.length > 0 ? adequateProviders : otherProviders;

        return this.randomSelect(availableProviders);
    }

    selectUnfrozenProvider(last, strict) {
        const hasUnfrozenProvider = this.frozenProviders.size < this.providers.length;
        if (!hasUnfrozenProvider) {
            return null;
        }

        if (!last) {
            let index = this.sampler.sample();
            let provider = this.providers[index];

            while (this.onHold(provider)) {
                console.warn(`Skip frozen provider, address: ${provider.address}, token: ${provider.token}`);
                index = (index + 1) % this.providers.length;
                provider = this.providers[index];
            }

            return provider;
        }

        const unFrozenProviders = this.providers.filter(item =>
            !(this.isSameProvider(last, item, strict) || this.onHold(item))
        );

        return unFrozenProviders.length > 0 ? this.randomSelect(unFrozenProviders) : null;
    }

    randomSelect(providers) {
        if (!providers || providers.length <= 0)
            return null;

        return providers[Math.floor(Math.random() * providers.length)];
    }

    isSameProvider(last, provider, strict) {
        if (last === provider || (!last && !provider))
            return true;
        else if (!last || !provider)
            return false;

        return provider.address === last.address && (strict || provider.token === last.token);
    }

    getNextFreezeDuration(provider) {
        if (!provider) return 0;

        const key = provider.valueOf();
        let count = this.failures.get(key);
        if (!count || count < 0) count = 0;

        count++;
        this.failures.set(key, count);

        const duration = Math.pow(2, count) * 1000;
        return Math.min(duration, maxFreezingDuration);
    }

    freeze(provider) {
        if (!provider) return;

        const current = Date.now();
        const key = provider.valueOf();

        let base = this.frozenProviders.get(key);
        if (!base || base < current) {
            base = current;
        }

        this.frozenProviders.set(key, base + this.getNextFreezeDuration(provider));
    }

    unfreeze(provider) {
        if (!provider) return;

        const key = provider.valueOf();
        this.frozenProviders.delete(key);
        this.failures.delete(key);
    }

    onHold(provider) {
        if (!provider) false;
        const key = provider.valueOf();

        const timestamp = this.frozenProviders.get(key);
        return !timestamp ? false : timestamp > Date.now();
    }
}

/**
 * Handle request
 */
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
    if (!accessToken || !accessToken.startsWith('Bearer ')) {
        return createErrorResponse('Unauthorized', 401);
    }

    const authToken = accessToken.substring(7).trim();
    const url = new URL(request.url);

    if (('/v1/models' === url.pathname || supportedRequestPaths.has(url.pathname)) && authToken !== (SECRET_KEY || '')
        || ['/v1/provider/list', '/v1/provider/update', '/v1/provider/reload'].includes(url.pathname)
        && authToken !== (ADMIN_AUTH_TOKEN || '')) {
        return createErrorResponse('Unauthorized', 401);
    }


    let response;
    if (url.pathname === '/v1/models' && request.method === 'GET') {
        response = await handleListModels();
    } else if (url.pathname === '/v1/chat/completions' && request.method === 'POST') {
        response = await handleCompletion(request);
    } else if (url.pathname === '/v1/embeddings' && request.method === 'POST') {
        response = await handleEmbedding(request);
    } else if (supportedRequestPaths.has(url.pathname) && request.method === 'POST') {
        const body = await request.json();
        const headers = new Headers(request.headers);
        response = await handleProxyRequest(body, headers);
    } else if (url.pathname === '/v1/provider/list' && request.method === 'GET') {
        response = await handleProviderList();
    } else if (url.pathname === '/v1/provider/update' && request.method === 'PUT') {
        const config = await request.json();
        response = await handleProviderUpdate(config);
    } else if (url.pathname === '/v1/provider/reload' && request.method === 'POST') {
        // TODO: Need to synchronously delete the cache in all instances
        providerSelectorCache.clear();
        response = new Response(JSON.stringify({ message: 'Ok', success: true }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
        });
    } else {
        response = new Response(JSON.stringify({ message: 'Invalid request method or path', success: false }), {
            status: 405,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    return response;
}

/**
 * Handle list models request
 */
async function handleListModels() {
    // List and return all openai models
    const headers = new Headers({ 'Content-Type': 'application/json' });
    setCORSHeaders(headers);

    return new Response(JSON.stringify({
        "data": await listSupportModels(),
        "object": "list"
    }), {
        status: 200,
        headers: headers
    });
}

/**
 * Handle provider list request
 */
async function handleProviderList() {
    const headers = new Headers({ 'Content-Type': 'application/json' });
    setCORSHeaders(headers);

    return new Response(JSON.stringify(await listAllProviders()), {
        status: 200,
        headers: headers
    });
}

/**
 * List all providers
 */
async function listAllProviders() {
    const items = await KV.list();
    const data = {};

    for (const key of items.keys) {
        const model = key.name;
        const content = await KV.get(model);
        try {
            const config = JSON.parse(content);
            data[model] = config;
        } catch {
            console.error(`Parse config error for model ${model}, config: ${content}`);
        }
    }

    return data;
}

/**
 * Create error response with given message and status code
 */
function createErrorResponse(message, status = 400) {
    return new Response(JSON.stringify({ message, success: false }), {
        status,
        headers: { 'Content-Type': 'application/json' }
    });
}

/**
 * Set common headers for requests
 */
function setCommonHeaders(headers, isStream = false) {
    headers.set('Content-Type', 'application/json');
    headers.set('Accept-Language', 'zh-CN,zh;q=0.9');
    headers.set('Accept-Encoding', 'gzip, deflate, br, zstd');
    headers.set('Accept', isStream ? 'application/json, text/event-stream' : 'application/json');
    headers.set('User-Agent', userAgent);

    const needRemoveHeaders = ['x-forwarded-for', 'CF-Connecting-IP', 'CF-IPCountry', 'CF-Visitor', 'CF-Ray', 'CF-Worker', 'CF-Device-Type'];
    needRemoveHeaders.forEach(key => headers.delete(key));
}

/**
 * Set provider-specific headers
 */
function setProviderHeaders(headers, proxyURL, accessToken) {
    headers.set('Referer', proxyURL);
    headers.set('Origin', proxyURL);
    headers.set('Host', new URL(proxyURL).host);
    headers.set('X-Real-IP', '8.8.8.8');

    headers.delete('Authorization');
    if (accessToken && accessToken !== 'null') {
        if (proxyURL.startsWith('https://api.anthropic.com')) {
            headers.set('x-api-key', accessToken);
            headers.set('anthropic-version', '2023-06-01');
        } else {
            headers.set('Authorization', `Bearer ${accessToken}`);
        }
    }
}

/**
 * Set cross-origin headers
 */
function setCORSHeaders(headers) {
    headers.set('Access-Control-Allow-Origin', '*');
    headers.set('Access-Control-Allow-Methods', '*');
    headers.set('Access-Control-Allow-Headers', '*');
}

/**
 * Handle expired provider by updating KV store
 */
async function handleExpiredProvider(model, proxyURL, accessToken) {
    const text = await KV.get(model);
    try {
        const arrays = JSON.parse(text);
        const providers = arrays.map(item => {
            if (item.address === proxyURL && item.token === accessToken) {
                item.alive = invalidStatus;
            }

            return item;
        });

        // Save to KV database
        await KV.put(model, JSON.stringify(providers));

        // Remove cache for reload
        providerSelectorCache.remove(model);
    } catch {
        console.error(`Update provider status failed due to parse config error, model: ${model}, config: ${text}`);
    }
}

/**
 * Initialize provider selector for a model
 */
async function initializeSelector(model, functionCall = false) {
    const functionEnabledKey = providerSelectorCache.generateKey(model, true);

    if (!providerSelectorCache.has(model)) {
        const config = await KV.get(model);
        if (!config) {
            return null;
        }

        const obj = await createModelProviderSelector(model);
        const commonSelector = obj?.selector;
        const functionCallSelector = obj?.functionEnabledSelector;

        providerSelectorCache.set(model, commonSelector);
        providerSelectorCache.set(functionEnabledKey, functionCallSelector);
    }

    const key = functionCall ? functionEnabledKey : model;
    return providerSelectorCache.get(key);
}

/**
 * Make request to provider with retry mechanism
 */
async function sendRequest(headers, url, requestBody, method = 'POST') {
    try {
        return await fetch(url, {
            method: method || 'POST',
            headers: headers,
            body: JSON.stringify(requestBody),
        });
    } catch (error) {
        console.error(`Error during fetch with ${url}: `, error);
        return null;
    }
}

/**
 * Process response based on content type and stream requirement
 */
async function processResponse(response, isStreamReq, requestModel, realModel) {
    if (!response) {
        return createErrorResponse('No response from server', 500);
    } else if (response.status !== 200) {
        console.error(`Request failed, request model: ${requestModel}, real model: ${realModel}, stream: ${isStreamReq}, status: ${response.status}`);
        return response;
    }

    const newHeaders = new Headers(response.headers);
    setCORSHeaders(newHeaders);

    let newBody = response.body;
    const contentType = response.headers.get('Content-Type') || '';
    console.log(`Start parse response, request model: ${requestModel}, real model: ${realModel}, stream: ${isStreamReq}, content-type: ${contentType}`);

    if (isStreamReq && !contentType.includes('text/event-stream')) {
        // Need text/event-stream but got others
        if (contentType.includes('application/json')) {
            console.log(`Request with stream but got 'application/json'`);

            try {
                const data = await response.json();

                // 'chatcmpl-'.length = 10
                const messageId = (data?.id || '').slice(10);

                const choices = data?.choices
                if (!choices || choices.length === 0) {
                    return createErrorResponse('No effective response', 503);
                }

                const record = choices[0].message || {};
                const message = record?.content || '';
                const content = transformToJSON(message, requestModel, messageId);
                const text = `data: ${content}\n\ndata: [Done]`;

                newBody = new ReadableStream({
                    start(controller) {
                        controller.enqueue(new TextEncoder().encode(text));
                        controller.close();
                    }
                });

            } catch (error) {
                console.error(`Parse response error: `, error);
                return createErrorResponse('Internal server error', 500);
            }
        } else {
            const { readable, writable } = new TransformStream();

            // Transform chunk data to event-stream
            streamResponse(response, writable, requestModel, generateUUID());
            newBody = readable;
        }

        newHeaders.set('Content-Type', 'text/event-stream');
    } else if (!isStreamReq && !contentType.includes('application/json')) {
        // Need application/json
        try {
            const content = (await response.text())
                .replace(/^\`\`\`json\n/, "").replace(/\n\`\`\`$/, "");

            // Compress json data
            const obj = JSON.parse(content);

            // Replace model name to request model
            if (obj.hasOwnProperty("choices")) {
                obj.model = requestModel;
            }

            const text = JSON.stringify();
            newBody = new ReadableStream({
                start(controller) {
                    controller.enqueue(new TextEncoder().encode(text));
                    controller.close();
                }
            });

            newHeaders.set('Content-Type', 'application/json');
        } catch (error) {
            console.error(`Parse response error: `, error);
            return createErrorResponse('Internal server error', 500);
        }
    }

    return new Response(newBody, {
        ...response,
        headers: newHeaders
    });
}

/**
 * Generic request handler for both completion and embedding
 */
async function handleProxyRequest(body, headers, options = {}, method = 'POST') {
    // Validate request
    if (!isNotEmptyObject(body)) {
        return createErrorResponse('Invalid request, body cannot be empty');
    }

    const model = (body.model || '').trim();
    if (!model) {
        return createErrorResponse('Model name cannot be empty');
    }

    // Initialize selector
    const isChatCompletion = options?.isChatCompletion === true;
    const functionCall = isChatCompletion &&
        (isNotEmptyObject(body.tools) || isNotEmptyObject(body.features) || isNotEmptyObject(body.tool_choice) || isNotEmptyObject(body.functions));

    const selector = await initializeSelectorFallback(model, functionCall);
    if (!selector) {
        const message = functionCall ? `Not found any model '${model}' support function call` : `Not support model '${model}'`
        return createErrorResponse(message);
    }

    // Prepare request
    const isStreamReq = isChatCompletion && (body.stream || false);

    headers = !headers ? {} : headers;
    setCommonHeaders(headers, isStreamReq);
    if (isChatCompletion) {
        // Compatible with nextchat API
        headers.set('Path', 'v1/chat/completions');
    }

    // Make request with retry
    let response;
    let provider = null;
    let invalidFlag = false;
    let internalErrorFlag = false;

    for (let retry = 0; retry < maxRetries; retry++) {
        provider = selector.select(invalidFlag ? provider : null, internalErrorFlag);
        if (!provider) {
            return createErrorResponse('Service is temporarily unavailable', 503);
        }

        const url = provider.address;
        const accessToken = provider.token;

        // Update request body
        body.model = provider.realModel;

        // Adapt o3-mini
        if (body.model.startsWith('o3-mini') && !body.reasoning_effort) {
            let reasoning_effort = 'low';
            if (model === 'o3-mini-high') reasoning_effort = 'high';
            else if (model === 'o3-mini-medium') reasoning_effort = 'medium';

            body.model = 'o3-mini';

            // see: https://community.openai.com/t/is-03-mini-in-the-api-the-low-medium-or-high-version/1110423
            body.reasoning_effort = reasoning_effort;
        }

        if (isChatCompletion) {
            body.stream = isStreamReq && provider.streamEnabled;
        }

        setProviderHeaders(headers, url, accessToken);
        response = await sendRequest(headers, url, body, method);

        if (response) {
            // There might be a problem with the service, switch to the next service directly
            internalErrorFlag = response.status >= 500;

            // Need switch to next provider
            invalidFlag = internalErrorFlag || switchNextStatusCodes.has(response.status);

            if (response.ok) {
                // Request successed, no cooldown
                selector.unfreeze(provider);

                break;
            } else if (response.status === 401) {
                console.warn(`Found expired provider, address: ${url}, token: ${accessToken}`);

                // Flag provider status to dead
                await handleExpiredProvider(model, url, accessToken);
            } else if (rateLimitStatusCodes.has(response.status)) {
                console.warn(`Upstream is busy, address: ${url}, token: ${accessToken}`);
            } else {
                console.error(`Failed to request, address: ${url}, token: ${accessToken}, status: ${response.status}`);
            }
        } else {
            invalidFlag = true;
        }
    }

    if (!response) {
        response = createErrorResponse('Internal server error', 500);
    }

    return response;
}

/**
 * Handle chat completion requests
 */
async function handleCompletion(request) {
    const requestBody = await request.json();
    const requestModel = requestBody.model;

    const realModel = (requestModel || defaultModel).trim();
    if (!realModel) {
        return createErrorResponse('Model name for chat completion cannot be empty');
    }

    requestBody.model = realModel;

    // Preprocess message
    const messages = [];
    for (const message of (requestBody.messages || [])) {
        try {
            const item = await preprocessMessage(message);
            if (item) {
                messages.push(item);
            }
        } catch (error) {
            console.error(`Preprocess message error: `, error);
            return createErrorResponse(`Found invalid message: ${JSON.stringify(message)}`, 400);
        }
    }

    if (messages.length === 0) {
        return createErrorResponse('Messages cannot be empty');
    }
    requestBody.messages = messages;

    const options = { isChatCompletion: true };
    const headers = new Headers(request.headers);
    const isStreamReq = requestBody.stream || false;

    const response = await handleProxyRequest(requestBody, headers, options);
    return processResponse(response, isStreamReq, requestModel, realModel);
}

/**
 * Handle embedding requests
 */
async function handleEmbedding(request) {
    const requestBody = await request.json();

    // Check input
    const input = requestBody?.input || '';
    let content;
    if (typeof input === 'string') {
        content = input.trim();
    } else if (input instanceof Array) {
        content = input.filter(i => i && i.trim());
        if (content.length === 0) {
            content = null;
        }
    } else {
        content = null;
    }

    if (!content) {
        return createErrorResponse('Embedding input cannot be empty');
    }

    return await handleProxyRequest(requestBody, new Headers(request.headers));
}

/**
 * Handle provider update requests
 */
async function handleProviderUpdate(config) {
    /* structure
        {
        "replace": true,
        "providers": {
            "https://a.com": {
                "paths": {
                    "completion": "/v1/chat/completions",
                    "embedding": "/v1/embeddings"
                },
                "tokens": {
                    "token1": {
                        "models": {
                            "gpt-4o": {
                                "functionEnabled": false,
                                "priority": 60,
                                "type": "completion"
                            },
                            "gpt-4o-mini": {},
                            "o1": {
                                "realModel": "o1-preview",
                                "functionEnabled": true,
                                "priority": 35
                            },
                            "text-embedding-3-large": {
                                "priority": 10,
                                "type": "embedding"
                            },
                            "claude-3-5-sonnet-20241022": {
                                "realModel": "claude-3-5-sonnet-20240620"
                            }
                        },
                        "tbd": "unknown"
                    }
                }
            }
        }
    }
  */

    if (!config) {
        return createErrorResponse('Invalid config', 400);
    }

    let replace = false;
    if (config.hasOwnProperty("replace")) {
        replace = config.replace;
    }

    const providers = config?.providers;
    if (!isNotEmptyObject(providers)) {
        return createErrorResponse('New providers cannot be empty', 400);
    }

    const map = new Map();
    if (!replace) {
        // Load exist items
        const existConfig = await listAllProviders();
        if (isNotEmptyObject(existConfig)) {
            Object.keys(existConfig).forEach(key => {
                const value = existConfig[key];
                if (!value || value.length <= 0) {
                    console.warn(`Ignore invalid config for model: ${key}`);
                } else {
                    const modelProvider = map.get(key) || {};
                    for (const element of value) {
                        // Used to distinguish different providers
                        const id = `${element?.url}@${element?.token}`;
                        modelProvider[id] = element;
                    }

                    map.set(key, modelProvider);
                }
            });
        }
    }

    // Process each provider
    Object.keys(providers).forEach(url => {
        if (!url || typeof url !== "string") {
            console.warn(`Drop illegal config due to url:${url} is not a string`);
            return;
        }

        const address = url.trim().replace(/\/+$/, "");
        if (!isValidURL(address)) {
            console.warn(`Drop illegal config due to url: ${url} is not valid`);
            return;
        }

        const obj = providers[url];
        const records = obj?.tokens || {};
        if (!isNotEmptyObject(records)) {
            console.warn(`Ignore invalid config for url: ${url}`);
            return;
        }

        const paths = obj?.paths || {};
        Object.keys(records).forEach(key => {
            if (typeof key !== "string") {
                console.warn(`Ignore invalid config for url: ${url}, token: ${key} because token must be string`);
                return;
            }

            const token = key.trim();
            const service = records[key];
            if (!isNotEmptyObject(service?.models)) {
                console.warn(`Ignore invalid config for url: ${url}, token: ${key} because models is empty`);
                return;
            }

            const models = service.models;
            Object.keys(models).forEach(name => {
                if (!name || typeof name !== "string") {
                    console.warn(`Model name must be a string, url: ${url}, token: ${key}, model: ${name}`);
                    return;
                }

                const model = name.trim();
                if (!model) {
                    console.warn(`Model name cannot empty, url: ${url}, token: ${key}, model: ${name}`);
                    return;
                }

                const item = models[name];
                if (!item || typeof item !== "object") {
                    console.warn(`Skip due to invalid config: ${item}, url: ${url}, token: ${key}, model: ${name}`);
                    return;
                }

                const type = (item.type || '').trim().toLowerCase() || 'completion';
                if (!(type in defaultRequestPaths)) {
                    console.warn(`Skip due to invalid model type: ${item}, url: ${url}, token: ${key}, model: ${name}`);
                    return;
                }

                let urlPath = (paths[type] || '').trim() || defaultRequestPaths[type];
                if (!urlPath.startsWith('/')) {
                    urlPath = '/' + urlPath;
                }

                item["url"] = address + urlPath;
                item["token"] = token;

                const provider = map.get(model) || {};
                const id = `${address}@${token}`;
                provider[id] = item;
                map.set(model, provider);
            });
        });
    });

    if (replace) {
        // Remove all exist items
        const items = await KV.list();
        for (const key of items.keys) {
            await KV.delete(key.name);
        }
    }

    // Write each model and providers to KV database
    for (const [k, v] of map.entries()) {
        try {
            if (!k || !isNotEmptyObject(v))
                continue;

            const services = Object.values(v);
            await KV.put(k, JSON.stringify(services));

            // Revome cache for reload
            providerSelectorCache.remove(providerSelectorCache.generateKey(k, false));
            providerSelectorCache.remove(providerSelectorCache.generateKey(k, true));
        } catch {
            console.error(`Storage to KV failed, model: ${k}, config: ${JSON.stringify(v)}`);
        }
    }

    return new Response(JSON.stringify({ message: 'Ok', success: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
    });
}

/**
 * List all support models
 */
async function listSupportModels() {
    const items = await KV.list();
    const models = [];

    for (const key of items.keys) {
        if (!key) continue;

        const model = key.name.trim().toLowerCase();
        let brand = "Other";
        if (model.includes("claude")) {
            brand = "Anthropic";
        } else if (model.includes("gemini")) {
            brand = "Google";
        } else if (model.includes("gpt-") || ["o1", "o1-mini", "o1-preview"].includes(model)) {
            brand = "OpenAI";
        } else if (model.includes("deepseek")) {
            brand = "DeepSeek";
        } else if (model.includes("qwen-") || model.includes("qwq-")) {
            brand = "Qwen"
        }

        models.push({
            id: model,
            object: "model",
            created: 1733976732,
            owned_by: brand,
        });
    }

    return models;
}

/**
 * Check and preprocess message
 */
async function preprocessMessage(message) {
    if (!message || typeof message !== "object") {
        throw new Error(`Invalid message: ${JSON.stringify(message)}`);
    }

    // See: https://platform.openai.com/docs/api-reference/chat/create#chat-create-messages
    if (!message.hasOwnProperty("role")) {
        throw new Error(`Message must have a role field: ${JSON.stringify(message)}`);
    }

    const role = (message.role || '').trim().toLowerCase();
    if (!role) {
        throw new Error(`Role cannot be empty: ${JSON.stringify(message)}`);
    }

    // Check where role is valid
    if (!validRoles.has(role)) {
        throw new Error(`Invalid role: ${role}, must be one of: ${Array.from(validRoles).join(", ")}`);
    }

    // Check where content is valid
    if (role === "system" || role === "user" || role === "developer") {
        // For system, user, developer roles, content must exist
        if (!message.hasOwnProperty("content") || !message.content) {
            throw new Error(`Message with role ${role} must have a content field: ${JSON.stringify(message)}`);
        }
    } else if (role === "assistant") {
        // For assistant role, content must exist (unless assistant has tool_calls or function_call)
        const content = (message.content || '');
        const toolCalls = (message.tool_calls || []);
        const functionCall = (message.function_call || {});

        if (!content && !isNotEmptyObject(toolCalls) && !isNotEmptyObject(functionCall)) {
            console.warn(`Assistant message must have a content field: ${JSON.stringify(message)}`);
            return null;
        }
    } else if (role === "tool") {
        // For tool role, content and tool_call_id must exist
        if (!message.hasOwnProperty("content") || !message.content) {
            throw new Error(`Tool message must have a content field: ${JSON.stringify(message)}`);
        }

        if (!message.hasOwnProperty("tool_call_id") || !message.tool_call_id) {
            throw new Error(`Tool message must have a tool_call_id field: ${JSON.stringify(message)}`);
        }
    } else if (role === "function") {
        if (!message.hasOwnProperty("name") || !message.name) {
            throw new Error(`Function message must have a name field: ${JSON.stringify(message)}`);
        }
    }

    // Check where name is valid
    if (message.hasOwnProperty("name")) {
        const name = (message.name || '').trim();
        if (!name) {
            throw new Error(`Name cannot be empty: ${JSON.stringify(message)}`);
        }

        // Name cannot contain spaces
        if (name.includes(" ")) {
            throw new Error(`Name cannot contain spaces: ${JSON.stringify(message)}`);
        }
    }

    return message;
}

/**
 * Transform text to JSON
 */
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

/**
 * Generate UUID
 */
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        const r = (Math.random() * 16) | 0;
        const v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}

/**
 * Check if object is not empty
 */
function isNotEmptyObject(obj) {
    if (!obj) {
        return false;
    }

    if (typeof obj === "object") {
        return Object.keys(obj).length > 0;
    } else if (Array.isArray(obj)) {
        if (obj.length <= 0) {
            return false;
        }

        return obj.some(item => isNotEmptyObject(item));
    }

    return false;
}

/**
 * Check if URL is valid
 */
function isValidURL(url) {
    if (!url || typeof url !== "string" || (!url.startsWith('https://') && !url.startsWith('http://'))) {
        return false;
    }

    try {
        new URL(url);
        return true;
    } catch (err) {
        return false;
    }
}

/**
 * Stream response
 */
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

/**
 * Create model provider selector
 */
async function createModelProviderSelector(model) {
    const name = (model || '').trim();
    if (!name) {
        console.error(`Cannot load model provider due to model name is empty`);
        return null;
    }

    const content = (await KV.get(name) || '').trim();
    if (!content) {
        console.error(`Not support model: ${name}`);
        return null;
    }

    try {
        const arrays = JSON.parse(content);

        // Providers
        const modelProviders = new Set();
        const modelProvidersFunctionEnabled = new Set();

        for (const item of arrays) {
            const url = (item?.url || '').trim();
            if (!url.startsWith("https://") && !url.startsWith("http://")) {
                console.warn(`Ignore invalid provider config, model: ${name}, config: ${item}`);
                continue;
            }

            const dead = (item?.alive || '').trim().toLowerCase() === invalidStatus;
            if (dead) {
                console.warn(`Ignore expired provider config, model: ${name}, config: ${item}`);
                continue;
            }

            const token = (item?.token || '').trim();
            const realModel = (item?.realModel || '').trim() || name;

            let functionEnabled = false;
            if (item.hasOwnProperty("functionEnabled")) {
                functionEnabled = item?.functionEnabled;
            }

            let priority = -1;
            if (item.hasOwnProperty("priority")) {
                priority = item?.priority;
            }

            let streamEnabled = true;
            if (item.hasOwnProperty("streamEnabled")) {
                streamEnabled = item?.streamEnabled;
            }

            let instable = false;
            if (item.hasOwnProperty("instable")) {
                instable = item?.instable;
            }

            const provider = new ModelProvider(url, token, realModel, priority, streamEnabled, instable);
            modelProviders.add(provider);
            if (functionEnabled) {
                modelProvidersFunctionEnabled.add(provider);
            }
        }

        if (modelProviders.size <= 0) {
            console.warn(`Cannot found any valid provider for model: ${name}, config: ${content}`);
            return null;
        }

        const selector = new ModelProviderSelector(Array.from(modelProviders));
        let functionEnabledSelector = null;
        if (modelProvidersFunctionEnabled.size > 0) {
            functionEnabledSelector = new ModelProviderSelector(Array.from(modelProvidersFunctionEnabled));
        }

        return { selector: selector, functionEnabledSelector: functionEnabledSelector };
    } catch {
        console.error(`Load provider service error, model: ${name}, config: ${content}`);
        return null;
    }
}

/**
 * Initialize selector fallback
 */
async function initializeSelectorFallback(model, functionCall = false) {
    if (functionCall && unifyFunctionCallModel && commonFunctionCallModel) {
        return await initializeSelector(commonFunctionCallModel, functionCall);
    }

    let selector = await initializeSelector(model, functionCall);
    if (!selector && functionCall) {
        if (commonFunctionCallModel) {
            selector = await initializeSelector(commonFunctionCallModel, functionCall);
        }
    }

    return selector;
}