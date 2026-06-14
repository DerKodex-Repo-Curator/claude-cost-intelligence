param([string]$Html = "cci-dashboard.html")
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$enc = New-Object System.Text.UTF8Encoding($false)   # UTF-8, no BOM
$html = [System.IO.File]::ReadAllText((Resolve-Path $Html).Path, $enc)
$views = [ordered]@{ overview = 1130; models = 900; sessions = 1080; projects = 840; optimize = 1480; budget = 780 }
$outDir = (Resolve-Path assets).Path
foreach ($v in $views.Keys) {
  $h = $html
  if ($v -ne 'overview') {
    $inject = "<script>show('$v');</script></body>"
    $h = $h.Replace('</body>', $inject)
  }
  $tmp = Join-Path $outDir ("_t_" + $v + ".html")
  [System.IO.File]::WriteAllText($tmp, $h, $enc)
  $uri = ([Uri]$tmp).AbsoluteUri
  $out = Join-Path $outDir ("dash-" + $v + ".png")
  $prof = Join-Path $env:TEMP ("edge" + (Get-Random))
  $a = @('--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--hide-scrollbars', ('--user-data-dir=' + $prof), ('--window-size=1320,' + $views[$v]),
    '--virtual-time-budget=3000', ('--screenshot=' + $out), $uri)
  Start-Process -FilePath $edge -ArgumentList $a -Wait -NoNewWindow
  Remove-Item -Recurse -Force $prof -ErrorAction SilentlyContinue
  Remove-Item -Force $tmp -ErrorAction SilentlyContinue
  if (Test-Path $out) { "{0,-10} {1} KB" -f $v, [int]((Get-Item $out).Length / 1KB) } else { "$v FAILED" }
}
