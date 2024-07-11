' auto check and update clash config in local machine

dim args
dim display
dim mode

set args = WScript.Arguments

display = "0"
mode = "1"


' the number of arguments
dim count
count = args.Count

dim i, flag
for i = 0 to count - 1
    flag = LCase(args(i))
    if flag = "-c" or flag = "--crawl" then
        mode = "0"
    elseif flag = "-s" or flag = "--show" then
        display = "1"
    end if
next


dim environment
environment = ".env.test"
if mode = "0" then
    environment = ".env.dev"
end if


dim workspace
dim npctl
dim script
dim log

' workspace absolute path
workspace = "D:\ProgramProjects\Python\aggregator\"

' npctl absolute path
npctl = "D:\Applications\Clash\npctl.cmd"

' process.py absolute path
script = workspace & "subscribe\process.py"

' log file absolute path
log = workspace & "workflow.log"


set fso = CreateObject("Scripting.FileSystemObject")

' delete log file if exists
if fso.FileExists(log) then
    fso.DeleteFile log, true
end if

set fso = Nothing


dim command

' crawl mode
command = "python -u """ & script & """ " & "-o -e " & environment

' test mode
if mode = "1" then
    ' command = npctl & " -k && echo. && python -u " & script & " --overwrite && echo. && " & npctl & " -r && " & npctl & " -u -q"
    command = npctl & " -k && echo. && " & command & " && echo. && " & npctl & " -r && " & npctl & " -u -q"
else
    command = "cmd /c " & command
end if

' pause if display is true
if display = "1" then
    command = command & " && echo. && pause"
end if


' run command
set ws = WScript.CreateObject("WScript.Shell")
ws.Run command, display, true

set ws = Nothing
