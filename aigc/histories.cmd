@REM https://github.com/Chanzhaoyu/chatgpt-web
@REM fofa-hack.exe -k "title='ChatGPT Web'&&is_domain=true" -o txt -e 5000
fofa-hack.exe -k "'loading-wrap' && 'balls' && 'chat' && is_domain=true" -o txt -e 5000
python -u check.py -d -f data/from-fofa/chatgpt-web-material.txt -l /api/chat-process,/openapi/v1/chat/completions,/chat-process,/api -r chatgpt-web-sites.txt -s 1

@REM https://github.com/lobehub/lobe-chat
fofa-hack.exe -k "title='LobeChat'&&is_domain=true" -o txt -e 2000
python -u check.py -d -f data/from-fofa/lobechat-material.txt -l /api/chat/openai -r lobechat-sites.txt -s 0

@REM https://github.com/ChatGPTNextWeb/ChatGPT-Next-Web
fofa-hack.exe -k "(title='NextChat'||title='ChatGPT Next Web')&&is_domain=true" -o txt -e 20000
python -u check.py -d -f data/from-fofa/nextweb-material.txt -l /api/openai/v1/chat/completions,/api/chat-stream -r nextweb-sites.txt -s 0


@REM https://github.com/aurorax-neo/free-gpt3.5-2api
fofa-hack.exe -k "body=free-gpt3.5-2api" -o txt -e 2000
python -u check.py -d -f data/from-fofa/free-gpt3.5-2api-material.txt -l /v1/chat/completions -r free-gpt3.5-2api.txt -s 0

@REM oneapi or newapi
fofa-hack.exe -k "(title='One API' || title='New API') && is_domain=true" -o txt -e 10000
python -u check.py -d -o -f data/from-fofa/oneapi-material.txt -r oneapi.txt

@REM https://github.com/teralomaniac/clewd
fofa-hack.exe -k "clewd修改版" -o txt -e 2000
python -u check.py -d -f data/from-fofa/clewd-tera-material.txt -l /v1/chat/completions -r clewd-tera.txt -s 0 -m claude-3-5-sonnet-20240620

@REM https://github.com/open-webui/open-webui
fofa-hack.exe -k "title='Open WebUI' && is_domain=true" -o txt -e 10000
python -u check.py -d -o -f data/from-fofa/openwebui-material.txt -r openwebui-sites.txt

@REM https://github.com/danny-avila/LibreChat
fofa-hack.exe -k "title='LibreChat' && is_domain=true" -o txt -e 10000
python -u check.py -d -o -f data/from-fofa/librechat-material.txt -r librechat-sites.txt

@REM https://github.com/ourongxing/chatgpt-vercel
fofa-hack.exe -k "icon_hash='-932334720' && is_domain=true" -o txt -e 10000
python -u check.py -d -o -f data/from-fofa/ourongxing-chatgpt-vercel-material.txt -l /api -r ourongxing-chatgpt-vercel-sites.txt

@REM https://linux.do/t/topic/294966
fofa-hack.exe -k "title='LiteLLM API - Swagger UI'" -o txt -e 10000
python -u check.py -d -e -o -m gpt-4o -f data/from-fofa/litellm-material.txt -l /v1/chat/completions -r litellm-sites.txt

@REM https://github.com/zmh-program/chatnio