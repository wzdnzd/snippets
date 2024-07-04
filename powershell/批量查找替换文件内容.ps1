$filepath = 'C:\Users\mego\Downloads'
Get-ChildItem $filepath -Recurse -Include *.html | ForEach-Object -Process {
    if ($_ -is [System.IO.FileInfo]) {
        $filename = $_.name.split(".")[0];
        $content = get-content $_.pspath;
        clear-content $_.pspath;
        foreach ($line in $content) {
            $liner = $line -Replace 'src="mp3/\w+.mp3"', "src=`"mp3/$filename.mp3`"";
            if ($line -match 'src="mp3/\w+.mp3"') {
                Write-Output $liner
            }
            
            Add-content $_.pspath -Value $liner;
        }
    }
}