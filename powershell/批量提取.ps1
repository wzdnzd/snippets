[Console]::OutputEncoding = [System.Text.Encoding]::Default

# txt文件夹路径
$filepath = 'C:\Users\mego\Downloads';

# 结果保存路径
$outputfile = "$filepath\数据文件.csv";

# 结果文件存在则删除
if($(Test-Path $outputfile) -eq "True") {
    Remove-Item -Path $outputfile -Force;
}

# csv文件标题
Add-content $outputfile -Value "nm,Data" -Encoding utf8;

# 获取 $filepath 目录下所有.txt文件并遍历处理
Get-ChildItem $filepath -Recurse -Include *.txt | ForEach-Object -Process {
    # 判断是否是文件，只对文件做处理
    if ($_ -is [System.IO.FileInfo]) {        
        # 读取当前文件内容
        $content = get-content $_.pspath -Encoding utf8;
    
        $match = 0;

        # 遍历每一行
        foreach ($line in $content) {
            # 匹配开头的'nm Data'，可替换为需要的内容
            if ($line -match 'nm\s+Data') {                  
                $match = 1;
                continue;
            }

            # 匹配结尾，默认空行，可替换为其他字符串
            elseif ($match -eq 1 -and $line -eq "") {
                break;
            }

            if ($match -eq 1) {
                $line = $line -replace "\s+", ",";
                Add-content $outputfile -Value $line -Encoding utf8;
            }
        }
    }
}

read-Host -Prompt "数据提取完毕，文件保存在$outputfile，按Enter键退出..."