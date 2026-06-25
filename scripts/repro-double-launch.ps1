<#
.SYNOPSIS
  wagom-player の「二重ウィンドウ」バグを、Explorer のダブルクリックに頼らず
  決定論的に再現するハーネス。

  ログ(last-run.txt)で確認した不具合条件＝「同一ファイル引数の2プロセスが
  ほぼ同時(0ms差)に起動」をスクリプトから直接作り出す。
  各試行ごとに既存プロセスを落として "コールドスタート" を再現する。

.PARAMETER ExePath
  起動する exe。既定はインストール版(Explorer が実際に叩くのと同じ実体)。
  修正版を検証するときは dist のものを指す:
    -ExePath "C:\dev\web\wagom-player\dist\wagom-player\wagom-player.exe"

.PARAMETER File
  開く動画ファイル。未指定なら scratchpad にダミー .mp4 を作って使う。
  (シングルインスタンス判定はVLC再生より前に走るので、再生可否は結果に無関係)

.PARAMETER Iterations
  試行回数。

.PARAMETER WaitSeconds
  起動後、生存プロセス数を数えるまでの待ち時間。

.EXAMPLE
  pwsh -File repro-double-launch.ps1 -Iterations 30
#>
param(
    [string]$ExePath = "C:\Program Files\wagom-player\wagom-player.exe",
    [string]$File = "",
    [ValidateRange(1, 100000)]
    [int]$Iterations = 30,
    [ValidateRange(0, 3600)]
    [double]$WaitSeconds = 4
)

$ErrorActionPreference = "Stop"
$procName = "wagom-player"
$logDir = Join-Path $env:LOCALAPPDATA "wagom-player\logs"

if (-not (Test-Path -LiteralPath $ExePath)) { throw "exe not found: $ExePath" }

# --- 開くファイルを用意（未指定ならダミー mp4 を作る） ---
if (-not $File) {
    $File = Join-Path $env:TEMP "wagom-repro-sample.mp4"
    if (-not (Test-Path -LiteralPath $File)) {
        # 中身は何でもよい（プレイヤーの再生可否は単一インスタンス判定に無関係）
        [System.IO.File]::WriteAllBytes($File, (New-Object byte[] 1024))
    }
}
# 明示指定したパスは存在確認する（typo で無言起動するのを防ぐ）
if (-not (Test-Path -LiteralPath $File)) { throw "file not found: $File" }
Write-Host "exe : $ExePath"
Write-Host "file: $File"
Write-Host "iterations: $Iterations`n"

function Stop-AllWagom {
    Get-Process -Name $procName -ErrorAction SilentlyContinue | ForEach-Object {
        try { $_.Kill() } catch {}
    }
    # 完全終了＝名前付きパイプ解放＝"起動中インスタンス無し" を保証
    for ($i = 0; $i -lt 50; $i++) {
        if (-not (Get-Process -Name $procName -ErrorAction SilentlyContinue)) { return }
        Start-Sleep -Milliseconds 100
    }
    throw "wagom-player processes did not exit"
}

# 2プロセスを限界まで同時に起動する。
# .NET Process.Start を2回連続で呼ぶ（間隔 < 数ms）。これでログにあった
# 0ms 同時起動とほぼ同条件になる。
function Start-TwoSimultaneously {
    param([string]$Exe, [string]$Arg)
    $psi1 = New-Object System.Diagnostics.ProcessStartInfo
    $psi1.FileName = $Exe; $psi1.Arguments = '"' + $Arg + '"'; $psi1.UseShellExecute = $true
    $psi2 = New-Object System.Diagnostics.ProcessStartInfo
    $psi2.FileName = $Exe; $psi2.Arguments = '"' + $Arg + '"'; $psi2.UseShellExecute = $true
    $p1 = [System.Diagnostics.Process]::Start($psi1)
    $p2 = [System.Diagnostics.Process]::Start($psi2)
    return @($p1.Id, $p2.Id)
}

$doubleCount = 0
$results = @()

for ($n = 1; $n -le $Iterations; $n++) {
    Stop-AllWagom
    $tStart = Get-Date

    $pids = Start-TwoSimultaneously -Exe $ExePath -Arg $File
    Start-Sleep -Seconds $WaitSeconds

    # 生存プロセス数（転送側は即終了、ホストだけ残る）。ただしこれは「GUI 本体だけが
    # 残る」設計への依存があり、将来 helper/常駐プロセス等が増えると過大評価し得る。
    $alive = @(Get-Process -Name $procName -ErrorAction SilentlyContinue)
    $aliveCount = $alive.Count

    # ログ側からも裏取り：今回作られた session-*.txt のうち
    # "Forwarded request" を含まない＝ホスト化したプロセス数
    $hostSessions = @(Get-ChildItem -LiteralPath $logDir -Filter "session-*.txt" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $tStart } |
        Where-Object { (Get-Content -LiteralPath $_.FullName -Raw) -notmatch "Forwarded request" })
    $hostCount = $hostSessions.Count

    # 単一インスタンス競合の再現は「ホストが2つ」が本質。生存プロセス数だけだと
    # 上記の理由で誤判定し得るため、ログ上のホスト数とのANDで強めに判定する。
    $isDouble = ($aliveCount -ge 2 -and $hostCount -ge 2)
    if ($isDouble) { $doubleCount++ }

    $tag = if ($isDouble) { "DOUBLE (bug)" } else { "ok" }
    Write-Host ("[{0,3}/{1}] pids=({2}) alive={3} hostSessions={4}  => {5}" -f `
        $n, $Iterations, ($pids -join ','), $aliveCount, $hostCount, $tag)

    $results += [pscustomobject]@{ Iter=$n; Alive=$aliveCount; Hosts=$hostCount; Double=$isDouble }
}

Stop-AllWagom

Write-Host "`n==================== RESULT ===================="
Write-Host ("二重起動(2窓)再現: {0} / {1} 回  ({2:P0})" -f $doubleCount, $Iterations, ($doubleCount / $Iterations))
Write-Host "================================================"
if ($doubleCount -gt 0) {
    Write-Host "→ 不具合を再現できました。" -ForegroundColor Yellow
} else {
    Write-Host "→ この設定では二重起動は出ませんでした（修正後の確認ならOK）。" -ForegroundColor Green
}
