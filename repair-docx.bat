@REM author: wzdnzd
@REM date: 2024-01-04
@REM describe: 修复 word 文档中的图片丢失问题

@echo off
setlocal enabledelayedexpansion

@REM 设置编码为 UTF-8
chcp 65001 >nul 2>nul

@REM 7zip（7z.exe）解压软件绝对路径
set "zipPath="

@REM word文件目录
set "docsPath="

@REM 图片文件路径
set "picturePath="

@REM 待替换的图片文件路径
set "destPicturePath=word\media\water.png"

for %%F in ("!docsPath!\*.docx") do (
    @REM 复制文件并重命名为 .zip 文件
    copy /Y "%%F" "%%~dpnF.zip" >nul 2>nul

    @REM 解压文件 
    "!zipPath!" x "%%~dpnF.zip" -o"%%~dpnF" >nul 2>nul

    @REM 删除原来的 .zip 文件
    del "%%~dpnF.zip" >nul 2>nul

    @REM 复制图片文件到解压后的文件夹 media 目录下
    copy /Y "!picturePath!" "%%~dpnF\%destPicturePath%" >nul 2>nul

    @REM 压缩文件夹为 .zip 文件
    "!zipPath!" a -tzip "%%~dpnF.zip" "%%~dpnF\*" >nul 2>nul

    @REM 修复后的文件名
    set "filename=%%~dpFrepaired\%%~nF.docx"

    @REM 如果 repired 文件夹不存在，则创建
    if not exist "%%~dpFrepaired" mkdir "%%~dpFrepaired" >nul 2>nul

    @REM 如果目标文件已存在，则删除
    if exist "!filename!" del "!filename!" >nul 2>nul

    @REM 移动 .zip 文件 到 目标文件
    move /Y "%%~dpnF.zip" "!filename!" >nul 2>nul

    @REM 删除解压后的文件夹
    rd /S /Q "%%~dpnF" >nul 2>nul

    @echo 文件 "%%~fF" 修复完成，修复后的文件名为："!filename!"
)
