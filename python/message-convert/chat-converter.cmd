@REM author: wzdnzd
@REM date: 2025-03-19
@REM describe: chat converter for lobechat, nextchat, cherrystudio

@echo off & PUSHD %~DP0 

@REM 设置代码页为UTF-8，以处理中文
chcp 65001 >nul 2>nul

@REM 启用延迟变量扩展
setlocal enabledelayedexpansion

@REM 执行转换
goto :convert


@REM 转换
:convert
@REM 工作目录
set "workspace="

@REM 源格式
set "source="

@REM 目标格式
set "target="

@REM 输入文件
set "input="

@REM 输出文件
set "output="

@REM 是否覆盖已存在的聊天记录，默认追加
set "replace=0"

@REM 用户ID
set "user="

@REM 数据库URL
set "database="

@REM 如果参数为空，则打印使用信息
if "%1" == "" (
    goto :usage
    exit /b 1
)

@REM 解析命令行参数
call :argsparse %*
if !errorlevel! NEQ 0 (
    exit /b 1
)

@REM 如果 workspace 为空，则设置为当前目录
if "!workspace!" == "" set "workspace=%~dp0"

@REM 验证参数是否符合要求
call :check_params

@REM 参数不合法
if !errorlevel! NEQ 0 (
    exit /b 1
)

@REM 完整路径
set "input=!workspace!\!input!"
set "output=!workspace!\!output!"

@echo [信息] 开始执行转换

@REM 覆盖
if !replace! EQU 1 (
    python -u "D:\\Applications\\Tools\\Cmds\\chat-converter.py" -s "!source!" -t "!target!" -i "!input!" -o "!output!" -u "!user!" -d "!database!" -w
) else (
    python -u "D:\\Applications\\Tools\\Cmds\\chat-converter.py" -s "!source!" -t "!target!" -i "!input!" -o "!output!" -u "!user!" -d "!database!"
)

@echo [信息] 转换完成！
exit /b 0


:argsparse
set "result=false"

if "%1" == "-s" set "result=true"
if "%1" == "--source" set "result=true"
if "!result!" == "true" (
    call :trim source "%~2"
    set "result=false"
    shift & shift & goto :argsparse
)

if "%1" == "-t" set "result=true"
if "%1" == "--target" set "result=true"
if "!result!" == "true" (
    call :trim target "%~2"
    set "result=false"
    shift & shift & goto :argsparse
)

if "%1" == "-i" set "result=true"
if "%1" == "--input" set "result=true"
if "!result!" == "true" (
    call :trim input "%~2"
    set "result=false"
    shift & shift & goto :argsparse
)

if "%1" == "-o" set "result=true"
if "%1" == "--output" set "result=true"
if "!result!" == "true" (
    call :trim output "%~2"
    set "result=false"
    shift & shift & goto :argsparse
)

if "%1" == "-u" set "result=true"
if "%1" == "--user" set "result=true"
if "!result!" == "true" (
    call :trim user "%~2"
    set "result=false"
    shift & shift & goto :argsparse
)

if "%1" == "-d" set "result=true"
if "%1" == "--database" set "result=true"
if "!result!" == "true" (
    call :trim database "%~2"
    set "result=false"
    shift & shift & goto :argsparse
)

if "%1" == "-r" set "result=true"
if "%1" == "--replace" set "result=true"
if "!result!" == "true" (
    set "replace=1"
    set "result=false"
    shift & goto :argsparse
)

if "%1" == "-w" set "result=true"
if "%1" == "--workspace" set "result=true"
if "!result!" == "true" (
    call :trim workspace "%~2"
    set "result=false"
    shift & shift & goto :argsparse
)

if "%1" == "-h" set result=true
if "%1" == "--help" set result=true
if "!result!" == "true" (
    call :usage
    exit /b 1
)

if "%1" == "" goto :eof
call :usage
exit /b 1


@REM 使用方式
:usage
@echo 使用方式：%~nx0 -s source -t target -i input -o output -u uid -d database -w
@echo.
@REM @echo.
@echo 参数说明：
@REM @echo.
@echo -s 源格式，可选值：lobechat, nextchat, cherrystudio
@REM @echo.
@echo -t 目标格式，可选值：lobechat, nextchat, cherrystudio
@REM @echo. 
@echo -i 输入文件路径（当源格式为 nextchat 和 cherrystudio 时，必须提供）
@REM @echo.
@echo -o 输出文件路径（当目标格式为 nextchat 和 cherrystudio 时，必须提供）
@REM @echo.
@echo -u 用户ID（当源格式或目标格式为 lobechat 时，必须提供）
@REM @echo.
@echo -d 数据库URL（当源格式或目标格式为 lobechat 时，必须提供）
@REM @echo.
@echo -r 是否覆盖已存在的聊天记录，默认追加
@REM @echo.
@echo -w 工作目录

goto :eof


@REM 去除字符串两端的空格
:trim <result> <rawtext>
set "rawtext=%~2"
set "%~1="
if "!rawtext!" == "" goto :eof

for /f "tokens=* delims= " %%a in ("!rawtext!") do set "rawtext=%%a"

@REM 为了速度，只迭代10次
for /l %%a in (1,1,10) do if "!rawtext:~-1!"==" " set "rawtext=!rawtext:~0,-1!"

set "%~1=!rawtext!"
goto :eof


@REM 验证参数是否符合要求
:check_params
@REM 工作目录不存在
if not exist "!workspace!" (
    @echo [错误] 工作目录不存在，工作目录路径：!workspace!
    exit /b 1
)

@REM 源格式只能为 lobechat、nextchat、cherrystudio
if "!source!" == "" (
    @echo [错误] 源格式不能为空
    exit /b 1
)
if "!source!" NEQ "lobechat" if "!source!" NEQ "nextchat" if "!source!" NEQ "cherrystudio" (
    @echo [错误] 源格式只能为 lobechat、nextchat、cherrystudio
    exit /b 1
)

@REM 目标格式只能为 lobechat、nextchat、cherrystudio
if "!target!" == "" (
    @echo [错误] 目标格式不能为空
    exit /b 1
)
if "!target!" NEQ "lobechat" if "!target!" NEQ "nextchat" if "!target!" NEQ "cherrystudio" (
    @echo [错误] 目标格式只能为 lobechat、nextchat、cherrystudio
    exit /b 1
)

@REM 如果源格式为 nextchat 或 cherrystudio，则输入文件不能为空或者不存在
set "need_input=0"
if "!source!" == "nextchat" set "need_input=1"
if "!source!" == "cherrystudio" set "need_input=1"

if "!need_input!" == "1" (
    if "!input!" == "" (
        @echo [错误] 输入文件不能为空
        exit /b 1
    )

    if not exist "!workspace!\!input!" (
        @echo [错误] 输入文件不存在，输入文件路径：!workspace!\!input!
        exit /b 1
    )
)

@REM 如果目标格式为 nextchat 或 cherrystudio，则输出文件不能为空或者不存在
set "need_output=0" 
if "!target!" == "nextchat" set "need_output=1"
if "!target!" == "cherrystudio" set "need_output=1"

if "!need_output!" == "1" (
    if "!output!" == "" (
        @echo [错误] 输出文件不能为空
        exit /b 1
    )

    if not exist "!workspace!\!output!" (
        @echo [错误] 输出文件不存在，输出文件路径：!workspace!\!output!
        exit /b 1
    )
)

@REM 如果源格式或者目标格式 lobechat，则用户ID 和 数据库链接不能为空
set "has_lobechat=0"
if "!source!" == "lobechat" set "has_lobechat=1"
if "!target!" == "lobechat" set "has_lobechat=1"

if "!has_lobechat!" == "1" (
    if "!user!" == "" (
        @echo [错误] 用户ID不能为空
        exit /b 1
    )

    if "!database!" == "" (
        @echo [错误] 数据库链接不能为空
        exit /b 1
    )
)

goto :eof

endlocal