$text = "";
$filepath = "";

$files = Get-ChildItem $filepath\*.xls* -recurse;

$Excel = New-Object -ComObject Excel.Application;
$Excel.visible = $false;
$Excel.DisplayAlerts = $false;

Write-Output "查找内容为：$text"
Write-Output ""
Write-Output "包含'$text'的Excel文件如下："

ForEach ($file in $files) {
    $WorkBook = $Excel.Workbooks.Open($file.Fullname);

    foreach ($sht In $WorkBook.Worksheets) {
        $row = $sht.Rows.Count;
        $c = $sht.Range("1:$row").Find($text);
        if ($c) {
            Write-Output $file.Fullname;
        }
    }
}

# cleanup
$Excel.Quit();
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($WorkBook) | Out-Null;
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($Excel) | Out-Null;
[System.GC]::Collect();
[System.GC]::WaitForPendingFinalizers();

Write-Output ""
read-Host -Prompt "Press Enter to exit"