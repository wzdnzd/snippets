'
' @Author: wzdnzd
' @Date: 2022-02-10 09:14:29
' @Description: 
' Copyright (c) 2022 by wzdnzd, All Rights Reserved.
'
set ws=WScript.CreateObject("Shell.Application")

' execute
' ws.ShellExecute "cmd.exe", "/c (scoop update * && scoop cleanup * && scoop cache rm * && scoop update) & (scoop list | findstr ""typora"" && (if exist ""%SCOOP%\persist\typora\winmm.dll"" if not exist ""%SCOOP%\apps\typora\current\winmm.dll"" (mklink ""%SCOOP%\apps\typora\current\winmm.dll"" ""%SCOOP%\persist\typora\winmm.dll""))) & pip-review --auto --continue-on-fail", , "runas", 0

ws.ShellExecute "cmd.exe", "/c (scoop update * && scoop cleanup * && scoop cache rm * && scoop update) & (scoop list | findstr ""emeditor"" >nul 2>nul && (if exist ""%SCOOP%\persist\emeditor\mui"" (dir /a /l ""%SCOOP%\apps\emeditor\current"" | find ""<SYMLINKD>"" | find ""mui"" >nul 2>nul || ((if exist ""%SCOOP%\apps\emeditor\current\mui-bak"" (rd /s /q ""%SCOOP%\apps\emeditor\current\mui-bak"" >nul 2>nul)) & ren ""%SCOOP%\apps\emeditor\current\mui"" ""mui-bak"" >nul 2>nul && mklink /d ""%SCOOP%\apps\emeditor\current\mui"" ""%SCOOP%\persist\emeditor\mui"" >nul 2>nul)))) & pip-review --auto --continue-on-fail", , "runas", 0

set ws = Nothing