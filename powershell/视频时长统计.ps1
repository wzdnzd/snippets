$Directory = ""
$Shell = New-Object -ComObject Shell.Application
Get-ChildItem -Path $Directory -Recurse -Force -Include *.mp4, *.avi, *.flv, *.wmv, *.mkv | ForEach-Object {
    $Folder = $Shell.Namespace($_.DirectoryName)
    $File = $Folder.ParseName($_.Name)
    $Duration = $Folder.GetDetailsOf($File, 27)
    [PSCustomObject]@{
        Name     = $_.Name
        Size     = "$([int]($_.length / 1mb)) MB"
        Duration = $Duration
    }
} | Export-Csv -Path "$Directory/统计.csv" -NoTypeInformation -Encoding UTF8

read-Host -Prompt "视频时长统计完毕，结果文件保存在 $Directory，按Enter键退出...";