param([string]$filepath, [int]$num);

if ($(Test-Path $filepath) -ne "True") {
    Write-Output "文件夹$filepath不存在";
    exit 1;
}

$outputpath = "$filepath\merged";
if ($(Test-Path $outputpath) -ne "True") {
    mkdir $outputpath;
}

$count = 0;
Get-ChildItem -Path $filepath -Recurse -Include *.txt -Exclude merged | ForEach-Object -Process {
    if ($_ -is [System.IO.FileInfo]) {
        if ($count % $num -eq 0) {
            $filename = $(Split-Path -Path $_.name -Leaf -Resolve);
            $filename = "$outputpath\$filename";
        }

        Write-Output "正在合并: $_";
        $content = get-content $_.pspath -Encoding utf8;
        foreach ($line in $content) {
            Add-content $filename -Value $line -Encoding utf8;
        }

        $count += 1;
    }
}

read-Host -Prompt "文件合并完毕，文件保存在$outputpath，按Enter键退出...";