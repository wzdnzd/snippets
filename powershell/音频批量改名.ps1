$Directory = Split-Path -Parent $MyInvocation.MyCommand.Definition;
$Shell = New-Object -ComObject Shell.Application;
Get-ChildItem -Path $Directory -Recurse -Force -Include *.mp3, *.flac, *.ape, *.wav, *.aac | ForEach-Object {
    $Folder = $Shell.Namespace($_.DirectoryName);
    $File = $Folder.ParseName($_.Name);
    $Title = $Folder.GetDetailsOf($File, 21);

    $NewName = $Title + $_.extension;
    $Num = 1;

    $Filepath = Split-Path -Parent $File.Path
    while ($(Test-Path $Filepath\\$NewName) -eq "True") {
        if ($Num -lt 10) {
            $NewName = $Title + "-0$Num" + $_.extension;
        }
        else {
            $NewName = $Title + "-$Num" + $_.extension;
        }

        $Num += 1;
    }

    Write-Output "原文件名：$($_.Name)    新文件名：$NewName";

    Rename-Item $_.FullName -NewName $NewName;

    # 查看详情里每个属性对应的索引
    # 0..287 | Foreach-Object { '{0} = {1}' -f $_, $Folder.GetDetailsOf($null, $_) }
}

read-Host -Prompt "文件批量重命名结束，按Enter键退出...";