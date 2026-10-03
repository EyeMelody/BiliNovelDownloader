param(
    [string]$Python = 'python'
)
# 打包发行版：建置 exe、组装 release 资料夹、压 zip、核对必备档案。
# 用法见 RELEASING.md。前置需求：tools\ 内恰有一颗 bili_novel_packer exe、
# 环境装齐 requirements.txt 与 pyinstaller。
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot

$version = (Get-Content (Join-Path $repo 'version.txt') -TotalCount 1).Trim()
if ($version -notmatch '^v\d+\.\d+\.\d+$') { throw "version.txt 版号格式不符：'$version'" }

$name  = "BiliNovelDownloader-$version-windows-x64"
$stage = Join-Path $repo $name
$zip   = "$stage.zip"

$packer = @(Get-ChildItem (Join-Path $repo 'tools') -Filter 'bili_novel_packer*.exe' | Where-Object { $_.Name -notlike '*-gui.exe' })
if ($packer.Count -ne 1) { throw "tools\ 内应恰有一颗 bili_novel_packer exe，目前有 $($packer.Count) 颗" }

if (Test-Path $stage) { throw "输出目录已存在，请先另行保存或选择新的版本号：$stage" }
if (Test-Path $zip) { throw "压缩包已存在：$zip" }

Write-Host "== PyInstaller 建置（$version）=="
Push-Location $repo
& $Python -m PyInstaller 'BiliNovelDownloader.spec' --noconfirm
$code = $LASTEXITCODE
Pop-Location
if ($code -ne 0) { throw "PyInstaller 失败（exit $code）" }
$exe = Join-Path $repo 'dist\BiliNovelDownloader.exe'
if (-not (Test-Path $exe)) { throw "找不到建置产物 $exe" }

Write-Host "== 组装 $name =="
New-Item -ItemType Directory -Path (Join-Path $stage 'tools') -Force | Out-Null
Copy-Item $exe $stage
Copy-Item (Join-Path $repo 'LICENSE') (Join-Path $stage 'LICENSE.txt')
Copy-Item (Join-Path $repo 'NOTICES.txt') $stage
Copy-Item (Join-Path $repo 'THIRD_PARTY_LICENSES.txt') $stage
Copy-Item (Join-Path $PSScriptRoot 'readme.txt') $stage
Copy-Item $packer[0].FullName (Join-Path $stage 'tools')
Copy-Item (Join-Path $repo 'tools\LICENSE-bili_novel_packer.txt') (Join-Path $stage 'tools')
Copy-Item (Join-Path $repo 'tools\README.md') (Join-Path $stage 'tools')

Write-Host "== 压缩 =="
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -Force

Write-Host "== 核对必备档案 =="
$required = @(
    'BiliNovelDownloader.exe', 'LICENSE.txt', 'NOTICES.txt',
    'THIRD_PARTY_LICENSES.txt', 'readme.txt',
    ('tools\' + $packer[0].Name), 'tools\LICENSE-bili_novel_packer.txt', 'tools\README.md'
)
$missing = @()
foreach ($f in $required) {
    if (Test-Path (Join-Path $stage $f)) { Write-Host "  OK  $f" }
    else { Write-Host "  缺  $f"; $missing += $f }
}
if ($missing.Count -gt 0) { throw "缺少必备档案：$($missing -join '、')" }

$hash = (Get-FileHash $zip -Algorithm SHA256).Hash
Write-Host ''
Write-Host "完成：$zip"
Write-Host "SHA256：$hash"
