param([string]$filepath);

if ($(Test-Path $filepath) -ne "True") {
    Write-Output "文件夹$filepath不存在";
    exit 1;
}

Get-ChildItem -Path $filepath -Recurse -Include *.txt | ForEach-Object -Process {
    if ($_ -is [System.IO.FileInfo]) {
        $filename = $_.name.split(".")[0];
        if ($filename -match '^[0-9a-zA-Z]*$') {
            Write-Output "文件名只包含数字或字母，删除中：$_";
            Remove-Item -Path $_.pspath -Force;
            return;
        }

        $content = get-content $_.pspath -Encoding utf8;
        $content = $content -Replace "\s+", "";
        if ($content -eq "") {
            Write-Output "文件内容为空，删除中：$_";
            Remove-Item -Path $_.pspath -Force;
        }
    }
}

read-Host -Prompt "处理完毕，按Enter键退出...";