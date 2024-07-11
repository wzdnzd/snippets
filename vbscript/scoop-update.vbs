'
' @Author: wzdnzd
' @Date: 2022-02-10 09:14:29
' @Description: 
' Copyright (c) 2022 by wzdnzd, All Rights Reserved.
'
set ws=WScript.CreateObject("Shell.Application")

' execute
' ws.ShellExecute "cmd.exe", "/c (scoop update * && scoop cleanup * && scoop cache rm * && scoop update) & (scoop list | findstr ""typora"" && (if exist ""%SCOOP%\persist\typora\winmm.dll"" if not exist ""%SCOOP%\apps\typora\current\winmm.dll"" (mklink ""%SCOOP%\apps\typora\current\winmm.dll"" ""%SCOOP%\persist\typora\winmm.dll""))) & pip-review --auto --continue-on-fail", , "runas", 0

ws.ShellExecute "cmd.exe", "/c (scoop update * && scoop cleanup * && scoop cache rm * && scoop update) & pip-review --auto --continue-on-fail", , "runas", 0

set ws = Nothing