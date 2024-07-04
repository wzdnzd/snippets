# txt文件夹路径
$filepath = 'C:\Users\mego\Downloads';

# 结果保存路径
$outputfile = "$filepath\数据文件.xlsx";

# 结果文件存在则删除
if ($(Test-Path $outputfile) -eq "True") {
    Remove-Item -Path $outputfile -Force;
}

$excel = New-Object -ComObject Excel.Application;
$workbook = $excel.Workbooks.Add();
$sheet = $workbook.Worksheets.Item(1);
$sheet.Name = '数据';

$count = 0;
# 获取 $filepath 目录下所有.txt文件并遍历处理
Get-ChildItem $filepath -Recurse -Include *.txt | ForEach-Object -Process {
    # 判断是否是文件，只对文件做处理
    if ($_ -is [System.IO.FileInfo]) {
        $count += 1;

        Write-Output "正在处理：$_";

        $filename = $_.name.split(".")[0];

        # 读取当前文件内容
        $content = get-content $_.pspath -Encoding utf8;
    
        $match = 0;

        # 遍历每一行
        $dataset = @()
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
                $dataset += $line;
            }
        }

        $m = 2 * $count - 1;
        $n = 2 * $count;

        $sheet.Cells.Item(1, $m) = $filename;
        
        # 合并单元格
        $sheet.Range($sheet.Cells(1, $m), $sheet.Cells(1, $n)).Merge();
        # 居中显示
        $sheet.Range($sheet.Cells(1, $m), $sheet.Cells(1, $n)).HorizontalAlignment = -4108;

        $sheet.Cells.Item(2, $m) = "nm";
        $sheet.Cells.Item(2, $n) = "Data";

        $line = 3;
        foreach ($row in $dataset) {
            $words = $row.split(",");
            $sheet.Cells.Item($line, $m) = $words[0];
            $sheet.Cells.Item($line, $n) = $words[1];
            $line++;
        }
    }
}

$workbook.SaveAs($outputfile);
$excel.Quit();

read-Host -Prompt "数据提取完毕，文件保存在$outputfile，按Enter键退出...";