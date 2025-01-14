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
const maxRetries = 3;
const defaultModel = (DEFAULT_MODEL || 'gpt-4o').trim();
const userAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36';

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

const cacheConfig = {
    // Unit: ms, 7 days
    TTL: 7 * 24 * 60 * 60 * 1000,
    MAX_CACHE_SIZE: 10000,
};

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

class ModelProvider {
    constructor(address, token, realModel, priority, streamEnabled) {
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
    }

    valueOf() {
        return `${this.address}@${this.token}`;
    }

    toString() {
        return JSON.stringify({ "address": this.address, "token": this.token });
    }
}

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

    select() {
        if (!this.providers || this.providers.length <= 0) {
            return null;
        }

        let index = this.sampler.sample();
        if (index >= this.providers.length) {
            index = Math.floor(Math.random() * this.providers.length);
        }

        let provider = this.providers[index];
        if (this.onHold(provider) && this.frozenProviders.size < this.providers.length) {
            console.warn(`Skip frozen provider, address: ${provider.address}, token: ${provider.token}`);

            index = (index + 1) % this.providers.length;
            provider = this.providers[index];
        }

        return provider;
    }

    switch(last, strict) {
        if (!this.providers || this.providers.length <= 0) {
            return null;
        } else if (this.providers.length == 1) {
            return this.providers[0];
        } else if (!last) {
            const index = Math.floor(Math.random() * this.providers.length);
            return this.providers[index];
        }

        // Last request failed, need to cool down for a while
        this.freeze(last);

        // Filtering providers
        const otherProviders = [];
        const adequateProviders = [];
        const unFrozenProviders = [];

        for (const item of this.providers) {
            if (item.address === last.address && (strict || item.token === last.token)) {
                if (item.token !== last.token) {
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
        if (unFrozenProviders.length > 0) {
            return unFrozenProviders[Math.floor(Math.random() * unFrozenProviders.length)];
        } else if (adequateProviders.length > 0) {
            return adequateProviders[Math.floor(Math.random() * adequateProviders.length)];
        } else {
            return otherProviders[Math.floor(Math.random() * otherProviders.length)];
        }
    }

    getNextFreezeDuration(provider) {
        if (!provider) return 0;

        const key = provider.valueOf();
        let count = this.failures.get(key);
        if (!count || count < 0) count = 0;

        count++;
        this.failures.set(key, count);

        const duration = Math.pow(2, count);
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
        return new Response(JSON.stringify({ message: 'Unauthorized', success: false }), {
            status: 401,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    const authToken = accessToken.substring(7).trim();
    const url = new URL(request.url);

    if (['/v1/models', '/v1/chat/completions'].includes(url.pathname) && authToken !== (SECRET_KEY || '')
        || ['/v1/provider/list', '/v1/provider/update', '/v1/provider/reload'].includes(url.pathname)
        && authToken !== (ADMIN_AUTH_TOKEN || '')) {
        return new Response(JSON.stringify({ message: 'Unauthorized', success: false }), {
            status: 401,
            headers: { 'Content-Type': 'application/json' }
        });
    }


    let response;
    if (url.pathname === '/v1/models' && request.method === 'GET') {
        response = await handleListModels();
    } else if (url.pathname === '/v1/chat/completions' && request.method === 'POST') {
        response = await handleProxy(request);
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

async function handleListModels() {
    // List and return all openai models
    return new Response(JSON.stringify({
        "data": await listSupportModels(),
        "object": "list"
    }), {
        status: 200, headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': '*',
            'Content-Type': 'application/json',
        }
    });
}

async function handleProviderList() {
    return new Response(JSON.stringify(await listAllProviders()), {
        status: 200, headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': '*',
            'Content-Type': 'application/json',
        }
    });
}

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

async function handleProxy(request) {
    const requestBody = await request.json();
    const model = (requestBody.model || defaultModel).trim();
    if (!model) {
        return new Response(JSON.stringify({ message: 'Model name cannot be empty', success: false }), {
            status: 400,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    if (!providerSelectorCache.has(model)) {
        const config = await KV.get(model);
        if (!config) {
            return new Response(JSON.stringify({ message: `Not support model '${model}'`, success: false }), {
                status: 400,
                headers: { 'Content-Type': 'application/json' }
            });
        }

        const obj = await createModelProviderSelector(model);
        const commonSelector = obj?.selector;
        const functionCallSelector = obj?.functionEnabledSelector;

        providerSelectorCache.set(model, commonSelector);
        providerSelectorCache.set(providerSelectorCache.generateKey(model, true), functionCallSelector);
    }

    const functionCall = isNotEmptyObject(requestBody.tools) || isNotEmptyObject(requestBody.features);
    const key = providerSelectorCache.generateKey(model, functionCall);

    const selector = providerSelectorCache.get(key);
    if (!selector) {
        let message = `Not found any valid provider for model '${model}'`;
        if (functionCall) {
            message = `Not found any model '${model}' support function call`;
        }

        return new Response(JSON.stringify({ message: message, success: false }), {
            status: 400,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    const isStreamReq = requestBody.stream || false;
    const headers = new Headers(request.headers);

    // Add custom headers
    headers.set('Content-Type', 'application/json');
    headers.set('Path', 'v1/chat/completions');
    headers.set('Accept-Language', 'zh-CN,zh;q=0.9');
    headers.set('Accept-Encoding', 'gzip, deflate, br, zstd');
    headers.set('Accept', 'application/json, text/event-stream');
    headers.set('User-Agent', userAgent);

    const needRemoveHeaders = ['x-forwarded-for', 'CF-Connecting-IP', 'CF-IPCountry', 'CF-Visitor', 'CF-Ray', 'CF-Worker', 'CF-Device-Type'];
    needRemoveHeaders.forEach(key => headers.delete(key));

    let response;
    let provider = null;
    let invalidFlag = false;
    let internalErrorFlag = false;

    for (let retry = 0; retry < maxRetries; retry++) {
        provider = invalidFlag ? selector.switch(provider, internalErrorFlag) : selector.select();
        if (!provider) {
            return new Response(JSON.stringify({ message: 'Service is temporarily unavailable', success: false }), {
                status: 503,
                headers: { 'Content-Type': 'application/json' }
            });
        }

        requestBody.model = provider.realModel;
        requestBody.stream = isStreamReq && provider.streamEnabled;

        const proxyURL = provider.address;
        const accessToken = provider.token;

        console.log(`Selected proxy url: ${proxyURL}, token: ${accessToken}`);

        headers.set('Referer', proxyURL);
        headers.set('Origin', proxyURL);
        headers.set('Host', new URL(proxyURL).host);
        headers.set('X-Real-IP', '8.8.8.8');

        // Remove old authorization header if exist
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

            if (response) {
                // Need switch to next provider
                invalidFlag = switchNextStatusCodes.has(response.status);

                // There might be a problem with the service, switch to the next service directly
                internalErrorFlag = response.status >= 500;

                if (response.ok) {
                    break;
                } else if (response.status === 401) {
                    console.warn(`Found expired provider, address: ${proxyURL}, token: ${accessToken}`);

                    // Flag provider status to dead
                    const text = await KV.get(model);
                    try {
                        const arrays = JSON.parse(text);
                        const providers = [];

                        for (const item of arrays) {
                            if (item.address === proxyURL && item.token === accessToken) {
                                item.alive = invalidStatus;
                            }

                            providers.push(item);
                        }

                        // Save to KV database
                        await KV.put(model, JSON.stringify(providers));

                        // Remove cache for reload
                        providerSelectorCache.remove(key);
                    } catch {
                        console.error(`Update provider status failed due to parse config error, model: ${model}, config: ${text}`);
                    }
                } else if (rateLimitStatusCodes.has(response.status)) {
                    console.warn(`Upstream is busy, address: ${proxyURL}, token: ${accessToken}`);
                } else {
                    console.error(`Failed to request, address: ${proxyURL}, token: ${accessToken}, status: ${response.status}`);
                }
            }
        } catch (error) {
            console.error(`Error during fetch with ${proxyURL}: `, error);
        }
    }

    // No valid response after retries
    if (!response) {
        return new Response(JSON.stringify({ message: 'Internal server error', success: false }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    // Return the original response
    const newHeaders = new Headers(response.headers);
    newHeaders.set('Access-Control-Allow-Origin', '*');
    newHeaders.set('Access-Control-Allow-Methods', '*');

    let newBody = response.body;
    const contentType = response.headers.get('Content-Type') || '';

    if (response.status === 200) {
        // Request succeeded, no cooldown
        selector.unfreeze(provider);

        if (isStreamReq && !contentType.includes('text/event-stream')) {
            // Need text/event-stream but got others
            if (contentType.includes('application/json')) {
                try {
                    const data = await response.json();

                    // 'chatcmpl-'.length = 10
                    const messageId = (data?.id || '').slice(10);

                    const choices = data?.choices
                    if (!choices || choices.length === 0) {
                        return new Response(JSON.stringify({ message: 'No effective response', success: false }), {
                            status: 503,
                            headers: { 'Content-Type': 'application/json' }
                        });
                    }

                    const record = choices[0].message || {};
                    const message = record?.content || '';
                    const content = transformToJSON(message, model, messageId);
                    const text = `data: ${content}\n\ndata: [Done]`;

                    newBody = new ReadableStream({
                        start(controller) {
                            controller.enqueue(new TextEncoder().encode(text));
                            controller.close();
                        }
                    });

                } catch (error) {
                    return new Response(JSON.stringify({ message: 'Internal server error', success: false }), {
                        status: 500,
                        headers: { 'Content-Type': 'application/json' }
                    });
                }
            } else {
                const { readable, writable } = new TransformStream();

                // Transform chunk data to event-stream
                streamResponse(response, writable, model, generateUUID());
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
                    obj.model = model;
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
                return new Response(JSON.stringify({ message: 'Internal server error', success: false }), {
                    status: 500,
                    headers: { 'Content-Type': 'application/json' }
                });
            }
        }
    }

    const newResponse = new Response(newBody, {
        ...response,
        headers: newHeaders
    });

    return newResponse;
}

async function handleProviderUpdate(config) {
    /* structure
    {
      "replace": true,
      "providers": {
          "https://a.com": {
              "token1": {
                  "models": {
                      "gpt-4o": {
                          "functionEnabled": false,
                          "priority": 60
                      },
                      "gpt-4o-mini": {},
                      "o1": {
                          "realModel": "o1-preview",
                          "functionEnabled": true,
                          "priority": 35
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
  */

    if (!config) {
        return new Response(JSON.stringify({ message: 'Invalid config', success: false }), {
            status: 400,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    let replace = false;
    if (config.hasOwnProperty("replace")) {
        replace = config.replace;
    }

    const providers = config?.providers;
    if (!isNotEmptyObject(providers)) {
        return new Response(JSON.stringify({ message: 'New providers cannot be empty', success: false }), {
            status: 400,
            headers: { 'Content-Type': 'application/json' }
        });
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

        const address = url.trim();
        if (!isValidURL(address)) {
            console.warn(`Drop illegal config due to url: ${url} is not valid`);
            return;
        }

        const obj = providers[url];
        if (!isNotEmptyObject(obj)) {
            console.warn(`Ignore invalid config for url: ${url}`);
            return;
        }

        Object.keys(obj).forEach(key => {
            if (typeof key !== "string") {
                console.warn(`Ignore invalid config for url: ${url}, token: ${key} because token must be string`);
                return;
            }

            const token = key.trim();
            const service = obj[key];
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

                item["url"] = address;
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

async function listSupportModels() {
    const items = await KV.list();
    const models = [];

    for (const key of items.keys) {
        if (!key) continue;

        const model = key.name.trim().toLowerCase();
        const brand = model.includes("claude") ? "Anthropic"
            : model.includes("gemini") ? "Google"
                : (model.includes("gpt-") || ["o1", "o1-mini", "o1-preview"].includes(model)) ? "OpenAI" : "Other";
        models.push({
            id: model,
            object: "model",
            created: 1733976732,
            owned_by: brand,
        });
    }

    return models;
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

function isNotEmptyObject(obj) {
    if (!obj) {
        return false;
    }

    return Object.keys(obj).length > 0;
}

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

            const provider = new ModelProvider(url, token, realModel, priority, streamEnabled);
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