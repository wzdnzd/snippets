# 需求：https://www.52pojie.cn/thread-1648648-1-1.html

# html文件夹路径
$filepath = '';

# 获取 $filepath 目录下所有.html文件并遍历处理
Get-ChildItem $filepath -Recurse -Include *.html | ForEach-Object -Process{
    # 判断是否是文件，只对文件做处理
    if ($_ -is [System.IO.FileInfo]) {
        # 取文件名，如880609.html 则结果为880609
        $filename = $_.name.split(".")[0];

        # 上一页文件名，通过当前文件名-1获取，如当前文件名为880609.html，则上一页文件名为880608.html
        $pre_page = "$($filename - 1).html";

        # 下一页文件名，通过当前文件名+1获取，如当前文件名为880609.html，则上一页文件名为880610.html
        $next_page = "$(1 + $filename).html";
        
        $text = "`<a href=`"index.html`"`>回目录`<`/a`>";

        # 判断上一页对应的html文件是否存在，存在则插入，如当前文件为880609.html，则上一页文件为880608.html
        if($(Test-Path $filepath\\$pre_page) -eq "True") {
            $text = "`<a href=`"$pre_page`"`>上一页`<`/a`> " + $text;
        }

        # 判断下一页对应的html文件是否存在，存在则插入，如当前文件为880609.html，则上一页文件为880610.html
        if($(Test-Path $filepath\\$next_page) -eq "True") {
            $text = $text + " `<a href=`"$next_page`"`>下一页`<`/a`>";
        }

        # $text即为最终要插入html的内容
        $text = "`<p class=`"daoh`"`>" + $text + "`<`/p`>";
        
        # 读取当前html的内容，如880609.html文件里的内容
        $content = get-content $_.pspath -Encoding utf8;

        # 删除当前html文件里的内容，因为内容已经暂时读取到内存
        clear-content $_.pspath;
  
        # 插入动作需要确定在哪两行之间进行，该变量用于标识是否匹配前一行，至于匹配内容是什么，可修改正则表达式
        # 本脚本根据提供的样例文件，决定在<p class="A0">第一章 XXXXXXXX</p>下方的<hr />与<p>　</p>之间插入超链接
        $pre_match = 0;

        # 是否已经在<p class="A0">第一章 XXXXXXXX</p>下方插入过，未插入过才会插入超链接
        $inserted = 0;

        # 遍历每一行，通过特定逻辑确定插入位置
        foreach ($line in $content){
            # 正如上面所说，需要在<hr />与<p>　</p>之间插入超链接，故判断是否匹配<hr />
            if ($line -match '<hr[\s\S]*>') {                  
                $pre_match = 1;
            }

            # 是否匹配<p>　</p>，如果前面已经匹配到<hr />，现在又匹配到<p>　</p>，并且是第一次匹配到，则先插入超链接
            if ($line -match '<p>(\s+)?</p>' -and $pre_match -eq 1 -and $inserted -eq 0) {
                # 插入超链接，因为是在写回<p>　</p>之前插入，所以等价于在<hr />与<p>　</p>之间插入
                Add-content $_.pspath -Value $text -Encoding utf8;

                # 将状态置1，之后不会再插入，即只插入一次
                $inserted = 1;
            }
            
            # 将原来html的一行内容写回到html文件
            Add-content $_.pspath -Value $line -Encoding utf8;

            # 判断当前行是否是<p class="B0">书名：XXXXXXXX</p>，如果是则在其下方插入超链接
            if ($line -match '<p class="B0[\s\S]*>') {
                Add-content $_.pspath -Value $text -Encoding utf8;
            }
        }
    }
}